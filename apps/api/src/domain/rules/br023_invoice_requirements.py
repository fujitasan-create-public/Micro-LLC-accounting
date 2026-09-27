"""BR-023 インボイス（適格請求書）の記載事項と、税率ごとの消費税額の計算。

端数処理: 1請求書につき税率ごとに1回、切り捨て。
明細の amount は税抜金額として扱う。
"""

from __future__ import annotations

from decimal import ROUND_DOWN, Decimal


def summarize_by_rate(lines: list[dict]) -> list[dict]:
    """[{rate, is_reduced, net_total, tax, gross_total}] を税率の高い順に返す。"""
    buckets: dict[str, int] = {}
    for ln in lines:
        rate = str(Decimal(str(ln["tax_rate"])).quantize(Decimal("0.01")))
        buckets[rate] = buckets.get(rate, 0) + int(ln["amount"])
    result = []
    for rate, net in sorted(buckets.items(), key=lambda kv: Decimal(kv[0]), reverse=True):
        tax = int((Decimal(net) * Decimal(rate)).to_integral_value(rounding=ROUND_DOWN))
        result.append({
            "rate": rate,
            "is_reduced": Decimal(rate) == Decimal("0.08"),
            "net_total": net,
            "tax": tax,
            "gross_total": net + tax,
        })
    return result


def missing_requirements(issuer_name: str | None, registration_number: str | None,
                         service_period: str | None, lines: list[dict], client_name: str | None) -> list[str]:
    """記載事項のうち欠けているものを返す。空なら要件を満たす。"""
    missing = []
    if not issuer_name:
        missing.append("発行者の名称")
    if not registration_number:
        missing.append("発行者の登録番号")
    if not service_period:
        missing.append("取引年月日")
    if not lines or any(not ln.get("description") for ln in lines):
        missing.append("取引内容")
    if not lines or any(ln.get("tax_rate") in (None, "") for ln in lines):
        missing.append("適用税率")
    if not client_name:
        missing.append("受け取る側の名称")
    return missing
