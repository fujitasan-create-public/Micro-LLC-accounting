"""帳票（OUT-01〜22）。GET /reports/{report_id}?period_id=&format=json|csv

すべての帳票は {report_id, out_id, title, sections: [{title, columns: [[key, label]], rows}], notes} の形で返す。
画面は sections を表として描画し、CSV は sections を順に連結して出力する。
"""

from __future__ import annotations

import csv
import io
from datetime import date
from typing import Any, Awaitable, Callable

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response

from common import AppError, get_db, not_found
from db import Database
from domain import consumption_tax as ct
from domain.assets import depreciation_for_period
from domain.reports import financials as fin
from domain.rules.br042_withholding_deadline import period_label
from repositories import masters, reports as rq, rule_settings
from repositories.base import loads

router = APIRouter(prefix="/api/v1")

Builder = Callable[[Database, dict, dict, dict], Awaitable[dict]]
REPORTS: dict[str, dict[str, Any]] = {}


def report(report_id: str, out_id: str, title: str, params: list[str] | None = None):
    def deco(fn: Builder) -> Builder:
        REPORTS[report_id] = {"id": report_id, "out_id": out_id, "title": title, "params": params or [], "fn": fn}
        return fn
    return deco


def cols(*specs: str) -> list[list[str]]:
    return [s.split(":", 1) for s in specs]


def section(title: str, columns: list[list[str]], rows: list[dict]) -> dict:
    return {"title": title, "columns": columns, "rows": rows}


OPENING_SOURCES = ["carryover", "opening_balance"]


# ---------------------------------------------------------------------------
# OUT-01 仕訳帳
# ---------------------------------------------------------------------------


@report("journal", "OUT-01", "仕訳帳")
async def journal_book(db, period, company, q):
    lines = await rq.period_lines(db, period["id"], from_=q.get("from"), to=q.get("to"))
    rows, current, no = [], None, 0
    for ln in lines:
        if ln["entry_id"] != current:
            current = ln["entry_id"]
            no += 1
        rows.append({
            "no": no, "date": ln["transaction_date"], "description": ln["description"],
            "counterparty": ln["counterparty_name"] or "",
            "debit_account": ln["account_name"] if ln["side"] == "debit" else "",
            "debit_amount": ln["amount"] if ln["side"] == "debit" else "",
            "credit_account": ln["account_name"] if ln["side"] == "credit" else "",
            "credit_amount": ln["amount"] if ln["side"] == "credit" else "",
            "tax_code": ln["tax_code"], "tax_amount": ln["tax_amount"] or "",
        })
    return {"sections": [section("仕訳帳", cols("no:No", "date:日付", "description:摘要", "counterparty:取引先",
                                              "debit_account:借方科目", "debit_amount:借方金額", "credit_account:貸方科目",
                                              "credit_amount:貸方金額", "tax_code:税区分", "tax_amount:消費税額"), rows)]}


# ---------------------------------------------------------------------------
# OUT-02 総勘定元帳 / OUT-03 現金・預金出納帳 / OUT-04 売掛帳
# ---------------------------------------------------------------------------


def _ledger_rows(lines: list[dict], category: str, per_counterparty: bool = False) -> list[dict]:
    debit_nature = category in fin.DEBIT_NATURE
    bal = 0
    rows = []
    for ln in lines:
        d = ln["amount"] if ln["side"] == "debit" else 0
        c = ln["amount"] if ln["side"] == "credit" else 0
        bal += (d - c) if debit_nature else (c - d)
        rows.append({"date": ln["transaction_date"], "description": ln["description"],
                     "counterparty": ln["counterparty_name"] or "", "debit": d or "", "credit": c or "", "balance": bal,
                     "source": "繰越" if ln["source"] in OPENING_SOURCES else ""})
    return rows


LEDGER_COLS = cols("date:日付", "description:摘要", "counterparty:取引先", "debit:借方", "credit:貸方", "balance:残高", "source:区分")


@report("ledger", "OUT-02", "総勘定元帳", ["account"])
async def general_ledger(db, period, company, q):
    lines = await rq.period_lines(db, period["id"], account_code=q.get("account"))
    by_acct: dict[str, list[dict]] = {}
    for ln in lines:
        by_acct.setdefault(ln["account_code"], []).append(ln)
    sections = []
    for code in sorted(by_acct):
        ls = by_acct[code]
        sections.append(section(f"{code} {ls[0]['account_name']}", LEDGER_COLS, _ledger_rows(ls, ls[0]["category"])))
    return {"sections": sections}


