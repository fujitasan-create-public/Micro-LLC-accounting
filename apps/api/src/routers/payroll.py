"""役員・役員報酬・給与・源泉所得税・年末調整（FR-30〜34, BR-031, BR-042, DM-11〜14）。"""

from __future__ import annotations

import csv
import io
import json
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, File, UploadFile
from pydantic import BaseModel, Field

from common import AppError, get_db, new_id, not_found, now_iso
from db import Database
from domain import payroll as dp
from domain import yearend
from domain.journal import LineIn
from domain.rules import br031_regular_compensation as br031
from domain.rules.br042_withholding_deadline import deadline_for_payment, period_label
from repositories import masters, rule_settings
from repositories.base import insert, loads, update
from services import journals as svc

router = APIRouter(prefix="/api/v1")


# ---------------------------------------------------------------------------
# 役員（DM-11）。マイナンバーは入力欄を設けない（NFR-05）
# ---------------------------------------------------------------------------


class Dependent(BaseModel):
    name: str
    relation: Literal["spouse", "child", "parent", "other"]
    birth_date: date | None = None
    income: int = 0
    cohabiting_parent: bool = False


class OfficerIn(BaseModel):
    name: str = Field(min_length=1)
    address: str = Field(min_length=1)
    dependents: list[Dependent] = []


def _officer_out(o: dict) -> dict:
    o = dict(o)
    o["dependents"] = loads(o.pop("dependents_json"), [])
    return o


@router.get("/officers")
async def list_officers(db: Database = Depends(get_db)):
    return {"items": [_officer_out(o) for o in await db.all("SELECT * FROM officers ORDER BY created_at")]}


@router.post("/officers", status_code=201)
async def create_officer(body: OfficerIn, db: Database = Depends(get_db)):
    now = now_iso()
    oid = new_id()
    await insert(db, "officers", {
        "id": oid, "name": body.name, "address": body.address, "my_number_stored_externally": True,
        "dependents_json": json.dumps(body.model_dump(mode="json")["dependents"], ensure_ascii=False),
        "created_at": now, "updated_at": now,
    })
    return _officer_out(await db.first("SELECT * FROM officers WHERE id = ?", [oid]))


@router.put("/officers/{oid}")
async def update_officer(oid: str, body: OfficerIn, db: Database = Depends(get_db)):
    if not await db.first("SELECT id FROM officers WHERE id = ?", [oid]):
        raise not_found("役員")
    await update(db, "officers", "id", oid, {
        "name": body.name, "address": body.address,
        "dependents_json": json.dumps(body.model_dump(mode="json")["dependents"], ensure_ascii=False),
        "updated_at": now_iso(),
    })
    return _officer_out(await db.first("SELECT * FROM officers WHERE id = ?", [oid]))


# ---------------------------------------------------------------------------
# 役員報酬の改定履歴（FR-30, BR-031）
# ---------------------------------------------------------------------------


class CompensationIn(BaseModel):
    effective_from: date
    monthly_amount: int = Field(ge=0)
    payment_day: int = Field(ge=1, le=31)
    resolution_date: date
    revision_reason: Literal["regular", "performance_deterioration", "other"]


async def _compensations(db: Database, oid: str) -> list[dict]:
    rows = await db.all("SELECT * FROM officer_compensations WHERE officer_id = ? ORDER BY effective_from", [oid])
    for r in rows:
        r["effective_from_date"] = date.fromisoformat(r["effective_from"])
    return rows


async def _comp_warnings(db: Database, comps: list[dict]) -> list[dict]:
    months = int(await rule_settings.value_on(db, "officer_comp_revision_months", date.today(), 3))
    data = [{"effective_from": c["effective_from_date"], "monthly_amount": c["monthly_amount"],
             "revision_reason": c["revision_reason"]} for c in comps]
    warnings = []
    for p in await masters.list_periods(db):
        warnings.extend(br031.revision_warnings(date.fromisoformat(p["start_date"]), date.fromisoformat(p["end_date"]),
                                                data, months))
    return warnings


@router.get("/officers/{oid}/compensations")
async def list_compensations(oid: str, db: Database = Depends(get_db)):
    comps = await _compensations(db, oid)
    warnings = await _comp_warnings(db, comps)
    for c in comps:
        c.pop("effective_from_date")
    return {"items": comps, "warnings": warnings}


