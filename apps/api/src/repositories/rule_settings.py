"""設定値テーブル（BR-000）。"""

from __future__ import annotations

from datetime import date
from typing import Any

from db import Database
from domain.settings import SettingRow, pick_value, schedule_of
from repositories.base import loads


async def list_all(db: Database) -> list[dict[str, Any]]:
    return await db.all("SELECT * FROM rule_settings ORDER BY key, effective_from")


async def rows_for(db: Database, key: str) -> list[SettingRow]:
    rows = await db.all("SELECT * FROM rule_settings WHERE key = ? ORDER BY effective_from", [key])
    return [
        SettingRow(
            key=r["key"],
            value=loads(r["value"]),
            effective_from=date.fromisoformat(r["effective_from"]),
            effective_to=date.fromisoformat(r["effective_to"]) if r["effective_to"] else None,
        )
        for r in rows
    ]


async def value_on(db: Database, key: str, on: date, default: Any = None) -> Any:
    """判定日 on に有効な設定値を返す。無ければ default。"""
    return pick_value(await rows_for(db, key), on, default)


async def schedule(db: Database, key: str) -> list[tuple[date, date | None, Any]]:
    return schedule_of(await rows_for(db, key))


async def upsert(db: Database, key: str, value_json: str, effective_from: str, effective_to: str | None, note: str | None) -> None:
    await db.run(
        """INSERT INTO rule_settings (key, value, effective_from, effective_to, note) VALUES (?, ?, ?, ?, ?)
           ON CONFLICT (key, effective_from) DO UPDATE SET value = excluded.value,
             effective_to = excluded.effective_to, note = excluded.note""",
        [key, value_json, effective_from, effective_to, note],
    )
