"""減価償却の計算（FR-50）。償却の起点は service_start_date、月割り（1か月未満は1か月）。

- 定額法: 取得価額 × (1 / 耐用年数) × 月数/12。最終年度は備忘価額1円を残す。
- 定率法（200%定率法）: 償却率 = 2 / 耐用年数。未償却残高 ×償却率 が「残存年数での均等償却額」を下回ったら切り替える近似。
  【要確認】法定の償却保証率・改定償却率の表とは端数が異なる場合がある。
- 一括償却資産: 取得価額 × 月数/36（事業年度の月数で按分）。3年（36か月）で全額。
- 即時費用化・中小企業者等の特例: 事業に使い始めた期に全額。
端数は1円未満切捨て。
"""

from __future__ import annotations

from datetime import date
from decimal import ROUND_DOWN, Decimal


def _floor(x: Decimal) -> int:
    return int(x.to_integral_value(rounding=ROUND_DOWN))


def months_between(start: date, end: date) -> int:
    """start の月から end の月までの月数（両端含む）。"""
    if end < start:
        return 0
    return (end.year - start.year) * 12 + (end.month - start.month) + 1


def depreciation_for_period(*, method: str, cost: int, useful_life_years: int, service_start: date,
                            disposal_date: date | None, period_start: date, period_end: date,
                            accumulated_before: int) -> int:
    book = cost - accumulated_before
    if book <= 0 or service_start > period_end:
        return 0
    if disposal_date and disposal_date < period_start:
        return 0

    start = max(service_start, period_start)
    end = min(disposal_date, period_end) if disposal_date else period_end
    months = months_between(start, end)
    period_months = months_between(period_start, period_end)

    if method in ("immediate_small", "small_sme_special"):
        return book if period_start <= service_start <= period_end else 0

    if method == "lump_sum_3y":
        # 一括償却資産は除却しても3年で償却を続ける（月数は事業年度の月数）
        return min(book, _floor(Decimal(cost) * Decimal(period_months) / Decimal(36)))

    floor_value = 1  # 備忘価額
    if method == "straight_line":
        amount = _floor(Decimal(cost) / Decimal(useful_life_years) * Decimal(months) / Decimal(12))
        return max(min(amount, book - floor_value), 0)

    if method == "declining_balance":
        rate = Decimal(2) / Decimal(useful_life_years)
        db_amount = Decimal(book) * rate
        elapsed_months = months_between(service_start, period_start) - 1 if service_start < period_start else 0
        remaining_years = max(Decimal(useful_life_years) - Decimal(elapsed_months) / Decimal(12), Decimal(1))
        sl_amount = Decimal(book) / remaining_years
        annual = max(db_amount, sl_amount)
        amount = _floor(annual * Decimal(months) / Decimal(12))
        return max(min(amount, book - floor_value), 0)

    raise ValueError(f"unknown method: {method}")
