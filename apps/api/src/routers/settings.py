"""初期設定とマスタ（FR-01, FR-02, DM-01〜07, BR-000, BR-020, BR-021）。"""

from __future__ import annotations

import json
from datetime import date
from typing import Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator

from common import AppError, get_db, new_id, not_found, now_iso
from db import Database
from domain.rules.br010_sme import is_sme
from domain.rules.br020_taxable_status_hint import taxable_status_hint
from domain.rules.br021_two_tenths_special import allowed_calculation_methods
from repositories import masters, rule_settings
from repositories.base import insert, update

router = APIRouter(prefix="/api/v1")


# ---------------------------------------------------------------------------
# 初期設定の状況（FR-01）
# ---------------------------------------------------------------------------


@router.get("/setup/status")
async def setup_status(db: Database = Depends(get_db)):
    company = await masters.get_company(db)
    periods = await masters.list_periods(db)
    ct = await masters.get_consumption_tax(db, periods[-1]["id"]) if periods else None
    return {
        "company": company is not None,
        "fiscal_period": bool(periods),
        "consumption_tax": ct is not None,
        "completed": company is not None and bool(periods) and ct is not None,
    }


# ---------------------------------------------------------------------------
# 会社設定（DM-01）
# ---------------------------------------------------------------------------


class CompanyIn(BaseModel):
    trade_name: str = Field(min_length=1)
    corporate_number: str = Field(pattern=r"^\d{13}$")
    head_office_address: str = Field(min_length=1)
    representative_name: str = Field(min_length=1)
    incorporation_date: date
    capital_amount: int = Field(ge=0)
    fiscal_year_start_month: int = Field(ge=1, le=12)
    blue_return_approved: bool
    blue_return_effective_from: date | None = None
    tax_office: str = Field(min_length=1)
    prefecture: str = Field(min_length=1)
    municipality: str = Field(min_length=1)
    accounting_tax_method: Literal["tax_included", "tax_excluded"]


@router.get("/company")
async def get_company(db: Database = Depends(get_db)):
    c = await masters.get_company(db)
    if not c:
        return {"company": None}
    limit = await rule_settings.value_on(db, "sme_capital_limit", date.today(), 100_000_000)
    return {"company": c, "is_sme": is_sme(c["capital_amount"], int(limit))}


@router.put("/company")
async def put_company(body: CompanyIn, db: Database = Depends(get_db)):
    data = body.model_dump()
    for k in ("incorporation_date", "blue_return_effective_from"):
        data[k] = data[k].isoformat() if data[k] else None
    await masters.save_company(db, data, now_iso())
    return await get_company(db)


# ---------------------------------------------------------------------------
# 会計期間（DM-03）
# ---------------------------------------------------------------------------


class FiscalPeriodIn(BaseModel):
    start_date: date
    end_date: date


@router.get("/fiscal-periods")
async def list_fiscal_periods(db: Database = Depends(get_db)):
    return {"items": await masters.list_periods(db)}


@router.get("/fiscal-periods/{period_id}")
async def get_fiscal_period(period_id: str, db: Database = Depends(get_db)):
    p = await masters.get_period(db, period_id)
    if not p:
        raise not_found("会計期間")
    return p


@router.post("/fiscal-periods", status_code=201)
async def create_fiscal_period(body: FiscalPeriodIn, db: Database = Depends(get_db)):
    if body.end_date <= body.start_date:
        raise AppError(422, "invalid_period", "期末日は期首日より後にしてください")
    if (body.end_date - body.start_date).days > 366:
        raise AppError(422, "invalid_period", "事業年度は1年以内にしてください")
    if await masters.overlapping_period(db, body.start_date.isoformat(), body.end_date.isoformat()):
        raise AppError(409, "overlap", "既存の会計期間と重なっています")
    pid = f"FY{body.start_date.isoformat()}"
    await insert(db, "fiscal_periods", {
        "id": pid, "start_date": body.start_date.isoformat(), "end_date": body.end_date.isoformat(), "status": "open",
    })
    await db.run(
        "INSERT OR IGNORE INTO closing_carryovers (fiscal_period_id, updated_at) VALUES (?, ?)", [pid, now_iso()]
    )
    return await masters.get_period(db, pid)


# ---------------------------------------------------------------------------
# 消費税設定（DM-02, BR-020, BR-021）
# ---------------------------------------------------------------------------


