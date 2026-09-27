"""固定資産台帳と減価償却（FR-50〜52, BR-051, DM-16）。"""

from __future__ import annotations

from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from common import AppError, get_db, new_id, not_found, now_iso
from db import Database
from domain.assets import depreciation_for_period, months_between
from domain.journal import BuiltLine, LineIn
from domain.rules.br010_sme import is_sme
from domain.rules.br051_depreciation_options import depreciation_options, sme_annual_cap, sme_cap_warning
from repositories import masters, rule_settings
from repositories.base import insert, update
from services import journals as svc

router = APIRouter(prefix="/api/v1")

DEPRECIATION_EXPENSE = "620"
Method = Literal["straight_line", "declining_balance", "immediate_small", "lump_sum_3y", "small_sme_special"]


async def _options(db: Database, cost: int, acquisition_date: date) -> list[str]:
    company = await masters.get_company(db)
    capital_limit = int(await rule_settings.value_on(db, "sme_capital_limit", acquisition_date, 100_000_000))
    sme_blue = bool(company and company["blue_return_approved"] and is_sme(company["capital_amount"], capital_limit))
    sme_limit = await rule_settings.value_on(db, "small_asset_sme_limit", acquisition_date)
    return depreciation_options(
        cost,
        immediate_limit=int(await rule_settings.value_on(db, "small_asset_immediate_limit", acquisition_date, 100_000)),
        lump_sum_limit=int(await rule_settings.value_on(db, "small_asset_lump_sum_limit", acquisition_date, 200_000)),
        sme_limit=int(sme_limit) if sme_limit is not None else None,
        is_sme_blue=sme_blue,
    )


async def _sme_cap_status(db: Database, period: dict) -> dict:
    """FR-52: 事業年度内に取得した少額減価償却資産の特例の合計と上限。"""
    row = await db.first(
        """SELECT COALESCE(SUM(acquisition_cost), 0) AS total FROM fixed_assets
           WHERE depreciation_method = 'small_sme_special' AND acquisition_date BETWEEN ? AND ?""",
        [period["start_date"], period["end_date"]])
    start, end = date.fromisoformat(period["start_date"]), date.fromisoformat(period["end_date"])
    cap = sme_annual_cap(int(await rule_settings.value_on(db, "small_asset_sme_annual_cap", end, 3_000_000)),
                         months_between(start, end))
    w = sme_cap_warning(row["total"], cap)
    return {"period_id": period["id"], "total": row["total"], "cap": cap, "warnings": [w] if w else []}


@router.get("/fixed-assets/options")
async def options(acquisition_cost: int, acquisition_date: date, db: Database = Depends(get_db)):
    """FR-51 / BR-051: 取得価額と取得日から選べる償却方法を返す。"""
    return {"options": await _options(db, acquisition_cost, acquisition_date)}


@router.get("/fixed-assets")
async def list_assets(db: Database = Depends(get_db)):
    rows = await db.all(
        """SELECT fa.*, a.name AS account_name,
                  COALESCE((SELECT SUM(amount) FROM depreciation_runs dr WHERE dr.asset_id = fa.id), 0) AS accumulated_depreciation
           FROM fixed_assets fa JOIN accounts a ON a.code = fa.account_code ORDER BY fa.acquisition_date""")
    for r in rows:
        r["book_value"] = r["acquisition_cost"] - r["accumulated_depreciation"]
    return {"items": rows}


class AssetIn(BaseModel):
    name: str = Field(min_length=1)
    asset_category: str = Field(min_length=1)
    account_code: str = "170"
    acquisition_date: date
    service_start_date: date
    acquisition_cost: int = Field(gt=0)
    useful_life_years: int = Field(ge=1, le=100)
    depreciation_method: Method
    subject_to_depreciable_asset_return: bool = True
    # 取得の仕訳もあわせて作る場合に指定する
    payment_account_id: str | None = None
    counterparty_id: str | None = None


class AssetPatch(BaseModel):
    name: str | None = None
    disposal_date: date | None = None
    subject_to_depreciable_asset_return: bool | None = None


