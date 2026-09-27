"""仕訳（DM-08）・証憑（DM-09）の SQL。"""

from __future__ import annotations

from collections import OrderedDict
from typing import Any

from db import Database, Statement
from repositories.base import insert_stmt, loads


def entry_insert_statements(entry: dict[str, Any], lines: list[dict[str, Any]],
                            attachment_ids: list[str] | None = None) -> list[Statement]:
    stmts = [insert_stmt("journal_entries", entry)]
    for ln in lines:
        stmts.append(insert_stmt("journal_lines", ln))
    for aid in attachment_ids or []:
        stmts.append(("INSERT OR IGNORE INTO journal_attachments (entry_id, attachment_id) VALUES (?, ?)", [entry["id"], aid]))
    return stmts


def _filters(f: dict[str, Any]) -> tuple[str, list[Any]]:
    where = ["1 = 1"]
    params: list[Any] = []
    if not f.get("include_voided"):
        where.append("je.voided_at IS NULL")
    if f.get("period_id"):
        where.append("je.fiscal_period_id = ?")
        params.append(f["period_id"])
    if f.get("from"):
        where.append("je.transaction_date >= ?")
        params.append(f["from"])
    if f.get("to"):
        where.append("je.transaction_date <= ?")
        params.append(f["to"])
    total_sql = "(SELECT COALESCE(SUM(x.amount), 0) FROM journal_lines x WHERE x.entry_id = je.id AND x.side = 'debit')"
    if f.get("amount_min") is not None:
        where.append(f"{total_sql} >= ?")
        params.append(int(f["amount_min"]))
    if f.get("amount_max") is not None:
        where.append(f"{total_sql} <= ?")
        params.append(int(f["amount_max"]))
    if f.get("counterparty"):
        where.append("(je.counterparty_id = ? OR cp.name LIKE ?)")
        params.extend([f["counterparty"], f"%{f['counterparty']}%"])
    if f.get("account"):
        where.append("EXISTS (SELECT 1 FROM journal_lines y WHERE y.entry_id = je.id AND y.account_code = ?)")
        params.append(f["account"])
    if f.get("debit_category"):
        where.append("""EXISTS (SELECT 1 FROM journal_lines y JOIN accounts ya ON ya.code = y.account_code
                        WHERE y.entry_id = je.id AND y.side = 'debit' AND ya.category = ?)""")
        params.append(f["debit_category"])
    if f.get("source"):
        where.append("je.source = ?")
        params.append(f["source"])
    if f.get("keyword"):
        where.append("je.description LIKE ?")
        params.append(f"%{f['keyword']}%")
    return " AND ".join(where), params


async def search_entries(db: Database, f: dict[str, Any], limit: int = 500) -> list[dict[str, Any]]:
    """FR-70: 取引年月日（範囲）・金額（範囲）・取引先などの組み合わせ検索。1クエリで明細まで取得する。"""
    where, params = _filters(f)
    rows = await db.all(
        f"""WITH hit AS (
              SELECT je.id FROM journal_entries je
              LEFT JOIN counterparties cp ON cp.id = je.counterparty_id
              WHERE {where}
              ORDER BY je.transaction_date DESC, je.created_at DESC
              LIMIT ?
            )
            SELECT je.*, cp.name AS counterparty_name, pa.name AS payment_account_name,
                   jl.id AS line_id, jl.line_no, jl.side, jl.account_code, a.name AS account_name,
                   jl.amount, jl.tax_code, jl.tax_amount, jl.deductible_rate_pct,
                   (SELECT GROUP_CONCAT(ja.attachment_id) FROM journal_attachments ja WHERE ja.entry_id = je.id) AS attachment_ids
            FROM hit
            JOIN journal_entries je ON je.id = hit.id
            LEFT JOIN counterparties cp ON cp.id = je.counterparty_id
            LEFT JOIN payment_accounts pa ON pa.id = je.payment_account_id
            JOIN journal_lines jl ON jl.entry_id = je.id
            JOIN accounts a ON a.code = jl.account_code
            ORDER BY je.transaction_date DESC, je.created_at DESC, jl.line_no""",
        params + [limit],
    )
    return group_entries(rows)


