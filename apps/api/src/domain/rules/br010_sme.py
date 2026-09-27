"""BR-010 中小法人の判定。"""

from __future__ import annotations


def is_sme(capital_amount: int, capital_limit: int, wholly_owned_by_large_corporation: bool = False) -> bool:
    """資本金 capital_limit（1億円）以下で、大法人に完全支配されていなければ中小法人。"""
    return capital_amount <= capital_limit and not wholly_owned_by_large_corporation
