"""BR-022 インボイスのない仕入の経過措置。判定日は取引日（引渡し・役務提供の日）。"""

from __future__ import annotations

from datetime import date
from typing import Any

TRANSITIONAL_MAP = {"P10": "P10N", "P08": "P08N"}


def deductible_rate_pct(transaction_date: date, has_invoice: bool,
                        schedule: list[tuple[date, date | None, Any]]) -> int:
    """
    取引日に対応する仕入税額の控除率（%）を返す。
    schedule は rule_settings の 'invoice_transitional_rate' から作る
    (effective_from, effective_to, rate_pct) のリスト。
    """
    if has_invoice:
        return 100
    for start, end, rate in schedule:
        if start <= transaction_date and (end is None or transaction_date <= end):
            return int(rate)
    return 0


def purchase_tax_code_for(default_tax_code: str, counterparty_has_invoice: bool) -> str:
    """FR-12: 取引先にインボイス登録番号が無ければ、課税仕入の税区分を経過措置の区分にする。"""
    reverse = {v: k for k, v in TRANSITIONAL_MAP.items()}
    if counterparty_has_invoice:
        return reverse.get(default_tax_code, default_tax_code)
    return TRANSITIONAL_MAP.get(default_tax_code, default_tax_code)
