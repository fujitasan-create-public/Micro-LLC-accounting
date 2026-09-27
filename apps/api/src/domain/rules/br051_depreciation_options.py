"""BR-051 固定資産の償却方法の候補。判定日は取得日。"""

from __future__ import annotations


def depreciation_options(acquisition_cost: int, *, immediate_limit: int, lump_sum_limit: int,
                         sme_limit: int | None, is_sme_blue: bool) -> list[str]:
    """
    immediate_limit: 10万円（未満なら即時費用化）
    lump_sum_limit:  20万円（未満なら一括償却資産）
    sme_limit:       取得日に有効な中小企業者等の特例の上限（30万円／40万円）。適用期限外なら None
    """
    options: list[str] = []
    if acquisition_cost < immediate_limit:
        options.append("immediate_small")
    if acquisition_cost < lump_sum_limit:
        options.append("lump_sum_3y")
    if sme_limit is not None and is_sme_blue and acquisition_cost < sme_limit:
        options.append("small_sme_special")
    if acquisition_cost >= immediate_limit:
        # 特例は選択制のため、通常の減価償却も常に選べる
        options.extend(["straight_line", "declining_balance"])
    return options


def sme_annual_cap(annual_cap: int, period_months: int) -> int:
    """事業年度が1年未満なら月数で按分する。"""
    if period_months >= 12:
        return annual_cap
    return annual_cap * period_months // 12


def sme_cap_warning(total_in_period: int, cap: int) -> dict | None:
    if total_in_period > cap:
        return {
            "rule_id": "BR-051",
            "message": f"少額減価償却資産の特例の合計 {total_in_period:,}円 が上限 {cap:,}円 を超えています。"
                       "超える分は通常の減価償却などに切り替えてください",
        }
    return None