@report("cash-book", "OUT-03", "現金出納帳・預金出納帳")
async def cash_book(db, period, company, q):
    pas = [p for p in await masters.list_payment_accounts(db) if p["type"] in ("cash", "bank")]
    codes = sorted({p["linked_account_code"] for p in pas} | {"100", "110"})
    sections = []
    for code in codes:
        lines = await rq.period_lines(db, period["id"], account_code=code)
        if not lines:
            continue
        names = "、".join(p["name"] for p in pas if p["linked_account_code"] == code)
        sections.append(section(f"{lines[0]['account_name']}" + (f"（{names}）" if names else ""), LEDGER_COLS,
                                _ledger_rows(lines, "asset")))
    return {"sections": sections}


@report("ar-book", "OUT-04", "売掛帳")
async def ar_book(db, period, company, q):
    lines = await rq.period_lines(db, period["id"], account_code="130")
    by_cp: dict[str, list[dict]] = {}
    for ln in lines:
        by_cp.setdefault(ln["counterparty_name"] or "（取引先なし）", []).append(ln)
    return {"sections": [section(name, LEDGER_COLS, _ledger_rows(ls, "asset")) for name, ls in sorted(by_cp.items())]}


# ---------------------------------------------------------------------------
# OUT-05 固定資産台帳 / OUT-17 償却資産申告の一覧
# ---------------------------------------------------------------------------

METHOD_LABELS = {"straight_line": "定額法", "declining_balance": "定率法", "immediate_small": "即時費用化（10万円未満）",
                 "lump_sum_3y": "一括償却資産（3年）", "small_sme_special": "中小企業者等の少額減価償却資産"}


@report("fixed-assets", "OUT-05", "固定資産台帳")
async def fixed_asset_ledger(db, period, company, q):
    assets = await db.all(
        """SELECT fa.*,
                  COALESCE((SELECT SUM(dr.amount) FROM depreciation_runs dr JOIN fiscal_periods fp ON fp.id = dr.fiscal_period_id
                            WHERE dr.asset_id = fa.id AND fp.end_date < ?), 0) AS acc_before
           FROM fixed_assets fa ORDER BY fa.acquisition_date""", [period["start_date"]])
    start, end = date.fromisoformat(period["start_date"]), date.fromisoformat(period["end_date"])
    rows = []
    for a in assets:
        dep = depreciation_for_period(method=a["depreciation_method"], cost=a["acquisition_cost"],
                                      useful_life_years=a["useful_life_years"],
                                      service_start=date.fromisoformat(a["service_start_date"]),
                                      disposal_date=date.fromisoformat(a["disposal_date"]) if a["disposal_date"] else None,
                                      period_start=start, period_end=end, accumulated_before=a["acc_before"])
        rows.append({"name": a["name"], "category": a["asset_category"], "acquisition_date": a["acquisition_date"],
                     "service_start_date": a["service_start_date"], "cost": a["acquisition_cost"],
                     "life": a["useful_life_years"], "method": METHOD_LABELS[a["depreciation_method"]],
                     "opening_book": a["acquisition_cost"] - a["acc_before"], "depreciation": dep,
                     "closing_book": a["acquisition_cost"] - a["acc_before"] - dep,
                     "disposal_date": a["disposal_date"] or "",
                     "return": "対象" if a["subject_to_depreciable_asset_return"] else "対象外"})
    return {"sections": [section("固定資産台帳", cols(
        "name:資産名", "category:種類", "acquisition_date:取得日", "service_start_date:事業供用日", "cost:取得価額",
        "life:耐用年数", "method:償却方法", "opening_book:期首帳簿価額", "depreciation:当期償却額",
        "closing_book:期末帳簿価額", "disposal_date:除却日", "return:償却資産申告"), rows)]}


