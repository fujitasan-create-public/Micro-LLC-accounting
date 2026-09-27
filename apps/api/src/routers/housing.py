"""借上げ社宅（FR-40〜42, BR-081, DM-15）。"""

from __future__ import annotations

import calendar
from datetime import date
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from common import AppError, get_db, new_id, not_found, now_iso
from db import Database
from domain.journal import BuiltLine, LineIn
from domain.rules import br081_company_housing as br081
from repositories import masters, rule_settings
from repositories.base import insert, update
from services import journals as svc

router = APIRouter(prefix="/api/v1")

RENT_ACCOUNT = "520"
RESIDENTIAL_RENT_TAX_CODE = "PEX"  # 住宅の家賃は非課税（FR-42）


class HousingIn(BaseModel):
    landlord_id: str
    address: str = Field(min_length=1)
    contract_start: date
    contract_end: date
    monthly_rent: int = Field(ge=0)
    monthly_common_fee: int = Field(default=0, ge=0)
    floor_area_sqm: Decimal = Field(gt=0)
    structure: Literal["wooden", "non_wooden"]
    building_tax_base: int = Field(ge=0)
    land_tax_base: int = Field(ge=0)
    is_luxury: bool = False
    market_rent: int | None = Field(default=None, ge=0)
    collection_amount: int = Field(ge=0)
    collection_method: Literal["payroll_deduction", "transfer"]


class HousingPatch(BaseModel):
    contract_end: date | None = None
    monthly_rent: int | None = Field(default=None, ge=0)
    monthly_common_fee: int | None = Field(default=None, ge=0)
    building_tax_base: int | None = Field(default=None, ge=0)
    land_tax_base: int | None = Field(default=None, ge=0)
    is_luxury: bool | None = None
    market_rent: int | None = Field(default=None, ge=0)
    collection_amount: int | None = Field(default=None, ge=0)
    collection_method: Literal["payroll_deduction", "transfer"] | None = None


async def _imputed(db: Database, h: dict) -> dict:
    on = date.today()
    result = br081.imputed_rent(
        structure=h["structure"], floor_area_sqm=Decimal(str(h["floor_area_sqm"])),
        building_tax_base=h["building_tax_base"], land_tax_base=h["land_tax_base"],
        monthly_rent=h["monthly_rent"], is_luxury=bool(h["is_luxury"]), market_rent=h["market_rent"],
        small_limits=await rule_settings.value_on(db, "housing_small_area_limit_sqm", on),
        small_formula=await rule_settings.value_on(db, "housing_small_formula", on),
        large_formula=await rule_settings.value_on(db, "housing_large_formula", on),
    )
    warning = br081.collection_warning(h["collection_amount"], result["amount"])
    result["collection_amount"] = h["collection_amount"]
    result["shortfall"] = max(result["amount"] - h["collection_amount"], 0)
    result["warnings"] = [warning] if warning else []
    if bool(h["is_luxury"]) and not h["market_rent"]:
        result["warnings"].append({"rule_id": "BR-081", "message": "豪華社宅の場合は時価（market_rent）を入力してください"})
    return result


async def _get(db: Database, hid: str) -> dict:
    h = await db.first(
        "SELECT h.*, cp.name AS landlord_name FROM company_housings h JOIN counterparties cp ON cp.id = h.landlord_id WHERE h.id = ?",
        [hid])
    if not h:
        raise not_found("借上げ社宅")
    return h


@router.get("/housings")
async def list_housings(db: Database = Depends(get_db)):
    rows = await db.all(
        "SELECT h.*, cp.name AS landlord_name FROM company_housings h JOIN counterparties cp ON cp.id = h.landlord_id ORDER BY h.contract_start DESC")
    for r in rows:
        r["imputed_rent"] = await _imputed(db, r)
    return {"items": rows}


@router.post("/housings", status_code=201)
async def create_housing(body: HousingIn, db: Database = Depends(get_db)):
    if not await masters.get_counterparty(db, body.landlord_id):
        raise AppError(422, "invalid_landlord", "貸主（取引先）が存在しません")
    if body.contract_end < body.contract_start:
        raise AppError(422, "invalid_period", "契約終了日は契約開始日以後にしてください")
    now = now_iso()
    hid = new_id()
    data = body.model_dump(mode="json")
    data["floor_area_sqm"] = str(body.floor_area_sqm)
    await insert(db, "company_housings", {"id": hid, **data, "created_at": now, "updated_at": now})
    h = await _get(db, hid)
    return {"housing": h, "imputed_rent": await _imputed(db, h)}


@router.patch("/housings/{hid}")
async def patch_housing(hid: str, body: HousingPatch, db: Database = Depends(get_db)):
    await _get(db, hid)
    data = body.model_dump(mode="json", exclude_none=True)
    data["updated_at"] = now_iso()
    await update(db, "company_housings", "id", hid, data)
    h = await _get(db, hid)
    return {"housing": h, "imputed_rent": await _imputed(db, h)}


