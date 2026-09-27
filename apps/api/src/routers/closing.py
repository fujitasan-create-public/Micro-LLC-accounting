"""決算（FR-60〜64, BR-091, BR-092, DM-17）、期限一覧（第7章）、エクスポート（FR-71）。"""

from __future__ import annotations

import json
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from common import AppError, get_backup_storage, get_db, get_evidence_storage, not_found, now_iso, today
from db import Database
from domain import deadlines as dl
from domain.journal import BuiltLine
from domain.reports import financials as fin
from domain.rules.br010_sme import is_sme
from domain.rules.br031_regular_compensation import add_months
from domain.rules.br091_corporate_tax_estimate import apply_loss_carryforwards, estimate
from domain.rules.br092_interim_filing import interim_filing_required
from repositories import masters, reports as rq, rule_settings
from repositories.base import loads
from routers.reports import consumption_tax_result
from services import export as exp
from services import journals as svc
from storage import ObjectStorage

router = APIRouter(prefix="/api/v1")

CT_PAYABLE, INPUT_TAX, OUTPUT_TAX, TAXES_AND_DUES = "240", "160", "245", "570"
CORP_TAX_EXPENSE, CORP_TAX_PAYABLE, RETAINED = "700", "230", "310"
MISC_INCOME, MISC_LOSS = "420", "690"
CT_ENTRY_PREFIX = "【決算整理】未払消費税等の計上"
CORP_ENTRY_PREFIX = "【決算整理】未払法人税等の計上"


async def _period(db: Database, period_id: str) -> dict:
    p = await masters.get_period(db, period_id)
    if not p:
        raise not_found("会計期間")
    return p


async def _carryover(db: Database, period_id: str) -> dict:
    row = await db.first("SELECT * FROM closing_carryovers WHERE fiscal_period_id = ?", [period_id])
    if not row:
        await db.run("INSERT OR IGNORE INTO closing_carryovers (fiscal_period_id, updated_at) VALUES (?, ?)", [period_id, now_iso()])
        row = await db.first("SELECT * FROM closing_carryovers WHERE fiscal_period_id = ?", [period_id])
    return {
        "fiscal_period_id": period_id,
        "loss_carryforwards": loads(row["loss_carryforwards_json"], []),
        "prior_corporate_tax": row["prior_corporate_tax"],
        "interim_payments": loads(row["interim_payments_json"], []),
        "resident_tax_per_capita": row["resident_tax_per_capita"],
        "business_overview": loads(row["business_overview_json"], {}),
        "updated_at": row["updated_at"],
    }


# ---------------------------------------------------------------------------
# 繰越情報（DM-17）
# ---------------------------------------------------------------------------


class LossCarryforward(BaseModel):
    origin_period: str
    remaining_amount: int = Field(ge=0)


class InterimPayment(BaseModel):
    tax_type: str
    amount: int = Field(ge=0)
    paid_date: date


class CarryoverIn(BaseModel):
    loss_carryforwards: list[LossCarryforward] = []
    prior_corporate_tax: int = Field(default=0, ge=0)
    interim_payments: list[InterimPayment] = []
    resident_tax_per_capita: int = Field(default=70000, ge=0)
    business_overview: dict = {}


@router.get("/fiscal-periods/{period_id}/carryover")
async def get_carryover(period_id: str, db: Database = Depends(get_db)):
    await _period(db, period_id)
    c = await _carryover(db, period_id)
    threshold = int(await rule_settings.value_on(db, "interim_filing_threshold", today(), 200000))
    c["interim_filing_required"] = interim_filing_required(c["prior_corporate_tax"], threshold)
    return c


