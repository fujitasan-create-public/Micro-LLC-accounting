"""データベース接続の抽象化。

- Workers 上では D1 バインディング（env.DB）を使う。
- ローカル（CPython + uvicorn）では標準ライブラリの sqlite3 を使う。

SQL を書くのは repositories/ だけとし、repositories/ はこのモジュールの Database だけに依存する（設計書 2章）。
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Protocol

Statement = tuple[str, list[Any]]


class DatabaseError(Exception):
    """制約違反・トリガーによる拒否など。message にトリガーのメッセージが入る。"""


class Database(Protocol):
    async def all(self, sql: str, params: list[Any] | None = None) -> list[dict[str, Any]]: ...

    async def first(self, sql: str, params: list[Any] | None = None) -> dict[str, Any] | None: ...

    async def run(self, sql: str, params: list[Any] | None = None) -> None: ...

    async def batch(self, statements: list[Statement]) -> None:
        """複数の文を1トランザクションで実行する（D1 の batch() に相当）。"""
        ...


# ---------------------------------------------------------------------------
# ローカル: sqlite3
# ---------------------------------------------------------------------------


class SqliteDatabase:
    def __init__(self, path: str | Path):
        import sqlite3  # Pyodide では使わないため遅延 import

        self._sqlite = sqlite3
        self._path = str(path)
        self._conn = sqlite3.connect(self._path, check_same_thread=False, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._lock = threading.Lock()

    def _exec(self, sql: str, params: list[Any] | None) -> Any:
        try:
            return self._conn.execute(sql, params or [])
        except self._sqlite.DatabaseError as e:  # IntegrityError, OperationalError（RAISE(ABORT)）など
            raise DatabaseError(str(e)) from e

    async def all(self, sql: str, params: list[Any] | None = None) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(r) for r in self._exec(sql, params).fetchall()]

    async def first(self, sql: str, params: list[Any] | None = None) -> dict[str, Any] | None:
        with self._lock:
            row = self._exec(sql, params).fetchone()
            return dict(row) if row else None

    async def run(self, sql: str, params: list[Any] | None = None) -> None:
        with self._lock:
            self._exec(sql, params)

    async def batch(self, statements: list[Statement]) -> None:
        with self._lock:
            try:
                self._conn.execute("BEGIN")
                for sql, params in statements:
                    self._conn.execute(sql, params or [])
                self._conn.execute("COMMIT")
            except self._sqlite.DatabaseError as e:
                self._conn.execute("ROLLBACK")
                raise DatabaseError(str(e)) from e

    def apply_sql_files(self, directories: list[Path]) -> list[str]:
        """migrations/ と seed/ の未適用ファイルを順に適用する（ローカル専用）。"""
        applied: list[str] = []
        with self._lock:
            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS _local_migrations (name TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
            )
            done = {r[0] for r in self._conn.execute("SELECT name FROM _local_migrations")}
            for d in directories:
                for f in sorted(d.glob("*.sql")):
                    name = f"{d.name}/{f.name}"
                    if name in done:
                        continue
                    script = f.read_text(encoding="utf-8")
                    self._conn.executescript("BEGIN;\n" + script + "\nCOMMIT;")
                    self._conn.execute(
                        "INSERT INTO _local_migrations (name, applied_at) VALUES (?, datetime('now'))", [name]
                    )
                    applied.append(name)
        return applied


# ---------------------------------------------------------------------------
# Workers: D1
# ---------------------------------------------------------------------------


def _to_js_param(v: Any) -> Any:
    """Python の None は JS の undefined に変換され D1 が受け付けないため、null に置き換える。"""
    if v is None:
        try:
            from pyodide.ffi import jsnull  # type: ignore[import-not-found]

            return jsnull
        except ImportError:  # 古い Pyodide
            import js  # type: ignore[import-not-found]

            return js.JSON.parse("null")
    if isinstance(v, bool):
        return 1 if v else 0
    return v


def _to_py(value: Any) -> Any:
    if hasattr(value, "to_py"):
        return value.to_py()
    return value


class D1Database:
    """【要検証】Pyodide からの D1 呼び出しの型変換。"""

    def __init__(self, binding: Any):
        self._db = binding

    def _prepare(self, sql: str, params: list[Any] | None):
        stmt = self._db.prepare(sql)
        if params:
            stmt = stmt.bind(*[_to_js_param(p) for p in params])
        return stmt

    async def all(self, sql: str, params: list[Any] | None = None) -> list[dict[str, Any]]:
        try:
            res = await self._prepare(sql, params).all()
        except Exception as e:  # JsException
            raise DatabaseError(str(e)) from e
        rows = _to_py(res.results)
        return [dict(r) for r in rows]

    async def first(self, sql: str, params: list[Any] | None = None) -> dict[str, Any] | None:
        rows = await self.all(sql, params)
        return rows[0] if rows else None

    async def run(self, sql: str, params: list[Any] | None = None) -> None:
        try:
            await self._prepare(sql, params).run()
        except Exception as e:
            raise DatabaseError(str(e)) from e

    async def batch(self, statements: list[Statement]) -> None:
        if not statements:
            return
        from pyodide.ffi import to_js  # type: ignore[import-not-found]

        prepared = [self._prepare(sql, params) for sql, params in statements]
        try:
            await self._db.batch(to_js(prepared))
        except Exception as e:
            raise DatabaseError(str(e)) from e