class ConsumptionTaxIn(BaseModel):
    taxable_status: Literal["exempt", "taxable"]
    invoice_registration_number: str | None = Field(default=None, pattern=r"^T\d{13}$")
    calculation_method: Literal["standard", "simplified", "two_tenths_special"]
    simplified_business_category: Literal["1", "2", "3", "4", "5", "6"] | None = None
    interim_filing_required: bool = False

    @field_validator("invoice_registration_number", mode="before")
    @classmethod
    def empty_to_none(cls, v: Any) -> Any:
        return v or None


async def _two_tenths_last(db: Database, on: date) -> date:
    v = await rule_settings.value_on(db, "two_tenths_special_last_period_contains", on, "2026-09-30")
    return date.fromisoformat(v)


@router.get("/fiscal-periods/{period_id}/consumption-tax")
async def get_consumption_tax(period_id: str, db: Database = Depends(get_db)):
    p = await masters.get_period(db, period_id)
    if not p:
        raise not_found("会計期間")
    setting = await masters.get_consumption_tax(db, period_id)
    start = date.fromisoformat(p["start_date"])
    last = await _two_tenths_last(db, start)
    company = await masters.get_company(db)
    hint = None
    if company:
        periods = await masters.list_periods(db)
        index = [x["id"] for x in periods].index(period_id) + 1
        hint = taxable_status_hint(
            capital_amount=company["capital_amount"],
            incorporation_date=date.fromisoformat(company["incorporation_date"]),
            period_start=start,
            period_index=index,
            has_invoice_registration=bool(setting and setting.get("invoice_registration_number")),
        )
    return {
        "setting": setting,
        "allowed_calculation_methods": allowed_calculation_methods(start, last),
        "status_hint": hint,
    }


@router.put("/fiscal-periods/{period_id}/consumption-tax")
async def put_consumption_tax(period_id: str, body: ConsumptionTaxIn, db: Database = Depends(get_db)):
    p = await masters.get_period(db, period_id)
    if not p:
        raise not_found("会計期間")
    start = date.fromisoformat(p["start_date"])
    if body.taxable_status == "taxable":
        allowed = allowed_calculation_methods(start, await _two_tenths_last(db, start))
        if body.calculation_method not in allowed:
            raise AppError(
                422, "two_tenths_not_available",
                "2割特例は2026年9月30日を含む課税期間までしか使えません（課税期間の開始日が2026年10月1日以後のため選択不可）",
                "BR-021",
            )
        if body.calculation_method == "two_tenths_special" and not body.invoice_registration_number:
            raise AppError(422, "two_tenths_requires_invoice", "2割特例はインボイス登録により課税事業者になった場合に使えます", "BR-021")
    if body.calculation_method == "simplified" and not body.simplified_business_category:
        raise AppError(422, "category_required", "簡易課税では事業区分を選んでください")
    await masters.save_consumption_tax(db, period_id, body.model_dump())
    return await get_consumption_tax(period_id, db)


# ---------------------------------------------------------------------------
# 税区分・勘定科目（FR-02, DM-04, DM-05）
# ---------------------------------------------------------------------------


@router.get("/tax-codes")
async def list_tax_codes(db: Database = Depends(get_db)):
    return {"items": await masters.list_tax_codes(db)}


class AccountIn(BaseModel):
    code: str = Field(pattern=r"^[0-9A-Za-z_-]{1,10}$")
    name: str = Field(min_length=1)
    category: Literal["asset", "liability", "equity", "revenue", "expense"]
    statement_section: str = Field(min_length=1)
    default_tax_code: str
    requires_counterparty: bool = False
    is_active: bool = True


class AccountPatch(BaseModel):
    name: str | None = None
    statement_section: str | None = None
    default_tax_code: str | None = None
    requires_counterparty: bool | None = None
    is_active: bool | None = None


@router.get("/accounts")
async def list_accounts(active_only: bool = False, db: Database = Depends(get_db)):
    return {"items": await masters.list_accounts(db, include_inactive=not active_only)}


@router.post("/accounts", status_code=201)
async def create_account(body: AccountIn, db: Database = Depends(get_db)):
    if not await masters.get_tax_code(db, body.default_tax_code):
        raise AppError(422, "invalid_tax_code", "税区分が存在しません")
    await insert(db, "accounts", body.model_dump())
    return await masters.get_account(db, body.code)


@router.patch("/accounts/{code}")
async def patch_account(code: str, body: AccountPatch, db: Database = Depends(get_db)):
    if not await masters.get_account(db, code):
        raise not_found("勘定科目")
    await update(db, "accounts", "code", code, body.model_dump(exclude_none=True))
    return await masters.get_account(db, code)


# ---------------------------------------------------------------------------
# 取引先（DM-06）
# ---------------------------------------------------------------------------


