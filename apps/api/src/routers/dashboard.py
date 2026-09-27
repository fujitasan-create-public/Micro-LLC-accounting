"""ホーム画面の資金管理。会社のお金（口座・現金）、支払予定・税金の見込みを差し引いた使えるお金、
今期の売上の内訳（経費・役員報酬・税金・残り）、月ごとの入出金と残高の推移、今後の自動引落しをまとめて返す。"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends

from common import AppError, get_db, today
from db import Database
from domain.reports import financials as fin
from repositories import masters, reports as rq
from routers.closing import CORP_ENTRY_PREFIX, CT_ENTRY_PREFIX, _existing_adjustment, tax_estimate
from routers.reports import consumption_tax_result
from services import recurring

router = APIRouter(prefix="/api/v1")

# 近いうちに会社から出ていく負債（役員借入金は社長への返済で急がないため別扱い）
PAYABLES = [
    ("200", "カードの未払・未払金"),
    ("210", "未払費用（社会保険料の会社負担など）"),
    ("220", "預り金（源泉所得税）"),
    ("221", "預り金（住民税）"),
    ("222", "預り金（社会保険料）"),
    ("240", "未払消費税等"),
    ("230", "未払法人税等"),
]
OFFICER_LOAN = "250"
OFFICER_COSTS = {"500", "510"}  # 役員報酬・法定福利費
TAX_COSTS = {"570", "700"}      # 租税公課・法人税等


@router.get("/dashboard")
async def dashboard(db: Database = Depends(get_db)):
    t = today()
    period = await masters.period_for_date(db, t.isoformat())
    if not period:
        periods = await masters.list_periods(db)
        if not periods:
            raise AppError(422, "no_period", "会計期間がありません")
        period = periods[-1]
    company = await masters.get_company(db)
    rows = await rq.account_totals(db, period["id"])
    bal = {r["code"]: fin.balance_of(r) for r in rows}
    names = {r["code"]: r["name"] for r in rows}

    # 会社のお金: 銀行口座・現金（口座・支払手段に登録した科目）
    pas = await masters.list_payment_accounts(db)
    cash_codes = {p["linked_account_code"] for p in pas if p["type"] in ("bank", "cash")} | {"100", "110"}
    cash = []
    for code in sorted(cash_codes):
        linked = [p["name"] for p in pas if p["linked_account_code"] == code and p["type"] in ("bank", "cash")]
        if bal.get(code, 0) or linked:
            cash.append({"code": code, "name": names.get(code, code), "accounts": linked, "balance": bal.get(code, 0)})
    cash_total = sum(c["balance"] for c in cash)

    payables = [{"code": c, "name": label, "amount": bal.get(c, 0)} for c, label in PAYABLES if bal.get(c, 0)]
    payables_total = sum(p["amount"] for p in payables)

    # 税金の見込み（決算でまだ計上していない分）
    reserves = []
    if company:
        if not await _existing_adjustment(db, period["id"], CT_ENTRY_PREFIX):
            _, ct = await consumption_tax_result(db, period, company)
            if ct.get("payable_total", 0) > 0:
                reserves.append({"name": "消費税の見込み（今期分）", "amount": ct["payable_total"], "kind": "consumption"})
        if not await _existing_adjustment(db, period["id"], CORP_ENTRY_PREFIX):
            try:
                est = await tax_estimate(db, period)
                if est["payable_after_interim"] > 0:
                    reserves.append({"name": "法人税・住民税・事業税の見込み（今期分）", "amount": est["payable_after_interim"], "kind": "corporate"})
            except AppError:
                pass
    reserves_total = sum(r["amount"] for r in reserves)

    # 今期の売上の内訳
    pl = fin.income_statement(rows)
    revenue = sum(bal.get(r["code"], 0) for r in rows if r["category"] == "revenue")
    officer = sum(bal.get(c, 0) for c in OFFICER_COSTS)
    tax_booked = sum(bal.get(c, 0) for c in TAX_COSTS)
    expenses = sum(bal.get(r["code"], 0) for r in rows
                   if r["category"] == "expense" and r["code"] not in OFFICER_COSTS | TAX_COSTS)
    # 税抜経理では売上に消費税が含まれないため、内訳には消費税の見込みを入れない
    included = company is None or company["accounting_tax_method"] == "tax_included"
    taxes = tax_booked + sum(r["amount"] for r in reserves if included or r["kind"] != "consumption")
    remaining = revenue - expenses - officer - taxes
    breakdown = {
        "revenue": revenue,
        "items": [
            {"key": "expenses", "name": "経費", "amount": expenses},
            {"key": "officer", "name": "役員報酬・社会保険", "amount": officer},
            {"key": "taxes", "name": "税金（見込みを含む）", "amount": taxes},
            {"key": "remaining", "name": "残り（会社に残るお金）", "amount": remaining},
        ],
    }

    # 月ごとの入金・出金と月末残高（会社のお金の科目）
    lines = await db.all(
        f"""SELECT substr(je.transaction_date, 1, 7) AS month, je.source,
                   SUM(CASE WHEN jl.side = 'debit' THEN jl.amount ELSE 0 END) AS inflow,
                   SUM(CASE WHEN jl.side = 'credit' THEN jl.amount ELSE 0 END) AS outflow
            FROM journal_lines jl JOIN journal_entries je ON je.id = jl.entry_id
            WHERE je.voided_at IS NULL AND je.fiscal_period_id = ? AND jl.account_code IN ({', '.join('?' for _ in cash_codes)})
            GROUP BY month, je.source IN ('carryover', 'opening_balance')""",
        [period["id"], *sorted(cash_codes)],
    )
    opening = sum(r["inflow"] - r["outflow"] for r in lines if r["source"] in ("carryover", "opening_balance"))
    by_month: dict[str, dict] = {}
    for r in lines:
        if r["source"] in ("carryover", "opening_balance"):
            continue
        m = by_month.setdefault(r["month"], {"month": r["month"], "inflow": 0, "outflow": 0})
        m["inflow"] += r["inflow"]
        m["outflow"] += r["outflow"]
    months = []
    running = opening
    start = date.fromisoformat(period["start_date"])
    y, mth = start.year, start.month
    last = min(t, date.fromisoformat(period["end_date"])).strftime("%Y-%m")
    while f"{y:04d}-{mth:02d}" <= last:
        key = f"{y:04d}-{mth:02d}"
        m = by_month.get(key, {"month": key, "inflow": 0, "outflow": 0})
        running += m["inflow"] - m["outflow"]
        months.append({**m, "balance": running})
        y, mth = (y + 1, 1) if mth == 12 else (y, mth + 1)

    return {
        "as_of": t.isoformat(),
        "period": period,
        "cash": cash,
        "cash_total": cash_total,
        "payables": payables,
        "payables_total": payables_total,
        "reserves": reserves,
        "reserves_total": reserves_total,
        "available": cash_total - payables_total - reserves_total,
        "officer_loan": bal.get(OFFICER_LOAN, 0),
        "breakdown": breakdown,
        "net_income": pl["net_income"],
        "opening_cash": opening,
        "months": months,
        "upcoming": await recurring.upcoming(db, t, cash_codes),
    }
