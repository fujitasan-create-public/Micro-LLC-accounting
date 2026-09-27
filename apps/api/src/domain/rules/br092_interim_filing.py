"""BR-092 中間申告の要否。"""

from __future__ import annotations


def interim_filing_required(prior_corporate_tax: int, threshold: int = 200_000) -> bool:
    """前期の法人税額が20万円を超える場合に必要。"""
    return prior_corporate_tax > threshold