@report("depreciable-assets", "OUT-17", "償却資産申告の一覧", ["year"])
async def depreciable_assets(db, period, company, q):
    year = int(q.get("year") or date.today().year + (1 if date.today().month >= 2 else 0))
    as_of = date(year, 1, 1).isoformat()
    rows = await db.all(
        """SELECT * FROM fixed_assets WHERE subject_to_depreciable_asset_return = 1
             AND depreciation_method NOT IN ('immediate_small', 'lump_sum_3y')
             AND acquisition_date < ? AND (disposal_date IS NULL OR disposal_date >= ?) ORDER BY acquisition_date""",
        [as_of, as_of])
    out = [{"name": r["name"], "category": r["asset_category"], "acquired": r["acquisition_date"][:7],
            "cost": r["acquisition_cost"], "life": r["useful_life_years"]} for r in rows]
    return {"sections": [section(f"{year}年1月1日現在の償却資産（{company['municipality']}へ1月31日までに申告）",
                                 cols("name:資産の名称", "category:種類", "acquired:取得年月", "cost:取得価額", "life:耐用年数"), out)],
            "notes": ["即時費用化した資産・一括償却資産は申告の対象外です。ソフトウェアなどの無形資産も対象外です。"]}


# ---------------------------------------------------------------------------
# OUT-06 試算表 / OUT-10〜13 決算書
# ---------------------------------------------------------------------------


async def _pl_bs(db: Database, period: dict) -> tuple[list[dict], dict, dict]:
    rows = await rq.account_totals(db, period["id"])
    pl = fin.income_statement(rows)
    bs = fin.balance_sheet(rows, pl["net_income"])
    return rows, pl, bs


@report("trial-balance", "OUT-06", "試算表", ["month"])
async def trial_balance(db, period, company, q):
    month = q.get("month")
    opening_rows = await rq.account_totals(db, period["id"], only_sources=OPENING_SOURCES)
    opening = {r["code"]: fin.balance_of(r) for r in opening_rows}
    if month:
        import calendar
        from datetime import timedelta

        y, m = int(month[:4]), int(month[5:7])
        m_start = date(y, m, 1)
        m_end = date(y, m, calendar.monthrange(y, m)[1])
        before = await rq.account_totals(db, period["id"], to=(m_start - timedelta(days=1)).isoformat(),
                                         exclude_sources=OPENING_SOURCES)
        start_bal = {r["code"]: opening.get(r["code"], 0) + fin.balance_of(r) for r in before}
        movement = await rq.account_totals(db, period["id"], from_=m_start.isoformat(), to=m_end.isoformat(),
                                           exclude_sources=OPENING_SOURCES)
        tb = fin.trial_balance(movement, start_bal)
        title = f"月次試算表（{month}）"
    else:
        movement = await rq.account_totals(db, period["id"], exclude_sources=OPENING_SOURCES)
        tb = fin.trial_balance(movement, opening)
        title = "年次試算表"
    total = {"code": "", "name": "合計", "opening": "", "debit": sum(r["debit"] for r in tb),
             "credit": sum(r["credit"] for r in tb), "closing": ""}
    return {"sections": [section(title, cols("code:コード", "name:勘定科目", "opening:期首（前月末）残高", "debit:借方",
                                             "credit:貸方", "closing:残高"), tb + [total])]}


def _stmt_rows(groups: dict[str, list[dict]], order: list[str]) -> list[dict]:
    rows = []
    for sec in order + [k for k in groups if k not in order]:
        if sec not in groups:
            continue
        rows.append({"name": f"【{sec}】", "amount": ""})
        for x in groups[sec]:
            rows.append({"name": f"　{x['name']}", "amount": x["amount"]})
        rows.append({"name": f"　{sec} 計", "amount": sum(x["amount"] for x in groups[sec])})
    return rows


@report("balance-sheet", "OUT-10", "貸借対照表")
async def balance_sheet(db, period, company, q):
    _, pl, bs = await _pl_bs(db, period)
    c = cols("name:科目", "amount:金額")
    notes = [] if bs["balanced"] else ["貸借が一致していません。仕訳を確認してください。"]
    return {"sections": [
        section("資産の部", c, _stmt_rows(bs["assets"], fin.BS_SECTIONS["asset"]) + [{"name": "資産合計", "amount": bs["total_assets"]}]),
        section("負債の部", c, _stmt_rows(bs["liabilities"], fin.BS_SECTIONS["liability"]) + [{"name": "負債合計", "amount": bs["total_liabilities"]}]),
        section("純資産の部", c, _stmt_rows(bs["equity"], fin.BS_SECTIONS["equity"]) + [
            {"name": "純資産合計", "amount": bs["total_equity"]},
            {"name": "負債・純資産合計", "amount": bs["total_liabilities"] + bs["total_equity"]}]),
    ], "notes": notes, "summary": {"net_income": pl["net_income"], "balanced": bs["balanced"]}}


