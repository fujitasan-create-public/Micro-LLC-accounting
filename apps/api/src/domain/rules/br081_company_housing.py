"""BR-081 借上げ社宅の賃料相当額（月額）。端数は1円未満切捨て。"""

from __future__ import annotations

from decimal import ROUND_DOWN, Decimal


def _floor(x: Decimal) -> int:
    return int(x.to_integral_value(rounding=ROUND_DOWN))


def is_small_housing(structure: str, floor_area_sqm: Decimal, limits: dict) -> bool:
    limit = Decimal(str(limits["wooden" if structure == "wooden" else "non_wooden"]))
    return floor_area_sqm <= limit


def imputed_rent(*, structure: str, floor_area_sqm: Decimal, building_tax_base: int, land_tax_base: int,
                 monthly_rent: int, is_luxury: bool, market_rent: int | None,
                 small_limits: dict, small_formula: dict, large_formula: dict) -> dict:
    if is_luxury:
        return {"method": "luxury", "amount": int(market_rent or 0), "is_small": False}
    if is_small_housing(structure, floor_area_sqm, small_limits):
        amount = (
            Decimal(building_tax_base) * Decimal(str(small_formula["building_rate"]))
            + Decimal(str(small_formula["per_sqm_yen"])) * floor_area_sqm / Decimal(str(small_formula["sqm_divisor"]))
            + Decimal(land_tax_base) * Decimal(str(small_formula["land_rate"]))
        )
        return {"method": "small", "amount": _floor(amount), "is_small": True}
    b_rate = large_formula["building_rate_wooden" if structure == "wooden" else "building_rate_non_wooden"]
    by_tax_base = (Decimal(building_tax_base) * Decimal(str(b_rate))
                   + Decimal(land_tax_base) * Decimal(str(large_formula["land_rate"]))) / Decimal(12)
    by_rent = Decimal(monthly_rent) * Decimal(str(large_formula["rent_ratio"]))
    return {
        "method": "large",
        "amount": _floor(max(by_tax_base, by_rent)),
        "is_small": False,
        "by_tax_base": _floor(by_tax_base),
        "by_rent": _floor(by_rent),
    }


def collection_warning(collection_amount: int, imputed: int) -> dict | None:
    """FR-41: 徴収額が賃料相当額を下回る場合の警告。"""
    if collection_amount < imputed:
        diff = imputed - collection_amount
        return {
            "rule_id": "BR-081",
            "message": f"役員から受け取る額 {collection_amount:,}円 が賃料相当額 {imputed:,}円 を下回っています。"
                       f"差額 月{diff:,}円 は役員報酬（現物給与）として課税されます",
        }
    return None