@router.post("/officers/{oid}/compensations", status_code=201)
async def add_compensation(oid: str, body: CompensationIn, db: Database = Depends(get_db)):
    if not await db.first("SELECT id FROM officers WHERE id = ?", [oid]):
        raise not_found("役員")
    if body.resolution_date > body.effective_from:
        warnings_pre = [{"rule_id": "BR-031", "message": "社員総会の決定日が適用開始日より後になっています"}]
    else:
        warnings_pre = []
    await insert(db, "officer_compensations", {
        "id": new_id(), "officer_id": oid, "effective_from": body.effective_from.isoformat(),
        "monthly_amount": body.monthly_amount, "payment_day": body.payment_day,
        "resolution_date": body.resolution_date.isoformat(), "revision_reason": body.revision_reason,
        "created_at": now_iso(),
    })
    res = await list_compensations(oid, db)
    res["warnings"] = warnings_pre + res["warnings"]
    return res


# ---------------------------------------------------------------------------
# 源泉徴収税額表（FR-32, NFR-07）
# ---------------------------------------------------------------------------


@router.post("/withholding-tables/{year}/import")
async def import_withholding_table(year: int, file: UploadFile = File(...), db: Database = Depends(get_db)):
    """CSV 形式: min_amount,max_amount,dep0,dep1,...,dep7（金額は円。max_amount が空なら上限なし）。
    国税庁が公表する月額表・甲欄を、この形式に変換して取り込む。既存の同年データは置き換える。"""
    from domain.bank_csv import decode

    text = decode(await file.read())
    stmts = [("DELETE FROM withholding_tables WHERE table_year = ?", [year])]
    count = 0
    for row in csv.reader(io.StringIO(text)):
        if not row or not row[0].strip().replace(",", "").isdigit():
            continue
        vals = [c.strip().replace(",", "") for c in row]
        lo = int(vals[0])
        hi = int(vals[1]) if vals[1] else None
        for dep, tax in enumerate(vals[2:10]):
            if tax == "":
                continue
            stmts.append(("INSERT INTO withholding_tables (table_year, min_amount, max_amount, dependents, tax_amount) VALUES (?, ?, ?, ?, ?)",
                          [year, lo, hi, dep, int(tax)]))
            count += 1
    for i in range(0, len(stmts), 200):  # D1 の batch を分割（設計書 5.5）
        await db.batch(stmts[i:i + 200])
    return {"year": year, "rows": count}


@router.get("/withholding-tables/{year}/lookup")
async def lookup(year: int, amount: int, dependents: int = 0, db: Database = Depends(get_db)):
    rows = await db.all(
        "SELECT * FROM withholding_tables WHERE table_year = ? AND dependents = ? AND min_amount <= ? ORDER BY min_amount DESC LIMIT 1",
        [year, min(dependents, 7), amount])
    return {"tax_amount": dp.lookup_withholding(rows, amount, dependents)}


# ---------------------------------------------------------------------------
# 給与支給実績（FR-31, FR-32, DM-12）
# ---------------------------------------------------------------------------


class PayrollIn(BaseModel):
    officer_id: str
    pay_date: date
    gross_amount: int = Field(ge=0)
    health_insurance_employee: int = Field(ge=0)
    pension_employee: int = Field(ge=0)
    health_insurance_employer: int = Field(ge=0)
    pension_employer: int = Field(ge=0)
    standard_monthly_remuneration: int = Field(ge=0)
    withholding_income_tax: int | None = Field(default=None, ge=0, description="省略すると税額表から自動計算")
    resident_tax: int = Field(ge=0)
    company_housing_deduction: int = Field(default=0, ge=0)
    payment_account_id: str


@router.get("/payroll")
async def list_payroll(year: int | None = None, db: Database = Depends(get_db)):
    where, params = "WHERE p.voided_at IS NULL", []
    if year:
        where += " AND substr(p.pay_date, 1, 4) = ?"
        params.append(str(year))
    rows = await db.all(f"""SELECT p.*, o.name AS officer_name FROM payroll_records p JOIN officers o ON o.id = p.officer_id
                            {where} ORDER BY p.pay_date DESC""", params)
    return {"items": rows}