@report("income-statement", "OUT-11", "損益計算書")
async def income_statement(db, period, company, q):
    _, pl, _ = await _pl_bs(db, period)
    s = pl["sections"]
    total = lambda k: sum(x["amount"] for x in s.get(k, []))  # noqa: E731
    rows: list[dict] = []

    def block(key: str):
        if key in s:
            rows.append({"name": f"【{key}】", "amount": ""})
            rows.extend({"name": f"　{x['name']}", "amount": x["amount"]} for x in s[key])
            rows.append({"name": f"　{key} 計", "amount": total(key)})

    block("売上高")
    rows.append({"name": "売上総利益", "amount": pl["gross_profit"]})
    block("販売費及び一般管理費")
    rows.append({"name": "営業利益", "amount": pl["operating_income"]})
    block("営業外収益")
    block("営業外費用")
    rows.append({"name": "経常利益", "amount": pl["ordinary_income"]})
    block("特別利益")
    block("特別損失")
    rows.append({"name": "税引前当期純利益", "amount": pl["income_before_taxes"]})
    rows.append({"name": "法人税、住民税及び事業税", "amount": pl["income_taxes"]})
    rows.append({"name": "当期純利益", "amount": pl["net_income"]})
    return {"sections": [section("損益計算書", cols("name:科目", "amount:金額"), rows)], "summary": pl}


@report("equity-changes", "OUT-12", "社員資本等変動計算書")
async def equity_changes(db, period, company, q):
    opening = await rq.account_totals(db, period["id"], only_sources=["carryover"])
    movement = await rq.account_totals(db, period["id"], exclude_sources=["carryover"])
    _, pl, _ = await _pl_bs(db, period)
    rows = fin.equity_changes(opening, movement, pl["net_income"])
    return {"sections": [section("社員資本等変動計算書", cols("name:科目", "opening:当期首残高", "changes:当期変動額（出資等）",
                                                          "net_income:当期純利益", "closing:当期末残高"), rows)]}


@report("notes", "OUT-13", "個別注記表")
async def notes_report(db, period, company, q):
    methods = {r["depreciation_method"] for r in await db.all("SELECT DISTINCT depreciation_method FROM fixed_assets")}
    return {"sections": [section("個別注記表", cols("item:項目", "text:内容"), fin.notes(company, methods, period))]}


# ---------------------------------------------------------------------------
# OUT-14 勘定科目内訳明細書の元データ
# ---------------------------------------------------------------------------


