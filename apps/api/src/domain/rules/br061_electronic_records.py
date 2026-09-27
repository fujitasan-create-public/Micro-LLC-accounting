"""BR-061 電子取引データの保存。検索項目（取引年月日・金額・取引先）の検証とハッシュ値。"""

from __future__ import annotations

import hashlib

MAX_FILE_BYTES = 20 * 1024 * 1024  # 設計書 6章
ALLOWED_TYPES = {
    "application/pdf", "image/jpeg", "image/png", "image/gif", "image/webp", "image/heic",
    "text/csv", "text/plain", "application/xml", "text/xml", "application/json",
}


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def validate_upload(size: int, content_type: str, amount: int | None, counterparty_name: str | None,
                    transaction_date: str | None) -> list[str]:
    errors = []
    if size <= 0:
        errors.append("ファイルが空です")
    if size > MAX_FILE_BYTES:
        errors.append("ファイルサイズは20MBまでです")
    if content_type not in ALLOWED_TYPES:
        errors.append(f"このファイル形式は保存できません（{content_type}）")
    if not transaction_date:
        errors.append("取引年月日を入力してください")
    if amount is None:
        errors.append("取引金額を入力してください")
    if not counterparty_name:
        errors.append("取引先を入力してください")
    return errors


def r2_key(attachment_id: str, transaction_date: str, filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
    if not ext.isalnum() or len(ext) > 8:
        ext = "bin"
    return f"evidence/{transaction_date[:4]}/{transaction_date[5:7]}/{attachment_id}.{ext}"
