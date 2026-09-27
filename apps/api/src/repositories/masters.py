"""マスタ系（DM-01〜07）の SQL。"""

from __future__ import annotations

from typing import Any

from db import Database


# ---- 会社設定（DM-01） ----
async def get_company(db: Database) -> dict[str, Any] | None:
    return await db.first("SELECT * FROM company WHERE id = 1")


async def save_company(db: Database, data: dict[str, Any], now: str) -> None:
    cols = list(data.keys())
    await db.run(
        f"""INSERT INTO company (id, {', '.join(cols)}, updated_at) VALUES (1, {', '.join('?' for _ in cols)}, ?)
            ON CONFLICT (id) DO UPDATE SET {', '.join(f'{c} = excluded.{c}' for c in cols)}, updated_at = excluded.updated_at""",
        [int(v) if isinstance(v, bool) else v for v in data.values()] + [now],
    )


# ---- 会計期間（DM-03） ----
async def list_periods(db: Database) -> list[dict[str, Any]]:
    return await db.all("SELECT * FROM fiscal_periods ORDER BY start_date")


async def get_period(db: Database, period_id: str) -> dict[str, Any] | None:
    return await db.first("SELECT * FROM fiscal_periods WHERE id = ?", [period_id])


async def period_for_date(db: Database, d: str) -> dict[str, Any] | None:
    return await db.first("SELECT * FROM fiscal_periods WHERE start_date <= ? AND end_date >= ?", [d, d])


async def overlapping_period(db: Database, start: str, end: str) -> dict[str, Any] | None:
    return await db.first(
        "SELECT * FROM fiscal_periods WHERE NOT (end_date < ? OR start_date > ?)", [start, end]
    )


async def next_period(db: Database, end_date: str) -> dict[str, Any] | None:
    return await db.first("SELECT * FROM fiscal_periods WHERE start_date > ? ORDER BY start_date LIMIT 1", [end_date])


async def previous_period(db: Database, start_date: str) -> dict[str, Any] | None:
    return await db.first("SELECT * FROM fiscal_periods WHERE end_date < ? ORDER BY end_date DESC LIMIT 1", [start_date])


async def set_period_status(db: Database, period_id: str, status: str) -> None:
    await db.run("UPDATE fiscal_periods SET status = ? WHERE id = ?", [status, period_id])


# ---- 消費税設定（DM-02） ----
async def get_consumption_tax(db: Database, period_id: str) -> dict[str, Any] | None:
    return await db.first("SELECT * FROM consumption_tax_settings WHERE fiscal_period_id = ?", [period_id])


async def save_consumption_tax(db: Database, period_id: str, data: dict[str, Any]) -> None:
    cols = list(data.keys())
    await db.run(
        f"""INSERT INTO consumption_tax_settings (fiscal_period_id, {', '.join(cols)}) VALUES (?, {', '.join('?' for _ in cols)})
            ON CONFLICT (fiscal_period_id) DO UPDATE SET {', '.join(f'{c} = excluded.{c}' for c in cols)}""",
        [period_id] + [int(v) if isinstance(v, bool) else v for v in data.values()],
    )


# ---- 税区分・勘定科目（DM-04, 05） ----
async def list_tax_codes(db: Database) -> list[dict[str, Any]]:
    return await db.all("SELECT * FROM tax_codes ORDER BY sort_order, code")


async def get_tax_code(db: Database, code: str) -> dict[str, Any] | None:
    return await db.first("SELECT * FROM tax_codes WHERE code = ?", [code])


async def list_accounts(db: Database, include_inactive: bool = True) -> list[dict[str, Any]]:
    where = "" if include_inactive else "WHERE is_active = 1"
    return await db.all(f"SELECT * FROM accounts {where} ORDER BY code")


async def get_account(db: Database, code: str) -> dict[str, Any] | None:
    return await db.first("SELECT * FROM accounts WHERE code = ?", [code])


async def accounts_by_codes(db: Database, codes: list[str]) -> dict[str, dict[str, Any]]:
    if not codes:
        return {}
    uniq = sorted(set(codes))
    rows = await db.all(f"SELECT * FROM accounts WHERE code IN ({', '.join('?' for _ in uniq)})", uniq)
    return {r["code"]: r for r in rows}


async def tax_codes_map(db: Database) -> dict[str, dict[str, Any]]:
    return {r["code"]: r for r in await list_tax_codes(db)}


# ---- 取引先（DM-06） ----
async def list_counterparties(db: Database) -> list[dict[str, Any]]:
    return await db.all("SELECT * FROM counterparties ORDER BY name")


async def get_counterparty(db: Database, cp_id: str) -> dict[str, Any] | None:
    return await db.first("SELECT * FROM counterparties WHERE id = ?", [cp_id])


# ---- 口座・支払手段（DM-07） ----
async def list_payment_accounts(db: Database) -> list[dict[str, Any]]:
    return await db.all("SELECT * FROM payment_accounts ORDER BY type, name")


async def get_payment_account(db: Database, pa_id: str) -> dict[str, Any] | None:
    return await db.first("SELECT * FROM payment_accounts WHERE id = ?", [pa_id])