@report("breakdown", "OUT-14", "勘定科目内訳明細書の元データ")
async def breakdown(db, period, company, q):
    sections = []
    # 預貯金等
    rows = await db.all(
        """SELECT pa.name, pa.bank_name, pa.branch_name, pa.account_kind, pa.account_number, pa.linked_account_code,
                  COALESCE(SUM(CASE WHEN jl.side = 'debit' THEN jl.amount ELSE -jl.amount END), 0) AS balance
           FROM payment_accounts pa
           LEFT JOIN journal_entries je ON je.payment_account_id = pa.id AND je.voided_at IS NULL AND je.fiscal_period_id = ?
           LEFT JOIN journal_lines jl ON jl.entry_id = je.id AND jl.account_code = pa.linked_account_code
           WHERE pa.type IN ('bank', 'cash') GROUP BY pa.id ORDER BY pa.type, pa.name""", [period["id"]])
    totals = {r["code"]: fin.balance_of(r) for r in await rq.account_totals(db, period["id"])}
    attributed = {}
    for r in rows:
        attributed[r["linked_account_code"]] = attributed.get(r["linked_account_code"], 0) + r["balance"]
    for code, amt in attributed.items():
        if totals.get(code, 0) != amt:
            rows.append({"name": "（口座の指定がない仕訳）", "bank_name": "", "branch_name": "", "account_kind": "",
                         "account_number": "", "balance": totals.get(code, 0) - amt})
    sections.append(section("預貯金等の内訳書", cols("bank_name:金融機関名", "branch_name:支店名", "account_kind:種類",
                                                 "account_number:口座番号", "name:口座名", "balance:期末現在高"), rows))

    async def by_cp(code: str, title: str, debit_nature: bool):
        items = []
        for r in await rq.counterparty_balances(db, period["id"], code):
            bal = (r["debit"] - r["credit"]) if debit_nature else (r["credit"] - r["debit"])
            if bal:
                items.append({"counterparty": r["counterparty_name"], "address": r["address"] or "", "balance": bal})
        sections.append(section(title, cols("counterparty:相手先", "address:所在地", "balance:期末現在高"), items))

    await by_cp("130", "売掛金（未収入金）の内訳書", True)
    await by_cp("150", "仮払金（前渡金）の内訳書", True)
    await by_cp("200", "買掛金（未払金・未払費用）の内訳書（未払金）", False)

    officers = await db.all("SELECT * FROM officers ORDER BY created_at")
    officer_name = officers[0]["name"] if officers else company["representative_name"]
    officer_addr = officers[0]["address"] if officers else ""
    sections.append(section("借入金及び支払利子の内訳書（役員借入金）", cols("lender:借入先", "address:所在地", "relation:法人・代表者との関係", "balance:期末現在高"),
                            [{"lender": officer_name, "address": officer_addr, "relation": "代表社員", "balance": totals.get("250", 0)}]
                            if totals.get("250") else []))
    comp = await db.first(
        """SELECT COALESCE(SUM(gross_amount), 0) AS total FROM payroll_records
           WHERE voided_at IS NULL AND pay_date BETWEEN ? AND ?""", [period["start_date"], period["end_date"]])
    sections.append(section("役員報酬手当等及び人件費の内訳書", cols("title:役職名", "name:氏名", "address:住所", "total:役員給与計", "regular:定期同額給与"),
                            [{"title": "代表社員", "name": officer_name, "address": officer_addr,
                              "total": totals.get("500", 0), "regular": comp["total"]}]))
    rent = []
    for r in await rq.counterparty_balances(db, period["id"], "520"):
        amt = r["debit"] - r["credit"]
        if amt:
            rent.append({"kind": "", "use": "", "landlord": r["counterparty_name"], "address": r["address"] or "", "amount": amt})
    housing = await db.all("SELECT h.address, cp.name FROM company_housings h JOIN counterparties cp ON cp.id = h.landlord_id")
    for row in rent:
        for h in housing:
            if h["name"] == row["landlord"]:
                row["kind"], row["use"] = "家屋", f"社宅（{h['address']}）"
    sections.append(section("地代家賃等の内訳書", cols("kind:区分", "use:用途・所在地", "landlord:貸主の名称", "address:貸主の所在地", "amount:支払賃借料"), rent))
    misc = []
    for code, label in (("420", "雑益"), ("690", "雑損失")):
        for ln in await rq.period_lines(db, period["id"], account_code=code):
            amt = ln["amount"] if (ln["side"] == "credit") == (code == "420") else -ln["amount"]
            misc.append({"kind": label, "description": ln["description"], "counterparty": ln["counterparty_name"] or "", "amount": amt})
    sections.append(section("雑益、雑損失等の内訳書", cols("kind:科目", "description:取引の内容", "counterparty:相手先", "amount:金額"), misc))
    return {"sections": sections}


# ---------------------------------------------------------------------------
# OUT-15 法人事業概況説明書の元データ
# ---------------------------------------------------------------------------