@router.put("/fiscal-periods/{period_id}/carryover")
async def put_carryover(period_id: str, body: CarryoverIn, db: Database = Depends(get_db)):
    await _period(db, period_id)
    await _carryover(db, period_id)
    d = body.model_dump(mode="json")
    await db.run(
        """UPDATE closing_carryovers SET loss_carryforwards_json = ?, prior_corporate_tax = ?, interim_payments_json = ?,
             resident_tax_per_capita = ?, business_overview_json = ?, updated_at = ? WHERE fiscal_period_id = ?""",
        [json.dumps(d["loss_carryforwards"], ensure_ascii=False), d["prior_corporate_tax"],
         json.dumps(d["interim_payments"], ensure_ascii=False), d["resident_tax_per_capita"],
         json.dumps(d["business_overview"], ensure_ascii=False), now_iso(), period_id])
    return await get_carryover(period_id, db)


# ---------------------------------------------------------------------------
# 法人税等の概算（FR-62, BR-091）
# ---------------------------------------------------------------------------


async def tax_estimate(db: Database, period: dict) -> dict:
    company = await masters.get_company(db)
    rows = await rq.account_totals(db, period["id"])
    pl = fin.income_statement(rows)
    start = date.fromisoformat(period["start_date"])
    carry = await _carryover(db, period["id"])
    sme = is_sme(company["capital_amount"], int(await rule_settings.value_on(db, "sme_capital_limit", start, 100_000_000)))
    pretax = pl["income_before_taxes"]
    taxable, remaining_losses, used = apply_loss_carryforwards(pretax, carry["loss_carryforwards"], sme)
    corp_rate = await rule_settings.value_on(db, "corporate_tax_rate", start)
    if corp_rate is None:
        raise AppError(422, "settings_missing", "法人税率の設定値がありません", "BR-000")
    result = estimate(
        taxable_income=taxable, is_sme=sme, per_capita=carry["resident_tax_per_capita"], corporate_rate=corp_rate,
        local_corporate_rate=await rule_settings.value_on(db, "local_corporate_tax_rate", start, "0.103"),
        defense=await rule_settings.value_on(db, "defense_special_corporate_tax", start),
        enterprise_rates=await rule_settings.value_on(db, "enterprise_tax_rates", start, []),
        special_enterprise_rate=await rule_settings.value_on(db, "special_enterprise_tax_rate", start, "0.37"),
        resident_corporate_rate=await rule_settings.value_on(db, "resident_tax_corporate_rate", start, "0.07"),
    )
    interim_total = sum(int(p["amount"]) for p in carry["interim_payments"])
    new_losses = remaining_losses + ([{"origin_period": period["id"], "remaining_amount": -pretax}] if pretax < 0 else [])
    return {
        **result,
        "income_before_taxes": pretax,
        "loss_carryforward_used": used,
        "loss_carryforwards_after": new_losses,
        "is_sme": sme,
        "interim_payments_total": interim_total,
        "payable_after_interim": result["total"] - interim_total,
        "notice": "概算です。交際費の損金不算入・役員給与の損金不算入などの申告調整は反映していません。税率は都道府県・市区町村ごとに異なるため、設定値を確認してください。",
    }


@router.get("/fiscal-periods/{period_id}/tax-estimate")
async def get_tax_estimate(period_id: str, db: Database = Depends(get_db)):
    return await tax_estimate(db, await _period(db, period_id))


# ---------------------------------------------------------------------------
# 決算の状況と決算整理仕訳（FR-60, FR-61）
# ---------------------------------------------------------------------------


async def _existing_adjustment(db: Database, period_id: str, prefix: str) -> dict | None:
    return await db.first(
        "SELECT id FROM journal_entries WHERE fiscal_period_id = ? AND voided_at IS NULL AND source = 'closing_adjustment' AND description LIKE ?",
        [period_id, prefix + "%"])


