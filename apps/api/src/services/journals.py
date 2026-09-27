"""仕訳の登録処理。手入力・CSV取込・定型仕訳・請求書・給与・社宅・減価償却・決算整理から共通で使う。"""

from __future__ import annotations

import json
from datetime import date
from typing import Any, Callable

from common import AppError, new_id, now_iso
from db import Database
from domain.journal import BuiltLine, JournalValidationError, LineIn, build_lines, reverse_lines
from repositories import journals as repo
from repositories import masters, rule_settings


async def resolve_period(db: Database, d: date) -> dict[str, Any]:
    period = await masters.period_for_date(db, d.isoformat())
    if not period:
        raise AppError(422, "no_period", f"{d.isoformat()} を含む会計期間がありません。先に会計期間を作成してください")
    if period["status"] == "closed":
        raise AppError(409, "period_closed",
                       "締め済みの会計期間には仕訳を登録できません。当期の修正仕訳で訂正してください", "NFR-03")
    return period


async def create_entry(
    db: Database,
    *,
    transaction_date: date,
    description: str,
    lines: list[LineIn],
    source: str = "manual",
    counterparty_id: str | None = None,
    payment_account_id: str | None = None,
    entertainment_detail: dict | None = None,
    attachment_ids: list[str] | None = None,
    reverses_entry_id: str | None = None,
    prebuilt: list[BuiltLine] | None = None,
    extra_statements: Callable[[str], list[tuple[str, list[Any]]]] | None = None,
) -> tuple[str, list[dict]]:
    """仕訳を検証して1トランザクションで保存する。返り値は (仕訳ID, 警告)。

    extra_statements には仕訳IDを受け取り、同じトランザクションで実行する SQL を返す関数を渡す。
    """
    period = await resolve_period(db, transaction_date)
    company = await masters.get_company(db)
    method = company["accounting_tax_method"] if company else "tax_included"

    counterparty = None
    if counterparty_id:
        counterparty = await masters.get_counterparty(db, counterparty_id)
        if not counterparty:
            raise AppError(422, "invalid_counterparty", "取引先が存在しません")
    if payment_account_id and not await masters.get_payment_account(db, payment_account_id):
        raise AppError(422, "invalid_payment_account", "口座・支払手段が存在しません")

    warnings: list[dict] = []
    entertainment = None
    try:
        if prebuilt is not None:
            from domain.journal import validate_balance

            validate_balance(prebuilt)
            built_lines = prebuilt
        else:
            accounts = await masters.accounts_by_codes(db, [ln.account_code for ln in lines])
            result = build_lines(
                lines_in=lines,
                transaction_date=transaction_date,
                accounts=accounts,
                tax_codes=await masters.tax_codes_map(db),
                counterparty=counterparty,
                accounting_tax_method=method,
                transitional_schedule=await rule_settings.schedule(db, "invoice_transitional_rate"),
                entertainment_detail=entertainment_detail,
                entertainment_limit=int(await rule_settings.value_on(db, "entertainment_food_per_person_limit", transaction_date, 10000)),
                fee_withholding_params=await rule_settings.value_on(db, "withholding_individual_fee", transaction_date, None),
            )
            built_lines = result.lines
            warnings = result.warnings
            entertainment = result.entertainment
    except JournalValidationError as e:
        raise AppError(422, e.code, e.message, e.rule_id) from e

    now = now_iso()
    entry_id = new_id()
    entry = {
        "id": entry_id,
        "fiscal_period_id": period["id"],
        "transaction_date": transaction_date.isoformat(),
        "description": description,
        "counterparty_id": counterparty_id,
        "payment_account_id": payment_account_id,
        "entertainment_json": json.dumps(entertainment, ensure_ascii=False) if entertainment else None,
        "source": source,
        "reverses_entry_id": reverses_entry_id,
        "voided_at": None,
        "created_at": now,
        "updated_at": now,
    }
    line_rows = [{
        "id": new_id(), "entry_id": entry_id, "line_no": bl.line_no, "side": bl.side,
        "account_code": bl.account_code, "amount": bl.amount, "tax_code": bl.tax_code,
        "tax_amount": bl.tax_amount, "deductible_rate_pct": bl.deductible_rate_pct,
    } for bl in built_lines]
    stmts = repo.entry_insert_statements(entry, line_rows, attachment_ids)
    if extra_statements:
        stmts.extend(extra_statements(entry_id))
    await db.batch(stmts)
    return entry_id, warnings


async def void_entry(db: Database, entry_id: str, reversal_date: date | None = None) -> dict[str, Any]:
    """NFR-02: 取消し。当期（未締め）の仕訳は voided_at を設定し、締め済みなら当期に逆仕訳を作る。"""
    entry = await repo.get_entry(db, entry_id)
    if not entry:
        raise AppError(404, "not_found", "仕訳が見つかりません")
    if entry["voided_at"]:
        raise AppError(409, "already_voided", "この仕訳は既に取り消されています")
    period = await masters.get_period(db, entry["fiscal_period_id"])
    if period and period["status"] != "closed":
        await repo.void_entry(db, entry_id, now_iso())
        return {"voided": True, "reversal_entry_id": None}
    from common import today

    rev_date = reversal_date or today()
    rev_id, _ = await create_entry(
        db,
        transaction_date=rev_date,
        description=f"【逆仕訳】{entry['description']}（元仕訳 {entry['transaction_date']}）",
        lines=[],
        prebuilt=reverse_lines(entry["lines"]),
        source="closing_adjustment",
        counterparty_id=entry.get("counterparty_id"),
        payment_account_id=entry.get("payment_account_id"),
        reverses_entry_id=entry_id,
    )
    return {"voided": False, "reversal_entry_id": rev_id}