@report("business-overview", "OUT-15", "法人事業概況説明書の元データ")
async def business_overview(db, period, company, q):
    rows = await rq.monthly_account_totals(db, period["id"])
    months: dict[str, dict] = {}
    for r in rows:
        m = months.setdefault(r["month"], {"month": r["month"], "sales": 0, "expenses": 0, "officer_comp": 0, "withholding": 0})
        if r["category"] == "revenue" and r["code"] == "400":
            m["sales"] += r["credit"] - r["debit"]
        if r["category"] == "expense" and r["code"] != "700":
            m["expenses"] += r["debit"] - r["credit"]
        if r["code"] == "500":
            m["officer_comp"] += r["debit"] - r["credit"]
    for p in await db.all("SELECT substr(pay_date, 1, 7) AS month, SUM(withholding_income_tax) AS w FROM payroll_records WHERE voided_at IS NULL AND pay_date BETWEEN ? AND ? GROUP BY month",
                          [period["start_date"], period["end_date"]]):
        months.setdefault(p["month"], {"month": p["month"], "sales": 0, "expenses": 0, "officer_comp": 0, "withholding": 0})["withholding"] = p["w"]
    carry = await db.first("SELECT business_overview_json FROM closing_carryovers WHERE fiscal_period_id = ?", [period["id"]])
    overview = loads(carry["business_overview_json"], {}) if carry else {}
    info = [{"item": k, "value": v} for k, v in overview.items()]
    info.append({"item": "経理の方法（消費税）", "value": "税込経理" if company["accounting_tax_method"] == "tax_included" else "税抜経理"})
    info.append({"item": "使用システム", "value": "Micro-LLC-accounting（自社利用の会計システム）"})
    return {"sections": [
        section("月別の売上高等", cols("month:月", "sales:売上（収入）金額", "expenses:経費計", "officer_comp:役員報酬", "withholding:源泉徴収税額"),
                sorted(months.values(), key=lambda x: x["month"])),
        section("事業内容等", cols("item:項目", "value:内容"), info),
    ]}


# ---------------------------------------------------------------------------
# OUT-16 消費税の集計表（FR-61）
# ---------------------------------------------------------------------------


async def consumption_tax_result(db: Database, period: dict, company: dict) -> tuple[list[dict], dict]:
    totals = await rq.tax_code_totals(db, period["id"])
    setting = await masters.get_consumption_tax(db, period["id"])
    summary = ct.summarize(totals, company["accounting_tax_method"])
    end = date.fromisoformat(period["end_date"])
    if not setting:
        return totals, {"error": "この会計期間の消費税設定がありません"}
    deemed = None
    if setting["calculation_method"] == "simplified":
        table = await rule_settings.value_on(db, "simplified_deemed_purchase_pct", end, {})
        deemed = int(table.get(str(setting["simplified_business_category"]), 0))
    result = ct.calculate(summary, taxable_status=setting["taxable_status"], method=setting["calculation_method"],
                          deemed_pct=deemed,
                          two_tenths_pct=int(await rule_settings.value_on(db, "two_tenths_special_deduction_pct", end, 80)))
    return totals, result


@report("consumption-tax", "OUT-16", "消費税の集計表")
async def consumption_tax_report(db, period, company, q):
    totals, result = await consumption_tax_result(db, period, company)
    rows = [{"tax_code": t["tax_code"], "name": t["tax_code_name"], "rate": t["rate"] or "",
             "deductible": f"{t['deductible_rate_pct']}%" if t["kind"] == "taxable_purchase" else "",
             "debit": t["debit_amount"], "credit": t["credit_amount"], "debit_tax": t["debit_tax"],
             "credit_tax": t["credit_tax"], "count": t["line_count"]} for t in totals]
    calc_rows = []
    if "error" in result:
        calc_rows.append({"item": "エラー", "amount": result["error"]})
    elif result["taxable_status"] == "exempt":
        calc_rows.append({"item": result["message"], "amount": 0})
    else:
        calc_rows.append({"item": "計算方法", "amount": result["basis"]})
        for s in result["sales"]:
            calc_rows.append({"item": f"課税標準額（{s['rate']}）", "amount": s["tax_base"]})
            calc_rows.append({"item": f"消費税額（国税・{s['rate']}）", "amount": s["national_tax"]})
        for p in result["purchases"]:
            calc_rows.append({"item": f"控除対象仕入税額（{p['rate']}・控除率{p['deductible_rate_pct']}%）", "amount": p["deductible_national_tax"]})
        calc_rows += [
            {"item": "売上に係る消費税額（国税）", "amount": result["sales_national_tax"]},
            {"item": "控除税額（国税）", "amount": result["deductible_national_tax"]},
            {"item": "差引税額（国税）", "amount": result["national_tax"]},
            {"item": "地方消費税", "amount": result["local_tax"]},
            {"item": "納付（還付）税額 合計", "amount": result["payable_total"]},
        ]
    return {"sections": [
        section("税区分別・税率別・控除率別の集計", cols("tax_code:税区分", "name:名称", "rate:税率", "deductible:控除率", "debit:借方金額",
                                                     "credit:貸方金額", "debit_tax:借方税額", "credit_tax:貸方税額", "count:件数"), rows),
        section("納付税額の計算", cols("item:項目", "amount:金額"), calc_rows),
    ], "summary": result}


