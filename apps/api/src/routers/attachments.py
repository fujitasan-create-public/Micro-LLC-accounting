"""証憑（FR-16, FR-70, BR-061, 設計書 6章）。"""

from __future__ import annotations

from datetime import date
from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from common import AppError, get_db, get_evidence_storage, new_id, not_found, now_iso
from db import Database
from domain.rules.br061_electronic_records import r2_key, sha256_hex, validate_upload
from repositories import journals as repo
from repositories.base import insert, update
from storage import ObjectStorage

router = APIRouter(prefix="/api/v1")


@router.post("/attachments", status_code=201)
async def upload_attachment(
    file: UploadFile = File(...),
    received_date: date = Form(...),
    transaction_date: date = Form(...),
    amount: int = Form(...),
    counterparty_name: str = Form(...),
    receipt_channel: Literal["electronic", "paper_scanned", "paper"] = Form(...),
    entry_id: str | None = Form(default=None),
    db: Database = Depends(get_db),
    storage: ObjectStorage = Depends(get_evidence_storage),
):
    data = await file.read()
    content_type = file.content_type or "application/octet-stream"
    errors = validate_upload(len(data), content_type, amount, counterparty_name, transaction_date.isoformat())
    if errors:
        raise AppError(422, "invalid_attachment", "／".join(errors), "BR-061")
    if entry_id and not await repo.get_entry(db, entry_id):
        raise not_found("仕訳")

    att_id = new_id()
    key = r2_key(att_id, transaction_date.isoformat(), file.filename or "file")
    digest = sha256_hex(data)
    # 先に R2 に保存し、成功してから行を追加する（設計書 6章）
    await storage.put(key, data, content_type)
    now = now_iso()
    await insert(db, "attachments", {
        "id": att_id, "r2_key": key, "original_filename": file.filename or "file", "sha256": digest,
        "content_type": content_type, "size_bytes": len(data), "received_date": received_date.isoformat(),
        "transaction_date": transaction_date.isoformat(), "amount": amount,
        "counterparty_name": counterparty_name, "receipt_channel": receipt_channel,
        "voided_at": None, "created_at": now, "updated_at": now,
    })
    if entry_id:
        await db.run("INSERT OR IGNORE INTO journal_attachments (entry_id, attachment_id) VALUES (?, ?)", [entry_id, att_id])
    warnings = []
    if receipt_channel == "paper":
        warnings.append({"rule_id": "BR-061", "message": "紙で受け取った証憑です。原本も保存してください"})
    return {"attachment": await repo.get_attachment(db, att_id), "warnings": warnings}


@router.get("/attachments")
async def search_attachments(
    from_: str | None = Query(default=None, alias="from"),
    to: str | None = None,
    amount_min: int | None = None,
    amount_max: int | None = None,
    counterparty: str | None = None,
    include_voided: bool = False,
    db: Database = Depends(get_db),
):
    """FR-70: 取引年月日・金額・取引先の組み合わせ検索。"""
    items = await repo.search_attachments(db, {
        "from": from_, "to": to, "amount_min": amount_min, "amount_max": amount_max,
        "counterparty": counterparty, "include_voided": include_voided,
    })
    return {"items": items}


@router.get("/attachments/{att_id}")
async def get_attachment(att_id: str, db: Database = Depends(get_db)):
    a = await repo.get_attachment(db, att_id)
    if not a:
        raise not_found("証憑")
    a["history"] = await repo.audit_history(db, "attachments", att_id)
    return a


@router.get("/attachments/{att_id}/file")
async def download_attachment(att_id: str, db: Database = Depends(get_db),
                              storage: ObjectStorage = Depends(get_evidence_storage)):
    a = await repo.get_attachment(db, att_id)
    if not a:
        raise not_found("証憑")
    data = await storage.get(a["r2_key"])
    if data is None:
        raise AppError(404, "file_missing", "証憑ファイルが見つかりません")
    if sha256_hex(data) != a["sha256"]:
        raise AppError(409, "hash_mismatch", "証憑ファイルのハッシュ値が一致しません（改ざんの可能性）", "BR-061")
    filename = quote(a["original_filename"])
    return Response(content=data, media_type=a["content_type"],
                    headers={"Content-Disposition": f"inline; filename*=UTF-8''{filename}"})


class AttachmentPatch(BaseModel):
    received_date: date | None = None
    transaction_date: date | None = None
    amount: int | None = Field(default=None, ge=0)
    counterparty_name: str | None = None
    receipt_channel: Literal["electronic", "paper_scanned", "paper"] | None = None


@router.patch("/attachments/{att_id}")
async def patch_attachment(att_id: str, body: AttachmentPatch, db: Database = Depends(get_db)):
    """検索項目の訂正。変更前の値は audit_log に残る（NFR-02）。ファイル自体は変更できない。"""
    if not await repo.get_attachment(db, att_id):
        raise not_found("証憑")
    data = {k: (v.isoformat() if isinstance(v, date) else v) for k, v in body.model_dump(exclude_none=True).items()}
    data["updated_at"] = now_iso()
    await update(db, "attachments", "id", att_id, data)
    return await repo.get_attachment(db, att_id)


@router.post("/attachments/{att_id}/void")
async def void_attachment(att_id: str, db: Database = Depends(get_db)):
    """論理削除（NFR-01: 保存期間内は物理削除しない。ファイルは R2 に残る）。"""
    if not await repo.get_attachment(db, att_id):
        raise not_found("証憑")
    now = now_iso()
    await db.run("UPDATE attachments SET voided_at = ?, updated_at = ? WHERE id = ? AND voided_at IS NULL", [now, now, att_id])
    return {"ok": True}
