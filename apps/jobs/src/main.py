"""日次バックアップ（設計書 10章、NFR-04）。Cron Trigger で毎日実行する。

全テーブルを1テーブル1ファイルの JSON Lines にして backup/daily/{YYYY-MM-DD}/ に保存する。
90日より古いものは R2 のライフサイクルルールで削除する（バケット側で設定）。
期限一覧（第7章）は api の GET /deadlines がその都度計算し、web のトップ画面に表示する。

【要検証】Python Workers の scheduled ハンドラのシグネチャと、全テーブル読み出しの CPU 時間。
収まらない場合は TABLES を分割し、Cron を複数に分ける。
"""

import json
from datetime import datetime, timedelta, timezone

from workers import WorkerEntrypoint  # type: ignore[import-not-found]

JST = timezone(timedelta(hours=9))

TABLES = [
    "rule_settings", "withholding_tables", "company", "fiscal_periods", "consumption_tax_settings", "tax_codes",
    "accounts", "counterparties", "payment_accounts", "journal_entries", "journal_lines", "attachments",
    "journal_attachments", "import_rules", "recurring_templates", "recurring_runs", "sales_invoices",
    "sales_invoice_receipts", "officers", "officer_compensations", "payroll_records", "withholding_settings",
    "withholding_payments", "year_end_adjustments", "company_housings", "fixed_assets", "depreciation_runs",
    "closing_carryovers", "audit_log",
]
PAGE = 1000


async def dump_table(db, table: str) -> str:
    lines = []
    offset = 0
    while True:
        res = await db.prepare(f"SELECT * FROM {table} LIMIT ? OFFSET ?").bind(PAGE, offset).all()
        rows = res.results.to_py()
        lines.extend(json.dumps(dict(r), ensure_ascii=False) for r in rows)
        if len(rows) < PAGE:
            break
        offset += PAGE
    return "\n".join(lines) + ("\n" if lines else "")


async def run_backup(env) -> dict:
    day = datetime.now(JST).date().isoformat()
    counts = {}
    for table in TABLES:
        body = await dump_table(env.DB, table)
        await env.BACKUP.put(f"backup/daily/{day}/{table}.jsonl", body)
        counts[table] = body.count("\n")
    await env.BACKUP.put(f"backup/daily/{day}/manifest.json",
                         json.dumps({"date": day, "tables": counts}, ensure_ascii=False))
    return counts


class Default(WorkerEntrypoint):
    async def scheduled(self, controller, env=None, ctx=None):
        await run_backup(env or self.env)