# ---------------------------------------------------------------------------
# OUT-20 源泉徴収票 / OUT-21 給与支払報告書 / OUT-22 源泉所得税の納付書
# ---------------------------------------------------------------------------


async def _yearend(db: Database, year: int) -> dict | None:
    from routers.payroll import year_end_result

    officer = await db.first("SELECT id FROM officers ORDER BY created_at LIMIT 1")
    if not officer:
        return None
    return await year_end_result(db, year, officer["id"])


def _slip_rows(r: dict, company: dict) -> list[dict]:
    spouse = next((d for d in r["officer"]["dependents"] if d["relation"] == "spouse"), None)
    return [
        {"item": "支払を受ける者 住所", "value": r["officer"]["address"]},
        {"item": "支払を受ける者 氏名（役職）", "value": f"{r['officer']['name']}（代表社員）"},
        {"item": "種別", "value": "役員報酬"},
        {"item": "支払金額", "value": r["gross_total"]},
        {"item": "給与所得控除後の金額", "value": r["employment_income"]},
        {"item": "所得控除の額の合計額", "value": r["deductions"]["total"]},
        {"item": "源泉徴収税額", "value": r["annual_tax"]},
        {"item": "控除対象配偶者の有無", "value": "有" if r["deductions"]["spouse"] else ("無" if not spouse else "無（所得要件外）")},
        {"item": "控除対象扶養親族の数（配偶者を除く）", "value": sum(1 for d in r["officer"]["dependents"] if d["relation"] != "spouse")},
        {"item": "社会保険料等の金額", "value": r["deductions"]["social_insurance"] + r["deductions"]["small_business_mutual_aid"]},
        {"item": "生命保険料の控除額", "value": r["deductions"]["life_insurance"]},
        {"item": "地震保険料の控除額", "value": r["deductions"]["earthquake_insurance"]},
        {"item": "住宅借入金等特別控除の額", "value": r["housing_loan_deduction"]},
        {"item": "基礎控除の額", "value": r["deductions"]["basic"]},
        {"item": "年末調整による過不足額（＋還付／−徴収）", "value": r["difference"]},
        {"item": "支払者 住所", "value": company["head_office_address"]},
        {"item": "支払者 名称", "value": company["trade_name"]},
        {"item": "支払者 法人番号", "value": company["corporate_number"]},
    ]


@report("withholding-slip", "OUT-20", "源泉徴収票", ["year"])
async def withholding_slip(db, period, company, q):
    year = int(q.get("year") or date.today().year)
    r = await _yearend(db, year)
    if not r:
        return {"sections": [], "notes": ["役員が登録されていません"]}
    return {"sections": [section(f"{year}年分 給与所得の源泉徴収票（記載内容）", cols("item:項目", "value:内容"), _slip_rows(r, company))],
            "notes": ["年末調整の計算は概算です。マイナンバーは本システムに保存していないため、提出時に記入してください。"]}


@report("payroll-report", "OUT-21", "給与支払報告書の元データ", ["year"])
async def payroll_report(db, period, company, q):
    year = int(q.get("year") or date.today().year)
    r = await _yearend(db, year)
    if not r:
        return {"sections": [], "notes": ["役員が登録されていません"]}
    rows = _slip_rows(r, company)
    rows.insert(0, {"item": "提出先", "value": f"{year + 1}年1月1日現在の住所地の市区町村（{r['officer']['address']}）"})
    months = await db.all("SELECT pay_date, gross_amount, withholding_income_tax, resident_tax FROM payroll_records WHERE voided_at IS NULL AND substr(pay_date, 1, 4) = ? ORDER BY pay_date", [str(year)])
    return {"sections": [
        section(f"{year}年分 給与支払報告書（個人別明細書）の記載内容", cols("item:項目", "value:内容"), rows),
        section("月別の支給実績", cols("pay_date:支給日", "gross_amount:支給額", "withholding_income_tax:源泉所得税", "resident_tax:住民税（特別徴収）"), months),
    ], "notes": ["提出期限は翌年1月31日です。"]}


