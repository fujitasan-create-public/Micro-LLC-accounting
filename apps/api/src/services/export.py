"""全データのエクスポート（FR-71, NFR-04）と、締め処理時の年次アーカイブ（NFR-01）。"""

from __future__ import annotations

import csv
import io
import json
import zipfile
from typing import Any

from db import Database
from storage import ObjectStorage

# 復元時に外部キーの順序で投入できるよう、依存の少ない順に並べる
TABLES = [
    "rule_settings", "withholding_tables", "company", "fiscal_periods", "consumption_tax_settings", "tax_codes",
    "accounts", "counterparties", "payment_accounts", "journal_entries", "journal_lines", "attachments",
    "journal_attachments", "import_rules", "recurring_templates", "recurring_runs", "sales_invoices",
    "sales_invoice_receipts", "officers", "officer_compensations", "payroll_records", "withholding_settings",
    "withholding_payments", "year_end_adjustments", "company_housings", "fixed_assets", "depreciation_runs",
    "closing_carryovers", "audit_log",
]


async def dump_table(db: Database, table: str, where: str = "", params: list[Any] | None = None) -> list[dict]:
    return await db.all(f"SELECT * FROM {table} {where}", params or [])


def to_jsonl(rows: list[dict]) -> bytes:
    return "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows).encode("utf-8")


def to_csv(rows: list[dict]) -> bytes:
    if not rows:
        return b""
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(rows[0].keys()), lineterminator="\r\n")
    w.writeheader()
    w.writerows(rows)
    return ("﻿" + buf.getvalue()).encode("utf-8")


async def build_zip(db: Database, evidence: ObjectStorage, include_files: bool = True) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        manifest: dict[str, Any] = {"format": "micro-llc-accounting-export", "version": 1, "tables": {}}
        for t in TABLES:
            rows = await dump_table(db, t)
            manifest["tables"][t] = len(rows)
            z.writestr(f"tables/{t}.jsonl", to_jsonl(rows))
            z.writestr(f"csv/{t}.csv", to_csv(rows))
        if include_files:
            for a in await dump_table(db, "attachments"):
                data = await evidence.get(a["r2_key"])
                if data is not None:
                    z.writestr(a["r2_key"], data)
        z.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    return buf.getvalue()


async def archive_closed_period(db: Database, backup: ObjectStorage, period: dict, reports: dict[str, Any]) -> list[str]:
    """締めた期のデータを backup/closed/{期末日}/ に保存する。このプレフィックスはバケットロックで保護する。"""
    prefix = f"backup/closed/{period['end_date']}"
    keys = []
    pid = period["id"]
    parts = {
        "journal_entries": await dump_table(db, "journal_entries", "WHERE fiscal_period_id = ?", [pid]),
        "journal_lines": await dump_table(db, "journal_lines", "WHERE entry_id IN (SELECT id FROM journal_entries WHERE fiscal_period_id = ?)", [pid]),
        "attachments": await dump_table(db, "attachments", "WHERE transaction_date BETWEEN ? AND ?", [period["start_date"], period["end_date"]]),
        "journal_attachments": await dump_table(db, "journal_attachments", "WHERE entry_id IN (SELECT id FROM journal_entries WHERE fiscal_period_id = ?)", [pid]),
        "payroll_records": await dump_table(db, "payroll_records", "WHERE pay_date BETWEEN ? AND ?", [period["start_date"], period["end_date"]]),
        "fixed_assets": await dump_table(db, "fixed_assets"),
        "accounts": await dump_table(db, "accounts"),
        "tax_codes": await dump_table(db, "tax_codes"),
        "counterparties": await dump_table(db, "counterparties"),
        "company": await dump_table(db, "company"),
        "closing_carryovers": await dump_table(db, "closing_carryovers", "WHERE fiscal_period_id = ?", [pid]),
        "audit_log": await dump_table(db, "audit_log"),
    }
    for name, rows in parts.items():
        key = f"{prefix}/{name}.jsonl"
        if not await backup.exists(key):
            await backup.put(key, to_jsonl(rows), "application/x-ndjson")
            keys.append(key)
    key = f"{prefix}/financial_statements.json"
    if not await backup.exists(key):
        await backup.put(key, json.dumps(reports, ensure_ascii=False, default=str).encode("utf-8"), "application/json")
        keys.append(key)
    return keys