@router.post("/fixed-assets", status_code=201)
async def create_asset(body: AssetIn, db: Database = Depends(get_db)):
    if body.service_start_date < body.acquisition_date:
        raise AppError(422, "invalid_date", "事業に使い始めた日は取得日以後にしてください")
    if not await masters.get_account(db, body.account_code):
        raise AppError(422, "invalid_account", "勘定科目が存在しません")
    allowed = await _options(db, body.acquisition_cost, body.acquisition_date)
    if body.depreciation_method not in allowed:
        raise AppError(422, "method_not_allowed",
                       f"この取得価額・取得日では選べない償却方法です（選択可: {', '.join(allowed)}）", "BR-051")
    warnings = []
    if body.account_code == "180" and body.subject_to_depreciable_asset_return:
        warnings.append({"rule_id": "DM-16", "message": "ソフトウェアなどの無形資産は償却資産申告の対象外です"})
    if body.account_code == "180" and body.depreciation_method == "declining_balance":
        raise AppError(422, "method_not_allowed", "ソフトウェアは定額法で償却します", "BR-051")

    aid = new_id()
    now = now_iso()
    data = body.model_dump(mode="json", exclude={"payment_account_id", "counterparty_id"})
    if body.account_code == "180":
        data["subject_to_depreciable_asset_return"] = False
    await insert(db, "fixed_assets", {"id": aid, **data, "disposal_date": None, "created_at": now, "updated_at": now})

    if body.payment_account_id:
        pa = await masters.get_payment_account(db, body.payment_account_id)
        if not pa:
            raise not_found("口座・支払手段")
        acct = "190" if body.depreciation_method == "lump_sum_3y" else body.account_code
        _, w = await svc.create_entry(
            db, transaction_date=body.acquisition_date, description=f"固定資産の取得 {body.name}",
            counterparty_id=body.counterparty_id or None, payment_account_id=pa["id"],
            lines=[LineIn("debit", acct, body.acquisition_cost), LineIn("credit", pa["linked_account_code"], body.acquisition_cost, "NT")])
        warnings.extend(w)

    period = await masters.period_for_date(db, body.acquisition_date.isoformat())
    if period and body.depreciation_method == "small_sme_special":
        warnings.extend((await _sme_cap_status(db, period))["warnings"])
    return {"asset": await db.first("SELECT * FROM fixed_assets WHERE id = ?", [aid]), "warnings": warnings}


@router.patch("/fixed-assets/{aid}")
async def patch_asset(aid: str, body: AssetPatch, db: Database = Depends(get_db)):
    if not await db.first("SELECT id FROM fixed_assets WHERE id = ?", [aid]):
        raise not_found("固定資産")
    data = body.model_dump(mode="json", exclude_none=True)
    data["updated_at"] = now_iso()
    await update(db, "fixed_assets", "id", aid, data)
    return await db.first("SELECT * FROM fixed_assets WHERE id = ?", [aid])


async def _plan(db: Database, period: dict) -> list[dict]:
    start, end = date.fromisoformat(period["start_date"]), date.fromisoformat(period["end_date"])
    assets = await db.all(
        """SELECT fa.*,
                  COALESCE((SELECT SUM(amount) FROM depreciation_runs dr WHERE dr.asset_id = fa.id), 0) AS accumulated,
                  (SELECT 1 FROM depreciation_runs dr WHERE dr.asset_id = fa.id AND dr.fiscal_period_id = ?) AS done
           FROM fixed_assets fa ORDER BY fa.acquisition_date""", [period["id"]])
    plan = []
    for a in assets:
        amount = depreciation_for_period(
            method=a["depreciation_method"], cost=a["acquisition_cost"], useful_life_years=a["useful_life_years"],
            service_start=date.fromisoformat(a["service_start_date"]),
            disposal_date=date.fromisoformat(a["disposal_date"]) if a["disposal_date"] else None,
            period_start=start, period_end=end, accumulated_before=a["accumulated"])
        plan.append({"asset_id": a["id"], "name": a["name"], "account_code": "190" if a["depreciation_method"] == "lump_sum_3y" else a["account_code"],
                     "method": a["depreciation_method"], "amount": amount, "already_booked": bool(a["done"]),
                     "book_value_before": a["acquisition_cost"] - a["accumulated"]})
    return plan


@router.get("/fiscal-periods/{period_id}/depreciation")
async def preview_depreciation(period_id: str, db: Database = Depends(get_db)):
    period = await masters.get_period(db, period_id)
    if not period:
        raise not_found("会計期間")
    return {"items": await _plan(db, period), "sme_cap": await _sme_cap_status(db, period)}


@router.post("/fiscal-periods/{period_id}/depreciation")
async def book_depreciation(period_id: str, db: Database = Depends(get_db)):
    """FR-50: 期末に減価償却費の仕訳（直接法）を作る。計上済みの資産は飛ばす。"""
    period = await masters.get_period(db, period_id)
    if not period:
        raise not_found("会計期間")
    targets = [p for p in await _plan(db, period) if p["amount"] > 0 and not p["already_booked"]]
    if not targets:
        return {"entry_id": None, "items": [], "message": "計上する減価償却費はありません"}
    lines: list[BuiltLine] = []
    total = sum(t["amount"] for t in targets)
    lines.append(BuiltLine(1, "debit", DEPRECIATION_EXPENSE, total, "NT", 0, None))
    by_account: dict[str, int] = {}
    for t in targets:
        by_account[t["account_code"]] = by_account.get(t["account_code"], 0) + t["amount"]
    for i, (acct, amt) in enumerate(sorted(by_account.items()), start=2):
        lines.append(BuiltLine(i, "credit", acct, amt, "NT", 0, None))
    now = now_iso()
    end = date.fromisoformat(period["end_date"])

    def extra(entry_id: str):
        return [("INSERT INTO depreciation_runs (fiscal_period_id, asset_id, amount, journal_entry_id, created_at) VALUES (?, ?, ?, ?, ?)",
                 [period_id, t["asset_id"], t["amount"], entry_id, now]) for t in targets]

    entry_id, _ = await svc.create_entry(db, transaction_date=end, description=f"減価償却費（{period['start_date']}〜{period['end_date']}）",
                                         lines=[], prebuilt=lines, source="closing_adjustment", extra_statements=extra)
    return {"entry_id": entry_id, "items": targets}