class CounterpartyIn(BaseModel):
    name: str = Field(min_length=1)
    entity_type: Literal["corporation", "individual"]
    invoice_registration_number: str | None = Field(default=None, pattern=r"^T\d{13}$")
    address: str | None = None
    bank_account: str | None = None
    is_client: bool = False

    @field_validator("invoice_registration_number", mode="before")
    @classmethod
    def empty_to_none(cls, v: Any) -> Any:
        return v or None


class CounterpartyPatch(CounterpartyIn):
    name: str | None = None  # type: ignore[assignment]
    entity_type: Literal["corporation", "individual"] | None = None  # type: ignore[assignment]
    is_client: bool | None = None  # type: ignore[assignment]


@router.get("/counterparties")
async def list_counterparties(db: Database = Depends(get_db)):
    return {"items": await masters.list_counterparties(db)}


@router.post("/counterparties", status_code=201)
async def create_counterparty(body: CounterpartyIn, db: Database = Depends(get_db)):
    now = now_iso()
    cid = new_id()
    await insert(db, "counterparties", {"id": cid, **body.model_dump(), "created_at": now, "updated_at": now})
    return await masters.get_counterparty(db, cid)


@router.patch("/counterparties/{cp_id}")
async def patch_counterparty(cp_id: str, body: CounterpartyPatch, db: Database = Depends(get_db)):
    if not await masters.get_counterparty(db, cp_id):
        raise not_found("取引先")
    data = body.model_dump(exclude_unset=True)
    data["updated_at"] = now_iso()
    await update(db, "counterparties", "id", cp_id, data)
    return await masters.get_counterparty(db, cp_id)


# ---------------------------------------------------------------------------
# 口座・支払手段（DM-07）
# ---------------------------------------------------------------------------


class PaymentAccountIn(BaseModel):
    name: str = Field(min_length=1)
    type: Literal["bank", "credit_card", "cash", "officer_advance"]
    bank_name: str | None = None
    branch_name: str | None = None
    account_kind: str | None = None
    account_number: str | None = None
    linked_account_code: str
    csv_import_format: str | None = None


class PaymentAccountPatch(BaseModel):
    name: str | None = None
    bank_name: str | None = None
    branch_name: str | None = None
    account_kind: str | None = None
    account_number: str | None = None
    linked_account_code: str | None = None
    csv_import_format: str | None = None


@router.get("/payment-accounts")
async def list_payment_accounts(db: Database = Depends(get_db)):
    return {"items": await masters.list_payment_accounts(db)}


@router.post("/payment-accounts", status_code=201)
async def create_payment_account(body: PaymentAccountIn, db: Database = Depends(get_db)):
    if not await masters.get_account(db, body.linked_account_code):
        raise AppError(422, "invalid_account", "対応する勘定科目が存在しません")
    if body.type == "officer_advance" and body.linked_account_code != "250":
        raise AppError(422, "officer_advance_account", "役員による立替は役員借入金（250）に紐付けてください", "FR-15")
    now = now_iso()
    pid = new_id()
    await insert(db, "payment_accounts", {"id": pid, **body.model_dump(), "created_at": now, "updated_at": now})
    return await masters.get_payment_account(db, pid)


@router.patch("/payment-accounts/{pa_id}")
async def patch_payment_account(pa_id: str, body: PaymentAccountPatch, db: Database = Depends(get_db)):
    if not await masters.get_payment_account(db, pa_id):
        raise not_found("口座・支払手段")
    data = body.model_dump(exclude_unset=True)
    data["updated_at"] = now_iso()
    await update(db, "payment_accounts", "id", pa_id, data)
    return await masters.get_payment_account(db, pa_id)


# ---------------------------------------------------------------------------
# 設定値（BR-000）
# ---------------------------------------------------------------------------


class RuleSettingIn(BaseModel):
    key: str = Field(min_length=1)
    value: Any
    effective_from: date
    effective_to: date | None = None
    note: str | None = None


@router.get("/rule-settings")
async def list_rule_settings(db: Database = Depends(get_db)):
    return {"items": await rule_settings.list_all(db)}


@router.post("/rule-settings", status_code=201)
async def upsert_rule_setting(body: RuleSettingIn, db: Database = Depends(get_db)):
    if body.effective_to and body.effective_to < body.effective_from:
        raise AppError(422, "invalid_range", "適用終了日は適用開始日以後にしてください")
    await rule_settings.upsert(
        db, body.key, json.dumps(body.value, ensure_ascii=False), body.effective_from.isoformat(),
        body.effective_to.isoformat() if body.effective_to else None, body.note,
    )
    return {"ok": True}