@report("withholding-payment-slip", "OUT-22", "源泉所得税の納付書の記載事項", ["year"])
async def withholding_payment_slip(db, period, company, q):
    year = int(q.get("year") or date.today().year)
    special = bool((await db.first("SELECT special_payment_deadline FROM withholding_settings WHERE id = 1") or {"special_payment_deadline": 0})["special_payment_deadline"])
    recs = await db.all("SELECT pay_date, gross_amount, withholding_income_tax FROM payroll_records WHERE voided_at IS NULL AND substr(pay_date, 1, 4) = ? ORDER BY pay_date", [str(year)])
    from domain.rules.br042_withholding_deadline import deadline_for_payment

    groups: dict[str, dict] = {}
    for r in recs:
        d = date.fromisoformat(r["pay_date"])
        label = period_label(d, special)
        fiscal_year = d.year if d.month >= 4 else d.year - 1
        g = groups.setdefault(label, {"period": label, "tax_office": company["tax_office"], "fiscal_year": f"{fiscal_year}年度",
                                      "pay_dates": [], "people": 0, "gross": 0, "tax": 0,
                                      "deadline": deadline_for_payment(d, special).isoformat()})
        g["pay_dates"].append(r["pay_date"])
        g["people"] = max(g["people"], 1)
        g["gross"] += r["gross_amount"]
        g["tax"] += r["withholding_income_tax"]
    rows = [{**g, "pay_dates": "、".join(g["pay_dates"]), "category": "俸給・給料等"} for g in groups.values()]
    return {"sections": [section("源泉所得税（給与所得・退職所得等）の納付書の記載事項", cols(
        "period:納期等の区分", "fiscal_year:年度", "tax_office:税務署", "category:区分", "pay_dates:支払年月日",
        "people:人員", "gross:支給額", "tax:税額", "deadline:納付期限"), rows)],
        "notes": ["納期の特例の承認を受けている場合、「納期等の区分」は半年分をまとめて記載します。" if special else "納期の特例なし: 支払月の翌月10日が期限です。"]}


# ---------------------------------------------------------------------------
# 共通
# ---------------------------------------------------------------------------


async def resolve_period(db: Database, period_id: str | None) -> dict:
    if period_id:
        p = await masters.get_period(db, period_id)
        if not p:
            raise not_found("会計期間")
        return p
    p = await masters.period_for_date(db, date.today().isoformat())
    if p:
        return p
    periods = await masters.list_periods(db)
    if not periods:
        raise AppError(422, "no_period", "会計期間がありません")
    return periods[-1]


def to_csv(rep: dict) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\r\n")
    w.writerow([rep["title"], rep.get("period_label", "")])
    for sec in rep["sections"]:
        w.writerow([])
        w.writerow([sec["title"]])
        w.writerow([label for _, label in sec["columns"]])
        for row in sec["rows"]:
            w.writerow([row.get(key, "") for key, _ in sec["columns"]])
    for n in rep.get("notes") or []:
        w.writerow([])
        w.writerow([n])
    return ("﻿" + buf.getvalue()).encode("utf-8")  # Excel で文字化けしないよう BOM 付き


@router.get("/reports")
async def list_reports():
    return {"items": [{k: v for k, v in r.items() if k != "fn"} for r in REPORTS.values()]}


@router.get("/reports/{report_id}")
async def get_report(report_id: str, request: Request, period_id: str | None = None, format: str = "json",
                     db: Database = Depends(get_db)):
    spec = REPORTS.get(report_id)
    if not spec:
        raise not_found("帳票")
    company = await masters.get_company(db)
    if not company:
        raise AppError(422, "no_company", "会社設定がありません")
    period = await resolve_period(db, period_id)
    q = dict(request.query_params)
    rep = await spec["fn"](db, period, company, q)
    rep.update({"report_id": report_id, "out_id": spec["out_id"], "title": spec["title"], "period": period,
                "period_label": f"{period['start_date']}〜{period['end_date']}", "company_name": company["trade_name"]})
    if format == "csv":
        return Response(content=to_csv(rep), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": f"attachment; filename={report_id}_{period['id']}.csv"})
    return rep