@router.get("/housings/{hid}/imputed-rent")
async def imputed_rent(hid: str, db: Database = Depends(get_db)):
    """BR-081 / FR-40, FR-41: 賃料相当額と、徴収額が下回る場合の警告。"""
    return await _imputed(db, await _get(db, hid))


class HousingJournalIn(BaseModel):
    year_month: str = Field(pattern=r"^\d{4}-\d{2}$")
    payment_account_id: str
    pay_day: int = Field(default=27, ge=1, le=31)
    include_collection: bool = True


@router.post("/housings/{hid}/journals", status_code=201)
async def create_housing_journals(hid: str, body: HousingJournalIn, db: Database = Depends(get_db)):
    """FR-42: 家賃の支払と役員からの徴収（振込の場合）の仕訳を作る。給与天引きの場合は給与の仕訳で処理する。"""
    h = await _get(db, hid)
    pa = await masters.get_payment_account(db, body.payment_account_id)
    if not pa:
        raise not_found("口座・支払手段")
    y, m = int(body.year_month[:4]), int(body.year_month[5:])
    d = date(y, m, min(body.pay_day, calendar.monthrange(y, m)[1]))
    total = h["monthly_rent"] + h["monthly_common_fee"]
    created, warnings = [], []
    eid, w = await svc.create_entry(
        db, transaction_date=d, description=f"社宅家賃 {body.year_month}分 {h['address']}",
        counterparty_id=h["landlord_id"], payment_account_id=pa["id"],
        lines=[LineIn("debit", RENT_ACCOUNT, total, RESIDENTIAL_RENT_TAX_CODE),
               LineIn("credit", pa["linked_account_code"], total, "NT")])
    created.append(eid)
    warnings.extend(w)
    if body.include_collection and h["collection_method"] == "transfer" and h["collection_amount"] > 0:
        eid2, w2 = await svc.create_entry(
            db, transaction_date=d, description=f"社宅家賃の役員負担分 {body.year_month}分",
            payment_account_id=pa["id"], lines=[],
            # 相手は役員（取引先マスタ外）のため、明細を直接組み立てる
            prebuilt=[BuiltLine(1, "debit", pa["linked_account_code"], h["collection_amount"], "NT", 0, None),
                      BuiltLine(2, "credit", RENT_ACCOUNT, h["collection_amount"], RESIDENTIAL_RENT_TAX_CODE, 0, None)])
        created.append(eid2)
        warnings.extend(w2)
    imputed = await _imputed(db, h)
    warnings.extend(imputed["warnings"])
    return {"created": created, "warnings": warnings}


class HousingAutomateIn(BaseModel):
    payment_account_id: str
    pay_day: int = Field(default=27, ge=1, le=31)
    start_month: str = Field(pattern=r"^\d{4}-\d{2}$")


@router.post("/housings/{hid}/automate", status_code=201)
async def automate_housing(hid: str, body: HousingAutomateIn, db: Database = Depends(get_db)):
    """家賃の引落し（と、振込で受け取る場合は役員からの徴収）を、毎月自動で計上する定型仕訳として登録する。"""
    from routers.imports import TemplateIn, TemplateLine, create_template_record

    h = await _get(db, hid)
    pa = await masters.get_payment_account(db, body.payment_account_id)
    if not pa:
        raise not_found("口座・支払手段")
    end_month = h["contract_end"][:7]
    total = h["monthly_rent"] + h["monthly_common_fee"]
    ids = [await create_template_record(db, TemplateIn(
        name=f"社宅家賃（{h['address']}）", day_of_month=body.pay_day, description=f"社宅家賃 {h['address']}",
        counterparty_id=h["landlord_id"], payment_account_id=pa["id"], start_month=body.start_month, end_month=end_month,
        lines=[TemplateLine(side="debit", account_code=RENT_ACCOUNT, amount=total, tax_code=RESIDENTIAL_RENT_TAX_CODE),
               TemplateLine(side="credit", account_code=pa["linked_account_code"], amount=total, tax_code="NT")]))]
    if h["collection_method"] == "transfer" and h["collection_amount"] > 0:
        ids.append(await create_template_record(db, TemplateIn(
            name=f"社宅家賃の役員負担分（{h['address']}）", day_of_month=body.pay_day, description="社宅家賃の役員負担分",
            counterparty_id=h["landlord_id"], payment_account_id=pa["id"], start_month=body.start_month, end_month=end_month,
            lines=[TemplateLine(side="debit", account_code=pa["linked_account_code"], amount=h["collection_amount"], tax_code="NT"),
                   TemplateLine(side="credit", account_code=RENT_ACCOUNT, amount=h["collection_amount"], tax_code=RESIDENTIAL_RENT_TAX_CODE)])))
    return {"template_ids": ids}