@router.post("/payroll", status_code=201)
async def create_payroll(body: PayrollIn, db: Database = Depends(get_db)):
    officer = await db.first("SELECT * FROM officers WHERE id = ?", [body.officer_id])
    if not officer:
        raise not_found("役員")
    pa = await masters.get_payment_account(db, body.payment_account_id)
    if not pa:
        raise not_found("口座・支払手段")
    warnings: list[dict] = []

    wht = body.withholding_income_tax
    inp = dp.PayrollInput(body.gross_amount, body.health_insurance_employee, body.pension_employee,
                          body.health_insurance_employer, body.pension_employer, wht or 0, body.resident_tax,
                          body.company_housing_deduction)
    if wht is None:
        deps = dp.withholding_dependents_count(loads(officer["dependents_json"], []), body.pay_date)
        amount = dp.taxable_after_social_insurance(inp)
        rows = await db.all(
            "SELECT * FROM withholding_tables WHERE table_year = ? AND dependents = ? AND min_amount <= ? ORDER BY min_amount DESC LIMIT 1",
            [body.pay_date.year, min(deps, 7), amount])
        found = dp.lookup_withholding(rows, amount, deps)
        if found is None:
            raise AppError(422, "withholding_table_missing",
                           f"{body.pay_date.year}年の源泉徴収税額表に該当する行がありません。税額を手入力するか、税額表を取り込んでください", "FR-32")
        inp.withholding_income_tax = found
        warnings.append({"rule_id": "FR-32", "message": f"源泉所得税を税額表（扶養{deps}人）から {found:,}円 と計算しました"})

    comps = await _compensations(db, body.officer_id)
    w = br031.payment_mismatch_warning(
        [{"effective_from": c["effective_from_date"], "monthly_amount": c["monthly_amount"],
          "revision_reason": c["revision_reason"]} for c in comps], body.pay_date, body.gross_amount)
    if w:
        warnings.append(w)

    net = dp.net_amount(inp)
    if net < 0:
        raise AppError(422, "negative_net", "差引支給額がマイナスになります")
    rec_id = new_id()
    now = now_iso()

    def extra(entry_id: str):
        return [(
            """INSERT INTO payroll_records (id, officer_id, pay_date, gross_amount, health_insurance_employee, pension_employee,
                 health_insurance_employer, pension_employer, standard_monthly_remuneration, withholding_income_tax,
                 resident_tax, company_housing_deduction, net_amount, payment_account_id, journal_entry_id, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [rec_id, body.officer_id, body.pay_date.isoformat(), inp.gross_amount, inp.health_insurance_employee,
             inp.pension_employee, inp.health_insurance_employer, inp.pension_employer,
             body.standard_monthly_remuneration, inp.withholding_income_tax, inp.resident_tax,
             inp.company_housing_deduction, net, pa["id"], entry_id, now, now],
        )]

    await svc.create_entry(
        db, transaction_date=body.pay_date, description=f"役員報酬 {body.pay_date.strftime('%Y年%m月')}分 {officer['name']}",
        lines=[], prebuilt=dp.journal_lines(inp, pa["linked_account_code"]), source="manual",
        payment_account_id=pa["id"], extra_statements=extra,
    )
    ws = await withholding_settings(db)
    warnings.append({"rule_id": "BR-042", "message":
                     f"源泉所得税の納付期限は {deadline_for_payment(body.pay_date, bool(ws['special_payment_deadline'])).isoformat()} です"})
    return {"record": await db.first("SELECT * FROM payroll_records WHERE id = ?", [rec_id]), "warnings": warnings}


class SocialInsurancePaidIn(BaseModel):
    paid_date: date
    payment_account_id: str
    employee_amount: int = Field(ge=0)
    employer_amount: int = Field(ge=0)


@router.post("/payroll/social-insurance-payments", status_code=201)
async def pay_social_insurance(body: SocialInsurancePaidIn, db: Database = Depends(get_db)):
    """社会保険料の口座振替（預り金（社会保険料）と未払費用を消し込む）。"""
    pa = await masters.get_payment_account(db, body.payment_account_id)
    if not pa:
        raise not_found("口座・支払手段")
    total = body.employee_amount + body.employer_amount
    lines = []
    if body.employee_amount:
        lines.append(LineIn("debit", dp.SOCIAL_PAYABLE, body.employee_amount, "NT"))
    if body.employer_amount:
        lines.append(LineIn("debit", dp.ACCRUED_EXPENSES, body.employer_amount, "NT"))
    lines.append(LineIn("credit", pa["linked_account_code"], total, "NT"))
    eid, w = await svc.create_entry(db, transaction_date=body.paid_date, description="社会保険料の納付",
                                    lines=lines, payment_account_id=pa["id"])
    return {"entry_id": eid, "warnings": w}


# ---------------------------------------------------------------------------
# 源泉所得税の設定・納付（DM-13, FR-33, BR-042）
# ---------------------------------------------------------------------------


async def withholding_settings(db: Database) -> dict:
    row = await db.first("SELECT * FROM withholding_settings WHERE id = 1")
    return row or {"special_payment_deadline": 0}


class WithholdingSettingIn(BaseModel):
    special_payment_deadline: bool


@router.get("/withholding/settings")
async def get_withholding_settings(db: Database = Depends(get_db)):
    return await withholding_settings(db)


@router.put("/withholding/settings")
async def put_withholding_settings(body: WithholdingSettingIn, db: Database = Depends(get_db)):
    await db.run(
        """INSERT INTO withholding_settings (id, special_payment_deadline, updated_at) VALUES (1, ?, ?)
           ON CONFLICT (id) DO UPDATE SET special_payment_deadline = excluded.special_payment_deadline, updated_at = excluded.updated_at""",
        [1 if body.special_payment_deadline else 0, now_iso()])
    return await withholding_settings(db)


@router.get("/withholding/status")
async def withholding_status(year: int, db: Database = Depends(get_db)):
    """FR-33: 納付単位ごとの源泉徴収額・納付額・納付期限。"""
    special = bool((await withholding_settings(db))["special_payment_deadline"])
    rows = await db.all(
        "SELECT pay_date, withholding_income_tax, gross_amount FROM payroll_records WHERE voided_at IS NULL AND substr(pay_date, 1, 4) = ?",
        [str(year)])
    periods: dict[str, dict] = {}
    for r in rows:
        d = date.fromisoformat(r["pay_date"])
        label = period_label(d, special)
        p = periods.setdefault(label, {"period": label, "withheld": 0, "gross": 0, "count": 0,
                                       "deadline": deadline_for_payment(d, special).isoformat(), "paid": 0})
        p["withheld"] += r["withholding_income_tax"]
        p["gross"] += r["gross_amount"]
        p["count"] += 1
    for pay in await db.all("SELECT * FROM withholding_payments WHERE period LIKE ?", [f"{year}-%"]):
        if pay["period"] in periods:
            periods[pay["period"]]["paid"] += pay["amount"]
    items = sorted(periods.values(), key=lambda x: x["period"])
    for it in items:
        it["unpaid"] = it["withheld"] - it["paid"]
    return {"special_payment_deadline": special, "items": items,
            "payments": await db.all("SELECT * FROM withholding_payments ORDER BY paid_date DESC")}


class WithholdingPaymentIn(BaseModel):
    period: str = Field(pattern=r"^\d{4}-(\d{2}|H[12])$")
    amount: int = Field(gt=0)
    paid_date: date
    payment_account_id: str


@router.post("/withholding/payments", status_code=201)
async def pay_withholding(body: WithholdingPaymentIn, db: Database = Depends(get_db)):
    pa = await masters.get_payment_account(db, body.payment_account_id)
    if not pa:
        raise not_found("口座・支払手段")
    pid = new_id()
    now = now_iso()
    eid, w = await svc.create_entry(
        db, transaction_date=body.paid_date, description=f"源泉所得税の納付（{body.period}分）",
        lines=[LineIn("debit", dp.WITHHOLDING_PAYABLE, body.amount, "NT"),
               LineIn("credit", pa["linked_account_code"], body.amount, "NT")],
        payment_account_id=pa["id"],
        extra_statements=lambda entry_id: [(
            "INSERT INTO withholding_payments (id, period, amount, paid_date, created_at) VALUES (?, ?, ?, ?, ?)",
            [pid, body.period, body.amount, body.paid_date.isoformat(), now])],
    )
    return {"id": pid, "entry_id": eid, "warnings": w}


# ---------------------------------------------------------------------------
# 年末調整（FR-34, DM-14）
# ---------------------------------------------------------------------------


class YearEndIn(BaseModel):
    officer_id: str
    life_insurance_deduction_inputs: dict = {}
    earthquake_insurance_premium: int = Field(default=0, ge=0)
    small_business_mutual_aid_premium: int = Field(default=0, ge=0)
    social_insurance_paid_personally: int = Field(default=0, ge=0)
    spouse_income: int | None = None
    housing_loan_deduction: int = Field(default=0, ge=0)


async def year_end_result(db: Database, year: int, officer_id: str) -> dict:
    officer = await db.first("SELECT * FROM officers WHERE id = ?", [officer_id])
    if not officer:
        raise not_found("役員")
    inputs = await db.first("SELECT * FROM year_end_adjustments WHERE year = ? AND officer_id = ?", [year, officer_id]) or {}
    if inputs:
        inputs = dict(inputs)
        inputs["life_insurance_deduction_inputs"] = loads(inputs["life_insurance_deduction_inputs"], {})
    totals = await db.first(
        """SELECT COALESCE(SUM(gross_amount), 0) AS gross, COALESCE(SUM(health_insurance_employee + pension_employee), 0) AS si,
                  COALESCE(SUM(withholding_income_tax), 0) AS wht, COUNT(*) AS n
           FROM payroll_records WHERE voided_at IS NULL AND officer_id = ? AND substr(pay_date, 1, 4) = ?""",
        [officer_id, str(year)])
    on = date(year, 12, 31)
    settings = {
        "employment_income_deduction": await rule_settings.value_on(db, "employment_income_deduction", on),
        "basic_deduction": await rule_settings.value_on(db, "basic_deduction", on),
        "income_tax_brackets": await rule_settings.value_on(db, "income_tax_brackets", on),
        "reconstruction_rate": await rule_settings.value_on(db, "reconstruction_tax_rate", on, "0"),
        "dependent_deductions": await rule_settings.value_on(db, "dependent_deductions", on),
        "earthquake_cap": await rule_settings.value_on(db, "earthquake_insurance_deduction_cap", on, 50000),
    }
    if any(v is None for v in settings.values()):
        raise AppError(422, "settings_missing", f"{year}年の年末調整に必要な設定値がありません", "BR-000")
    result = yearend.calculate(
        year=year, gross_total=totals["gross"], social_insurance_withheld=totals["si"],
        withheld_tax_total=totals["wht"], dependents=loads(officer["dependents_json"], []),
        inputs=inputs, settings=settings)
    result["officer"] = _officer_out(officer)
    result["payment_count"] = totals["n"]
    result["inputs"] = inputs
    return result


@router.get("/year-end-adjustments/{year}")
async def get_year_end(year: int, officer_id: str, db: Database = Depends(get_db)):
    return await year_end_result(db, year, officer_id)


@router.put("/year-end-adjustments/{year}")
async def put_year_end(year: int, body: YearEndIn, db: Database = Depends(get_db)):
    await db.run(
        """INSERT INTO year_end_adjustments (officer_id, year, life_insurance_deduction_inputs, earthquake_insurance_premium,
             small_business_mutual_aid_premium, social_insurance_paid_personally, spouse_income, housing_loan_deduction, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT (officer_id, year) DO UPDATE SET
             life_insurance_deduction_inputs = excluded.life_insurance_deduction_inputs,
             earthquake_insurance_premium = excluded.earthquake_insurance_premium,
             small_business_mutual_aid_premium = excluded.small_business_mutual_aid_premium,
             social_insurance_paid_personally = excluded.social_insurance_paid_personally,
             spouse_income = excluded.spouse_income, housing_loan_deduction = excluded.housing_loan_deduction,
             updated_at = excluded.updated_at""",
        [body.officer_id, year, json.dumps(body.life_insurance_deduction_inputs), body.earthquake_insurance_premium,
         body.small_business_mutual_aid_premium, body.social_insurance_paid_personally, body.spouse_income,
         body.housing_loan_deduction, now_iso()])
    return await year_end_result(db, year, body.officer_id)
