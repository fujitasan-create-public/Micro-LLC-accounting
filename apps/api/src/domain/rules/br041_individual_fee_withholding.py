"""BR-041 個人への報酬支払時の源泉徴収。"""

from __future__ import annotations

from decimal import ROUND_DOWN, Decimal

FEE_ACCOUNT_CODE = "610"  # 支払報酬


def withholding_amount(payment: int, threshold: int = 1_000_000,
                       rate_low: str = "0.1021", rate_high: str = "0.2042") -> int:
    """100万円以下の部分は10.21%、超える部分は20.42%。1円未満切捨て。"""
    low = min(payment, threshold)
    high = max(payment - threshold, 0)
    tax = Decimal(low) * Decimal(rate_low) + Decimal(high) * Decimal(rate_high)
    return int(tax.to_integral_value(rounding=ROUND_DOWN))


def warning_if_needed(account_code: str, entity_type: str | None, amount: int, params: dict | None = None) -> dict | None:
    """支払報酬の科目で取引先が個人なら警告する。法人への支払は原則として源泉徴収不要。"""
    if account_code != FEE_ACCOUNT_CODE or entity_type != "individual":
        return None
    p = params or {}
    est = withholding_amount(amount, int(p.get("threshold", 1_000_000)),
                             str(p.get("rate_low", "0.1021")), str(p.get("rate_high", "0.2042")))
    return {
        "rule_id": "BR-041",
        "message": f"個人への報酬です。源泉徴収が必要な可能性があります（目安の税額 {est:,}円）。"
                   "徴収した場合は預り金（源泉所得税）を貸方に計上してください",
    }