@router.get("/fiscal-periods/{period_id}/closing")
async def closing_status(period_id: str, db: Database = Depends(get_db)):
    period = await _period(db, period_id)
    company = await masters.get_company(db)
    prev = await masters.previous_period(db, period["start_date"])
    dep = await db.first("SELECT COUNT(*) AS n FROM depreciation_runs WHERE fiscal_period_id = ?", [period_id])
    assets = await db.first("SELECT COUNT(*) AS n FROM fixed_assets WHERE service_start_date <= ?", [period["end_date"]])
    _, ct_result = await consumption_tax_result(db, period, company)
    rows = await rq.account_totals(db, period["id"])
    pl = fin.income_statement(rows)
    bs = fin.balance_sheet(rows, pl["net_income"])
    try:
        tax = await tax_estimate(db, period)
    except AppError as e:
        tax = {"error": e.message}
    checklist = [
        {"key": "previous_closed", "label": "前期の締め処理", "done": prev is None or prev["status"] == "closed"},
        {"key": "depreciation", "label": "減価償却費の計上", "done": dep["n"] > 0 or assets["n"] == 0},
        {"key": "consumption_tax", "label": "未払消費税等の計上",
         "done": bool(await _existing_adjustment(db, period_id, CT_ENTRY_PREFIX)) or ct_result.get("payable_total", 0) <= 0},
        {"key": "corporate_tax", "label": "未払法人税等の計上", "done": bool(await _existing_adjustment(db, period_id, CORP_ENTRY_PREFIX))},
        {"key": "balanced", "label": "貸借対照表の貸借一致", "done": bs["balanced"]},
    ]
    return {"period": period, "checklist": checklist, "consumption_tax": ct_result, "tax_estimate": tax,
            "income_statement": {k: v for k, v in pl.items() if k != "sections"}}


@router.post("/fiscal-periods/{period_id}/closing-entries/consumption-tax", status_code=201)
async def book_consumption_tax(period_id: str, db: Database = Depends(get_db)):
    period = await _period(db, period_id)
    company = await masters.get_company(db)
    if await _existing_adjustment(db, period_id, CT_ENTRY_PREFIX):
        raise AppError(409, "already_booked", "未払消費税等は計上済みです。やり直す場合は該当の仕訳を取り消してください")
    _, result = await consumption_tax_result(db, period, company)
    if "error" in result:
        raise AppError(422, "no_setting", result["error"])
    payable = result.get("payable_total", 0)
    end = date.fromisoformat(period["end_date"])
    lines: list[BuiltLine] = []
    if company["accounting_tax_method"] == "tax_included":
        if payable <= 0:
            raise AppError(422, "nothing_to_book", "納付する消費税額がありません（還付の場合は未収入金として手入力してください）")
        lines = [BuiltLine(1, "debit", TAXES_AND_DUES, payable, "NT", 0, None),
                 BuiltLine(2, "credit", CT_PAYABLE, payable, "NT", 0, None)]
    else:
        totals = {r["code"]: fin.balance_of(r) for r in await rq.account_totals(db, period_id)}
        received, paid = totals.get(OUTPUT_TAX, 0), totals.get(INPUT_TAX, 0)
        raw = []
        if received:
            raw.append(("debit", OUTPUT_TAX, received))
        if paid:
            raw.append(("credit", INPUT_TAX, paid))
        if payable > 0:
            raw.append(("credit", CT_PAYABLE, payable))
        diff = received - paid - max(payable, 0)
        if diff > 0:
            raw.append(("credit", MISC_INCOME, diff))
        elif diff < 0:
            raw.append(("debit", MISC_LOSS, -diff))
        lines = [BuiltLine(i, s, a, amt, "NT", 0, None) for i, (s, a, amt) in enumerate(raw, start=1)]
    entry_id, _ = await svc.create_entry(db, transaction_date=end, description=f"{CT_ENTRY_PREFIX}（{result.get('basis', '')}）",
                                         lines=[], prebuilt=lines, source="closing_adjustment")
    return {"entry_id": entry_id, "amount": payable}


class CorporateTaxIn(BaseModel):
    amount: int | None = Field(default=None, ge=0, description="省略すると概算額から中間納付額を差し引いた額")


