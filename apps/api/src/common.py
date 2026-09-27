"""API 共通: エラー形式、警告、ID、日時、依存性注入。"""

from __future__ import annotations

import os
import random
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from db import Database, DatabaseError, D1Database
from storage import ObjectStorage, R2Storage

JST = timezone(timedelta(hours=9))


# ---------------------------------------------------------------------------
# エラーと警告（設計書 7.1）
# ---------------------------------------------------------------------------


class AppError(Exception):
    def __init__(self, status: int, code: str, message: str, rule_id: str | None = None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.rule_id = rule_id


def error_response(status: int, code: str, message: str, rule_id: str | None = None) -> JSONResponse:
    body: dict[str, Any] = {"code": code, "message": message}
    if rule_id:
        body["rule_id"] = rule_id
    return JSONResponse(status_code=status, content={"error": body})


def not_found(what: str) -> AppError:
    return AppError(404, "not_found", f"{what}が見つかりません")


def db_error_to_app_error(e: DatabaseError) -> AppError:
    msg = str(e)
    if "fiscal period is closed" in msg:
        return AppError(409, "period_closed", "締め済みの会計期間の仕訳は変更できません。当期の修正仕訳で訂正してください", "NFR-03")
    if "physical delete is not allowed" in msg:
        return AppError(409, "delete_not_allowed", "物理削除はできません。取消しを使ってください", "NFR-01")
    if "immutable" in msg:
        return AppError(409, "immutable", "証憑ファイルは変更できません", "BR-061")
    if "UNIQUE" in msg:
        return AppError(409, "duplicate", "同じキーのデータが既に存在します")
    if "FOREIGN KEY" in msg:
        return AppError(422, "invalid_reference", "参照先のデータが存在しません")
    return AppError(500, "database_error", msg)


@dataclass
class Warnings:
    items: list[dict[str, str]] = field(default_factory=list)

    def add(self, rule_id: str, message: str) -> None:
        self.items.append({"rule_id": rule_id, "message": message})

    def extend(self, items: list[dict[str, str]]) -> None:
        self.items.extend(items)


# ---------------------------------------------------------------------------
# ID・日時
# ---------------------------------------------------------------------------

_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def new_id() -> str:
    """ULID（26文字）。"""
    ts = int(time.time() * 1000)
    rnd = int.from_bytes(os.urandom(10), "big") if hasattr(os, "urandom") else random.getrandbits(80)
    value = (ts << 80) | rnd
    chars = []
    for _ in range(26):
        chars.append(_CROCKFORD[value & 31])
        value >>= 5
    return "".join(reversed(chars))


def now_iso() -> str:
    return datetime.now(JST).isoformat(timespec="seconds")


def today() -> date:
    return datetime.now(JST).date()


def parse_date(s: str | None) -> date | None:
    return date.fromisoformat(s) if s else None


# ---------------------------------------------------------------------------
# 依存性注入: Workers では request.scope["env"]、ローカルでは app.state
# ---------------------------------------------------------------------------


def get_db(request: Request) -> Database:
    env = request.scope.get("env")
    if env is not None:
        return D1Database(env.DB)
    return request.app.state.db


def get_evidence_storage(request: Request) -> ObjectStorage:
    env = request.scope.get("env")
    if env is not None:
        return R2Storage(env.EVIDENCE)
    return request.app.state.evidence


def get_backup_storage(request: Request) -> ObjectStorage:
    env = request.scope.get("env")
    if env is not None:
        return R2Storage(env.BACKUP)
    return request.app.state.backup
