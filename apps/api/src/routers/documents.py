"""書類管理。契約書・登記・口座開設・届出などの会社の書類を保管し、種類やキーワードで探せるようにする。"""

from __future__ import annotations

from datetime import date
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

from common import AppError, get_db, get_evidence_storage, new_id, not_found, now_iso
from db import Database
from domain.rules.br061_electronic_records import sha256_hex
from repositories.base import insert, update
from storage import ObjectStorage

router = APIRouter(prefix="/api/v1")

CATEGORIES = ["契約書", "登記・定款", "口座開設", "税務の届出", "社会保険・労務", "保険", "社内の決定（議事録など）", "その他"]
MAX_BYTES = 30 * 1024 * 1024
BLOCKED_EXT = {"exe", "bat", "cmd", "com", "msi", "ps1", "sh", "js", "vbs", "scr", "dll"}


def _key(doc_id: str, filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
    if not ext.isalnum() or len(ext) > 8:
        ext = "bin"
    return f"documents/{date.today().year}/{doc_id}.{ext}"


@router.get("/documents/categories")
async def categories():
    return {"items": CATEGORIES}


@router.get("/documents")
async def list_documents(
    category: str | None = None,
    keyword: str | None = None,
    from_: str | None = Query(default=None, alias="from"),
    to: str | None = None,
    include_archived: bool = False,
    db: Database = Depends(get_db),
):
    where, params = ["1 = 1"], []
    if not include_archived:
        where.append("archived_at IS NULL")
    if category:
        where.append("category = ?")
        params.append(category)
    if keyword:
        where.append("(title LIKE ? OR party LIKE ? OR notes LIKE ? OR original_filename LIKE ?)")
        params.extend([f"%{keyword}%"] * 4)
    if from_:
        where.append("document_date >= ?")
        params.append(from_)
    if to:
        where.append("document_date <= ?")
        params.append(to)
    rows = await db.all(
        f"SELECT * FROM documents WHERE {' AND '.join(where)} ORDER BY COALESCE(document_date, substr(created_at, 1, 10)) DESC, created_at DESC",
        params)
    return {"items": rows}


@router.post("/documents", status_code=201)
async def upload_document(
    file: UploadFile = File(...),
    title: str = Form(...),
    category: str = Form(...),
    party: str | None = Form(default=None),
    document_date: date | None = Form(default=None),
    expiry_date: date | None = Form(default=None),
    notes: str | None = Form(default=None),
    db: Database = Depends(get_db),
    storage: ObjectStorage = Depends(get_evidence_storage),
):
    data = await file.read()
    filename = file.filename or "file"
    if not data:
        raise AppError(422, "empty_file", "ファイルが空です")
    if len(data) > MAX_BYTES:
        raise AppError(422, "too_large", "ファイルサイズは30MBまでです")
    if filename.rsplit(".", 1)[-1].lower() in BLOCKED_EXT:
        raise AppError(422, "blocked_type", "この種類のファイルは保存できません")
    if not title.strip():
        raise AppError(422, "title_required", "書類名を入力してください")
    doc_id = new_id()
    key = _key(doc_id, filename)
    await storage.put(key, data, file.content_type or "application/octet-stream")
    now = now_iso()
    await insert(db, "documents", {
        "id": doc_id, "title": title.strip(), "category": category, "party": party or None,
        "document_date": document_date.isoformat() if document_date else None,
        "expiry_date": expiry_date.isoformat() if expiry_date else None,
        "notes": notes or None, "r2_key": key, "original_filename": filename,
        "content_type": file.content_type or "application/octet-stream", "size_bytes": len(data),
        "sha256": sha256_hex(data), "archived_at": None, "created_at": now, "updated_at": now,
    })
    return await db.first("SELECT * FROM documents WHERE id = ?", [doc_id])


class DocumentPatch(BaseModel):
    title: str | None = None
    category: str | None = None
    party: str | None = None
    document_date: date | None = None
    expiry_date: date | None = None
    notes: str | None = None
    archived: bool | None = None


@router.patch("/documents/{doc_id}")
async def patch_document(doc_id: str, body: DocumentPatch, db: Database = Depends(get_db)):
    if not await db.first("SELECT id FROM documents WHERE id = ?", [doc_id]):
        raise not_found("書類")
    data = body.model_dump(mode="json", exclude_unset=True)
    archived = data.pop("archived", None)
    if archived is not None:
        data["archived_at"] = now_iso() if archived else None
    data["updated_at"] = now_iso()
    await update(db, "documents", "id", doc_id, data)
    return await db.first("SELECT * FROM documents WHERE id = ?", [doc_id])


@router.get("/documents/{doc_id}/file")
async def download_document(doc_id: str, download: bool = False, db: Database = Depends(get_db),
                            storage: ObjectStorage = Depends(get_evidence_storage)):
    d = await db.first("SELECT * FROM documents WHERE id = ?", [doc_id])
    if not d:
        raise not_found("書類")
    data = await storage.get(d["r2_key"])
    if data is None:
        raise AppError(404, "file_missing", "ファイルが見つかりません")
    disposition = "attachment" if download else "inline"
    return Response(content=data, media_type=d["content_type"],
                    headers={"Content-Disposition": f"{disposition}; filename*=UTF-8''{quote(d['original_filename'])}"})
