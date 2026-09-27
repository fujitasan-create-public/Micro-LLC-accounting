"""BR-020 消費税の課税判定の補助。最終的な区分はユーザーが DM-02 で設定する。"""

from __future__ import annotations

from datetime import date

CAPITAL_THRESHOLD = 10_000_000
SPECIFIED_PERIOD_THRESHOLD = 10_000_000


def taxable_status_hint(
    capital_amount: int,
    incorporation_date: date,
    period_start: date,
    period_index: int,
    has_invoice_registration: bool,
    specified_period_sales: int | None = None,
    specified_period_salaries: int | None = None,
) -> dict:
    """period_index は設立からの期数（1始まり）。判定の根拠と推定区分を返す。"""
    reasons: list[str] = []
    if has_invoice_registration:
        reasons.append("インボイス登録をしているため課税事業者です")
        return {"suggested": "taxable", "reasons": reasons}
    if capital_amount >= CAPITAL_THRESHOLD:
        reasons.append("資本金が1,000万円以上のため、設立当初から課税事業者です（新設法人の特例）")
        return {"suggested": "taxable", "reasons": reasons}
    if period_index <= 2:
        if (
            period_index == 2
            and specified_period_sales is not None
            and specified_period_salaries is not None
            and specified_period_sales > SPECIFIED_PERIOD_THRESHOLD
            and specified_period_salaries > SPECIFIED_PERIOD_THRESHOLD
        ):
            reasons.append("特定期間の課税売上高と給与支払額がともに1,000万円を超えるため課税事業者です")
            return {"suggested": "taxable", "reasons": reasons}
        reasons.append("資本金1,000万円未満で設立2期以内のため、原則として免税事業者です")
        return {"suggested": "exempt", "reasons": reasons}
    reasons.append("基準期間（前々期）の課税売上高が1,000万円を超えるかで判定してください")
    return {"suggested": None, "reasons": reasons}
