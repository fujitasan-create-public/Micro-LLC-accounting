"""単純な INSERT / UPDATE の SQL 生成。テーブル名・列名はコード内の定数だけを渡すこと。"""

from __future__ import annotations

import json
from typing import Any

from db import Database, Statement


def _norm(v: Any) -> Any:
    if isinstance(v, bool):
        return 1 if v else 0
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False)
    return v


def insert_stmt(table: str, data: dict[str, Any]) -> Statement:
    cols = list(data.keys())
    sql = f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join('?' for _ in cols)})"
    return sql, [_norm(data[c]) for c in cols]


def update_stmt(table: str, pk_col: str, pk: Any, data: dict[str, Any]) -> Statement:
    cols = list(data.keys())
    sql = f"UPDATE {table} SET {', '.join(f'{c} = ?' for c in cols)} WHERE {pk_col} = ?"
    return sql, [_norm(data[c]) for c in cols] + [pk]


async def insert(db: Database, table: str, data: dict[str, Any]) -> None:
    sql, params = insert_stmt(table, data)
    await db.run(sql, params)


async def update(db: Database, table: str, pk_col: str, pk: Any, data: dict[str, Any]) -> None:
    if not data:
        return
    sql, params = update_stmt(table, pk_col, pk, data)
    await db.run(sql, params)


def loads(value: str | None, default: Any = None) -> Any:
    if value is None or value == "":
        return default
    return json.loads(value)