def group_entries(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    entries: "OrderedDict[str, dict[str, Any]]" = OrderedDict()
    line_keys = {"line_id", "line_no", "side", "account_code", "account_name", "amount", "tax_code",
                 "tax_amount", "deductible_rate_pct"}
    for r in rows:
        e = entries.get(r["id"])
        if e is None:
            e = {k: v for k, v in r.items() if k not in line_keys}
            e["entertainment"] = loads(e.pop("entertainment_json", None))
            e["attachment_ids"] = (e.get("attachment_ids") or "").split(",") if e.get("attachment_ids") else []
            e["lines"] = []
            e["total_amount"] = 0
            entries[r["id"]] = e
        e["lines"].append({
            "id": r["line_id"], "line_no": r["line_no"], "side": r["side"], "account_code": r["account_code"],
            "account_name": r["account_name"], "amount": r["amount"], "tax_code": r["tax_code"],
            "tax_amount": r["tax_amount"], "deductible_rate_pct": r["deductible_rate_pct"],
        })
        if r["side"] == "debit":
            e["total_amount"] += r["amount"]
    return list(entries.values())


async def get_entry(db: Database, entry_id: str) -> dict[str, Any] | None:
    rows = await db.all(
        """SELECT je.*, cp.name AS counterparty_name, pa.name AS payment_account_name,
                  jl.id AS line_id, jl.line_no, jl.side, jl.account_code, a.name AS account_name,
                  jl.amount, jl.tax_code, jl.tax_amount, jl.deductible_rate_pct,
                  (SELECT GROUP_CONCAT(ja.attachment_id) FROM journal_attachments ja WHERE ja.entry_id = je.id) AS attachment_ids
           FROM journal_entries je
           LEFT JOIN counterparties cp ON cp.id = je.counterparty_id
           LEFT JOIN payment_accounts pa ON pa.id = je.payment_account_id
           JOIN journal_lines jl ON jl.entry_id = je.id
           JOIN accounts a ON a.code = jl.account_code
           WHERE je.id = ? ORDER BY jl.line_no""",
        [entry_id],
    )
    grouped = group_entries(rows)
    return grouped[0] if grouped else None


async def void_entry(db: Database, entry_id: str, now: str) -> None:
    await db.run("UPDATE journal_entries SET voided_at = ?, updated_at = ? WHERE id = ? AND voided_at IS NULL",
                 [now, now, entry_id])


async def audit_history(db: Database, table: str, row_id: str) -> list[dict[str, Any]]:
    return await db.all("SELECT * FROM audit_log WHERE table_name = ? AND row_id = ? ORDER BY id", [table, row_id])


# ---- 証憑 ----
async def search_attachments(db: Database, f: dict[str, Any]) -> list[dict[str, Any]]:
    where = ["1 = 1"]
    params: list[Any] = []
    if not f.get("include_voided"):
        where.append("a.voided_at IS NULL")
    if f.get("from"):
        where.append("a.transaction_date >= ?")
        params.append(f["from"])
    if f.get("to"):
        where.append("a.transaction_date <= ?")
        params.append(f["to"])
    if f.get("amount_min") is not None:
        where.append("a.amount >= ?")
        params.append(int(f["amount_min"]))
    if f.get("amount_max") is not None:
        where.append("a.amount <= ?")
        params.append(int(f["amount_max"]))
    if f.get("counterparty"):
        where.append("a.counterparty_name LIKE ?")
        params.append(f"%{f['counterparty']}%")
    return await db.all(
        f"""SELECT a.*, (SELECT GROUP_CONCAT(ja.entry_id) FROM journal_attachments ja WHERE ja.attachment_id = a.id) AS entry_ids
            FROM attachments a WHERE {' AND '.join(where)} ORDER BY a.transaction_date DESC, a.created_at DESC LIMIT 500""",
        params,
    )


async def get_attachment(db: Database, att_id: str) -> dict[str, Any] | None:
    return await db.first("SELECT * FROM attachments WHERE id = ?", [att_id])