@router.post("/fiscal-periods/{period_id}/closing-entries/corporate-tax", status_code=201)
async def book_corporate_tax(period_id: str, body: CorporateTaxIn | None = None, db: Database = Depends(get_db)):
    """未払法人税等の計上。中間納付額は納付時に「法人税、住民税及び事業税」で処理している前提。"""
    period = await _period(db, period_id)
    if await _existing_adjustment(db, period_id, CORP_ENTRY_PREFIX):
        raise AppError(409, "already_booked", "未払法人税等は計上済みです。やり直す場合は該当の仕訳を取り消してください")
    amount = body.amount if body and body.amount is not None else None
    if amount is None:
        est = await tax_estimate(db, period)
        amount = max(est["payable_after_interim"], 0)
    if amount <= 0:
        raise AppError(422, "nothing_to_book", "計上する金額がありません")
    entry_id, _ = await svc.create_entry(
        db, transaction_date=date.fromisoformat(period["end_date"]), description=CORP_ENTRY_PREFIX, lines=[],
        prebuilt=[BuiltLine(1, "debit", CORP_TAX_EXPENSE, amount, "NT", 0, None),
                  BuiltLine(2, "credit", CORP_TAX_PAYABLE, amount, "NT", 0, None)],
        source="closing_adjustment")
    return {"entry_id": entry_id, "amount": amount}


# ---------------------------------------------------------------------------
# 締め処理と残高繰越（FR-63, NFR-01, NFR-03）
# ---------------------------------------------------------------------------


@router.post("/fiscal-periods/{period_id}/close")
async def close_period(period_id: str, db: Database = Depends(get_db),
                       backup: ObjectStorage = Depends(get_backup_storage)):
    period = await _period(db, period_id)
    if period["status"] == "closed":
        raise AppError(409, "already_closed", "この会計期間は締め済みです")
    prev = await masters.previous_period(db, period["start_date"])
    if prev and prev["status"] != "closed":
        raise AppError(409, "previous_open", "前の会計期間を先に締めてください", "FR-63")

    rows = await rq.account_totals(db, period_id)
    pl = fin.income_statement(rows)
    bs = fin.balance_sheet(rows, pl["net_income"])
    if not bs["balanced"]:
        raise AppError(409, "unbalanced", "貸借対照表の貸借が一致しません")
    try:
        est = await tax_estimate(db, period)
    except AppError:
        est = None

    # 翌期の会計期間（無ければ作る）
    end = date.fromisoformat(period["end_date"])
    nxt = await masters.next_period(db, period["end_date"])
    if not nxt:
        ns = end + timedelta(days=1)
        ne = add_months(ns, 12) - timedelta(days=1)
        nid = f"FY{ns.isoformat()}"
        await db.run("INSERT INTO fiscal_periods (id, start_date, end_date, status) VALUES (?, ?, ?, 'open')",
                     [nid, ns.isoformat(), ne.isoformat()])
        nxt = await masters.get_period(db, nid)
        ct = await masters.get_consumption_tax(db, period_id)
        if ct:
            data = {k: v for k, v in ct.items() if k != "fiscal_period_id"}
            if data["calculation_method"] == "two_tenths_special":
                data["calculation_method"] = "standard"  # BR-021: 翌期も使えるかはユーザーが確認して設定する
            await masters.save_consumption_tax(db, nid, data)
    if nxt["status"] == "closed":
        raise AppError(409, "next_closed", "翌期が既に締められています")

    await masters.set_period_status(db, period_id, "closing")

    # 残高繰越の仕訳（翌期首の日付、source=carryover）
    raw: list[tuple[str, str, int]] = []
    for r in rows:
        if r["category"] not in ("asset", "liability", "equity"):
            continue
        bal = fin.balance_of(r) + (pl["net_income"] if r["code"] == RETAINED else 0)
        if bal == 0:
            continue
        natural = "debit" if r["category"] == "asset" else "credit"
        other = "credit" if natural == "debit" else "debit"
        raw.append((natural if bal > 0 else other, r["code"], abs(bal)))
    try:
        if raw:
            await svc.create_entry(
                db, transaction_date=date.fromisoformat(nxt["start_date"]),
                description=f"前期繰越（{period['start_date']}〜{period['end_date']}）", lines=[],
                prebuilt=[BuiltLine(i, s, a, amt, "NT", 0, None) for i, (s, a, amt) in enumerate(raw, start=1)],
                source="carryover")
    except Exception:
        await masters.set_period_status(db, period_id, "open")
        raise

    # 翌期の繰越情報（DM-17）
    carry = await _carryover(db, period_id)
    await _carryover(db, nxt["id"])
    await db.run(
        """UPDATE closing_carryovers SET loss_carryforwards_json = ?, prior_corporate_tax = ?, resident_tax_per_capita = ?, updated_at = ?
           WHERE fiscal_period_id = ?""",
        [json.dumps(est["loss_carryforwards_after"] if est else carry["loss_carryforwards"], ensure_ascii=False),
         est["corporate_tax"] if est else 0, carry["resident_tax_per_capita"], now_iso(), nxt["id"]])

    await masters.set_period_status(db, period_id, "closed")

    archived: list[str] = []
    try:
        archived = await exp.archive_closed_period(db, backup, period, {"income_statement": pl, "balance_sheet": bs, "tax_estimate": est})
    except Exception as e:  # アーカイブの失敗で締め処理自体は戻さない
        return {"closed": True, "next_period": nxt, "archived": [], "warnings": [{"rule_id": "NFR-01", "message": f"年次アーカイブに失敗しました: {e}"}]}
    return {"closed": True, "next_period": nxt, "archived": archived, "warnings": []}


