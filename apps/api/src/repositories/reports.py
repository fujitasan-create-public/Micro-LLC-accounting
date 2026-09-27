"""帳票用の集計 SQL。集計は GROUP BY で行い、行ごとのクエリを発行しない（設計書 5.5）。"""

from __future__ import annotations

from typing import Any

from db import Database

_LINES_SQL = """
SELECT je.id AS entry_id, je.transaction_date, je.description, je.source, je.counterparty_id,
       cp.name AS counterparty_name, je.payment_account_id, je.created_at,
       jl.line_no, jl.side, jl.account_code, a.name AS account_name, a.category, a.statement_section,
       jl.amount, jl.tax_code, jl.tax_amount, jl.deductible_rate_pct
FROM journal_entries je
JOIN journal_lines jl ON jl.entry_id = je.id
JOIN accounts a ON a.code = jl.account_code
LEFT JOIN counterparties cp ON cp.id = je.counterparty_id
WHERE je.voided_at IS NULL AND je.fiscal_period_id = ?
"""


async def period_lines(db: Database, period_id: str, account_code: str | None = None,
                       from_: str | None = None, to: str | None = None) -> list[dict[str, Any]]:
    sql = _LINES_SQL
    params: list[Any] = [period_id]
    if account_code:
        sql += " AND jl.account_code = ?"
        params.append(account_code)
    if from_:
        sql += " AND je.transaction_date >= ?"
        params.append(from_)
    if to:
        sql += " AND je.transaction_date <= ?"
        params.append(to)
    sql += " ORDER BY je.transaction_date, je.created_at, jl.line_no"
    return await db.all(sql, params)


async def account_totals(db: Database, period_id: str, to: str | None = None, from_: str | None = None,
                         exclude_sources: list[str] | None = None, only_sources: list[str] | None = None) -> list[dict[str, Any]]:
    """科目ごとの借方・貸方合計（全科目。取引の無い科目も 0 で返す）。"""
    cond = ["je.voided_at IS NULL", "je.fiscal_period_id = ?"]
    params: list[Any] = [period_id]
    if to:
        cond.append("je.transaction_date <= ?")
        params.append(to)
    if from_:
        cond.append("je.transaction_date >= ?")
        params.append(from_)
    if exclude_sources:
        cond.append(f"je.source NOT IN ({', '.join('?' for _ in exclude_sources)})")
        params.extend(exclude_sources)
    if only_sources:
        cond.append(f"je.source IN ({', '.join('?' for _ in only_sources)})")
        params.extend(only_sources)
    return await db.all(
        f"""SELECT a.code, a.name, a.category, a.statement_section, a.is_active,
                   COALESCE(SUM(CASE WHEN t.side = 'debit' THEN t.amount END), 0) AS debit,
                   COALESCE(SUM(CASE WHEN t.side = 'credit' THEN t.amount END), 0) AS credit
            FROM accounts a
            LEFT JOIN (
              SELECT jl.account_code, jl.side, jl.amount FROM journal_lines jl
              JOIN journal_entries je ON je.id = jl.entry_id WHERE {' AND '.join(cond)}
            ) t ON t.account_code = a.code
            GROUP BY a.code ORDER BY a.code""",
        params,
    )


async def counterparty_balances(db: Database, period_id: str, account_code: str) -> list[dict[str, Any]]:
    return await db.all(
        """SELECT COALESCE(cp.name, '（取引先なし）') AS counterparty_name, cp.address,
                  COALESCE(SUM(CASE WHEN jl.side = 'debit' THEN jl.amount ELSE 0 END), 0) AS debit,
                  COALESCE(SUM(CASE WHEN jl.side = 'credit' THEN jl.amount ELSE 0 END), 0) AS credit
           FROM journal_lines jl JOIN journal_entries je ON je.id = jl.entry_id
           LEFT JOIN counterparties cp ON cp.id = je.counterparty_id
           WHERE je.voided_at IS NULL AND je.fiscal_period_id = ? AND jl.account_code = ?
           GROUP BY cp.id ORDER BY cp.name""",
        [period_id, account_code],
    )


async def tax_code_totals(db: Database, period_id: str) -> list[dict[str, Any]]:
    """OUT-16: 税区分・控除率ごとの集計。"""
    return await db.all(
        """SELECT jl.tax_code, tc.name AS tax_code_name, tc.kind, tc.rate, tc.invoice_status,
                  COALESCE(jl.deductible_rate_pct, 100) AS deductible_rate_pct,
                  SUM(CASE WHEN jl.side = 'debit' THEN jl.amount ELSE 0 END) AS debit_amount,
                  SUM(CASE WHEN jl.side = 'credit' THEN jl.amount ELSE 0 END) AS credit_amount,
                  SUM(CASE WHEN jl.side = 'debit' THEN jl.tax_amount ELSE 0 END) AS debit_tax,
                  SUM(CASE WHEN jl.side = 'credit' THEN jl.tax_amount ELSE 0 END) AS credit_tax,
                  COUNT(*) AS line_count
           FROM journal_lines jl JOIN journal_entries je ON je.id = jl.entry_id
           JOIN tax_codes tc ON tc.code = jl.tax_code
           WHERE je.voided_at IS NULL AND je.fiscal_period_id = ?
           GROUP BY jl.tax_code, COALESCE(jl.deductible_rate_pct, 100)
           ORDER BY tc.sort_order, deductible_rate_pct DESC""",
        [period_id],
    )


async def monthly_account_totals(db: Database, period_id: str) -> list[dict[str, Any]]:
    return await db.all(
        """SELECT substr(je.transaction_date, 1, 7) AS month, a.code, a.name, a.category,
                  SUM(CASE WHEN jl.side = 'debit' THEN jl.amount ELSE 0 END) AS debit,
                  SUM(CASE WHEN jl.side = 'credit' THEN jl.amount ELSE 0 END) AS credit
           FROM journal_lines jl JOIN journal_entries je ON je.id = jl.entry_id
           JOIN accounts a ON a.code = jl.account_code
           WHERE je.voided_at IS NULL AND je.fiscal_period_id = ? AND je.source NOT IN ('carryover', 'opening_balance')
           GROUP BY month, a.code ORDER BY month, a.code""",
        [period_id],
    )
