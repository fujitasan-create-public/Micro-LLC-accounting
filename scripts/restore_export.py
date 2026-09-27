"""エクスポート ZIP（FR-71）から、別環境に復元するための SQL を作る（NFR-04）。

    python scripts/restore_export.py accounting-export-2026-09-27.zip > restore.sql
    npx wrangler d1 execute ledger --remote --file restore.sql      # D1 に復元
    sqlite3 apps/api/.local/ledger.sqlite3 < restore.sql              # ローカルに復元

復元先は migrations を適用済みで、業務データが空であること（seed 済みでもよい。INSERT OR REPLACE で上書きする）。
証憑ファイルは ZIP 内の evidence/ 以下を、同じキーで R2（またはローカルの .local/evidence/）に置く。
"""

from __future__ import annotations

import json
import sys
import zipfile

ORDER = [
    "rule_settings", "withholding_tables", "company", "fiscal_periods", "consumption_tax_settings", "tax_codes",
    "accounts", "counterparties", "payment_accounts", "journal_entries", "journal_lines", "attachments",
    "journal_attachments", "import_rules", "recurring_templates", "recurring_runs", "sales_invoices",
    "sales_invoice_receipts", "officers", "officer_compensations", "payroll_records", "withholding_settings",
    "withholding_payments", "year_end_adjustments", "company_housings", "fixed_assets", "depreciation_runs",
    "closing_carryovers", "documents", "audit_log",
]


def literal(v: object) -> str:
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, (int, float)):
        return str(v)
    return "'" + str(v).replace("'", "''") + "'"


def main(path: str) -> None:
    out = sys.stdout
    out.write("PRAGMA defer_foreign_keys = ON;\n")
    # 復元中は監査ログ・締め済み期間のトリガーを一時的に外す必要がある場合がある。
    # D1 ではトリガーの無効化ができないため、fiscal_periods の status は最後に更新する。
    with zipfile.ZipFile(path) as z:
        closed: list[str] = []
        for t in ORDER:
            name = f"tables/{t}.jsonl"
            if name not in z.namelist():
                continue
            for line in z.read(name).decode("utf-8").splitlines():
                if not line.strip():
                    continue
                row = json.loads(line)
                if t == "fiscal_periods" and row.get("status") == "closed":
                    closed.append(row["id"])
                    row["status"] = "open"
                cols = ", ".join(row.keys())
                vals = ", ".join(literal(v) for v in row.values())
                verb = "INSERT OR IGNORE" if t == "audit_log" else "INSERT OR REPLACE"
                out.write(f"{verb} INTO {t} ({cols}) VALUES ({vals});\n")
        for pid in closed:
            out.write(f"UPDATE fiscal_periods SET status = 'closed' WHERE id = {literal(pid)};\n")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    main(sys.argv[1])