# ---------------------------------------------------------------------------
# 期限一覧（第7章）
# ---------------------------------------------------------------------------


@router.get("/deadlines")
async def deadlines(from_: date | None = Query(default=None, alias="from"), to: date | None = None,
                    db: Database = Depends(get_db)):
    start = from_ or today()
    end = to or (start + timedelta(days=60))
    periods = await masters.list_periods(db)
    ws = await db.first("SELECT special_payment_deadline FROM withholding_settings WHERE id = 1")
    has_payroll = bool(await db.first("SELECT 1 AS x FROM officer_compensations LIMIT 1")) or \
        bool(await db.first("SELECT 1 AS x FROM payroll_records LIMIT 1"))
    threshold = int(await rule_settings.value_on(db, "interim_filing_threshold", today(), 200000))
    interim = set()
    for p in periods:
        c = await db.first("SELECT prior_corporate_tax FROM closing_carryovers WHERE fiscal_period_id = ?", [p["id"]])
        ct = await masters.get_consumption_tax(db, p["id"])
        if (c and interim_filing_required(c["prior_corporate_tax"], threshold)) or (ct and ct["interim_filing_required"]):
            interim.add(p["id"])
    items = dl.compute(start=start, end=end, periods=periods, special_withholding=bool(ws and ws["special_payment_deadline"]),
                       interim_required_period_ids=interim, has_payroll=has_payroll)
    soon = (today() + timedelta(days=14)).isoformat()
    for it in items:
        it["within_14_days"] = it["date"] <= soon
    return {"items": items}


# ---------------------------------------------------------------------------
# エクスポート（FR-71, NFR-04）
# ---------------------------------------------------------------------------


@router.post("/exports")
async def export_all(include_files: bool = True, db: Database = Depends(get_db),
                     evidence: ObjectStorage = Depends(get_evidence_storage)):
    data = await exp.build_zip(db, evidence, include_files)
    name = f"accounting-export-{today().isoformat()}.zip"
    return Response(content=data, media_type="application/zip", headers={"Content-Disposition": f"attachment; filename={name}"})
