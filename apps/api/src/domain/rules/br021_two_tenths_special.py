"""BR-021 2割特例の適用可否。

法人の2割特例は、last_period_contains（2026-09-30）を含む課税期間までしか使えない。
課税期間の開始日が翌日（2026-10-01）以後なら選べない。個人事業者向けの3割特例は法人には無いので扱わない。
"""

from __future__ import annotations

from datetime import date


def is_two_tenths_available(period_start: date, last_period_contains: date, taxable_status: str = "taxable") -> bool:
    if taxable_status != "taxable":
        return False
    return period_start <= last_period_contains


def allowed_calculation_methods(period_start: date, last_period_contains: date, taxable_status: str = "taxable") -> list[str]:
    methods = ["standard", "simplified"]
    if is_two_tenths_available(period_start, last_period_contains, taxable_status):
        methods.append("two_tenths_special")
    return methods
