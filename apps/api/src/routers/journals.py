"""仕訳（FR-03, FR-10〜12, FR-15, FR-17, FR-60, FR-70, NFR-02）。"""

from __future__ import annotations

from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from common import get_db, not_found
from db import Database
from domain.journal import LineIn
from repositories import journals as repo
from services import journals as svc

router = APIRouter(prefix="/api/v1")


class LineModel(BaseModel):
    side: Literal["debit", "credit"]
    account_code: str
    amount: int = Field(ge=0)
    tax_code: str | None = None
    tax_amount: int | None = Field(default=None, ge=0)


class EntertainmentDetail(BaseModel):
    participants: str = ""
    headcount: int = Field(default=0, ge=0)
    is_food_and_drink: bool = False
    venue: str | None = None
    is_internal_only: bool = False


class JournalIn(BaseModel):
    transaction_date: date
    description: str = Field(min_length=1)
    counterparty_id: str | None = None
    payment_account_id: str | None = None
    lines: list[LineModel] = Field(min_length=2)
    entertainment_detail: EntertainmentDetail | None = None
    attachment_ids: list[str] = []
    # manual: 通常の手入力 / opening_balance: 開始残高（FR-03） / closing_adjustment: 決算整理（FR-60）
    source: Literal["manual", "opening_balance", "closing_adjustment"] = "manual"


class VoidIn(BaseModel):
    reversal_date: date | None = None


class LinkAttachmentIn(BaseModel):
    attachment_id: str


@router.get("/journals")
async def search_journals(
    from_: str | None = Query(default=None, alias="from"),
    to: str | None = None,
    amount_min: int | None = None,
    amount_max: int | None = None,
    counterparty: str | None = None,
    account: str | None = None,
    period_id: str | None = None,
    source: str | None = None,
    keyword: str | None = None,
    debit_category: str | None = None,
    include_voided: bool = False,
    db: Database = Depends(get_db),
):
    """FR-70: 取引年月日（範囲）・金額（範囲）・取引先などを組み合わせて検索する。"""
    items = await repo.search_entries(db, {
        "from": from_, "to": to, "amount_min": amount_min, "amount_max": amount_max,
        "counterparty": counterparty, "account": account, "period_id": period_id,
        "source": source, "keyword": keyword, "include_voided": include_voided,
        "debit_category": debit_category,
    })
    return {"items": items}


@router.get("/journals/{entry_id}")
async def get_journal(entry_id: str, db: Database = Depends(get_db)):
    e = await repo.get_entry(db, entry_id)
    if not e:
        raise not_found("仕訳")
    e["history"] = await repo.audit_history(db, "journal_entries", entry_id)
    return e


@router.post("/journals", status_code=201)
async def create_journal(body: JournalIn, db: Database = Depends(get_db)):
    entry_id, warnings = await svc.create_entry(
        db,
        transaction_date=body.transaction_date,
        description=body.description,
        lines=[LineIn(**ln.model_dump()) for ln in body.lines],
        source=body.source,
        counterparty_id=body.counterparty_id or None,
        payment_account_id=body.payment_account_id or None,
        entertainment_detail=body.entertainment_detail.model_dump() if body.entertainment_detail else None,
        attachment_ids=body.attachment_ids,
    )
    return {"entry": await repo.get_entry(db, entry_id), "warnings": warnings}


@router.post("/journals/{entry_id}/void")
async def void_journal(entry_id: str, body: VoidIn | None = None, db: Database = Depends(get_db)):
    return await svc.void_entry(db, entry_id, body.reversal_date if body else None)


@router.post("/journals/{entry_id}/attachments")
async def link_attachment(entry_id: str, body: LinkAttachmentIn, db: Database = Depends(get_db)):
    if not await repo.get_entry(db, entry_id):
        raise not_found("仕訳")
    if not await repo.get_attachment(db, body.attachment_id):
        raise not_found("証憑")
    await db.run("INSERT OR IGNORE INTO journal_attachments (entry_id, attachment_id) VALUES (?, ?)",
                 [entry_id, body.attachment_id])
    return {"ok": True}
