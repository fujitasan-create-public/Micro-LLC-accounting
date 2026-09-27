"""ローカル開発用のエントリポイント（CPython + uvicorn）。

D1 の代わりに SQLite、R2 の代わりにローカルフォルダを使う。起動時に migrations/ と seed/ を自動適用する。

    uv run uvicorn local_server:app --app-dir src --port 8787 --reload
"""

from __future__ import annotations

import os
from pathlib import Path

from app_factory import create_app
from db import SqliteDatabase
from storage import LocalStorage

API_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = API_DIR.parent.parent
DATA_DIR = Path(os.environ.get("ACCOUNTING_LOCAL_DIR", API_DIR / ".local"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

app = create_app()
app.state.db = SqliteDatabase(DATA_DIR / "ledger.sqlite3")
app.state.evidence = LocalStorage(DATA_DIR / "evidence")
app.state.backup = LocalStorage(DATA_DIR / "backup")

_applied = app.state.db.apply_sql_files([REPO_ROOT / "migrations", REPO_ROOT / "seed"])
if _applied:
    print(f"[local] applied: {', '.join(_applied)}")
