"""FastAPI アプリの組み立て。Workers（main.py）とローカル（local_server.py）で共通。"""

from __future__ import annotations

import importlib

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError

from common import AppError, db_error_to_app_error, error_response
from db import DatabaseError

ROUTER_MODULES = [
    "routers.settings",
    "routers.journals",
    "routers.attachments",
    "routers.imports",
    "routers.sales_invoices",
    "routers.payroll",
    "routers.housing",
    "routers.assets",
    "routers.reports",
    "routers.closing",
    "routers.documents",
    "routers.dashboard",
]


def create_app() -> FastAPI:
    app = FastAPI(title="Micro LLC Accounting API", version="0.1.0")

    for name in ROUTER_MODULES:
        app.include_router(importlib.import_module(name).router)

    @app.exception_handler(AppError)
    async def _app_error(_: Request, e: AppError):
        return error_response(e.status, e.code, e.message, e.rule_id)

    @app.exception_handler(DatabaseError)
    async def _db_error(_: Request, e: DatabaseError):
        a = db_error_to_app_error(e)
        return error_response(a.status, a.code, a.message, a.rule_id)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, e: RequestValidationError):
        details = "; ".join(
            f"{'.'.join(str(x) for x in err.get('loc', [])[1:])}: {err.get('msg')}" for err in e.errors()
        )
        return error_response(422, "validation_error", details or "入力内容が正しくありません")

    @app.get("/api/v1/health")
    async def health():
        return {"ok": True}

    return app
