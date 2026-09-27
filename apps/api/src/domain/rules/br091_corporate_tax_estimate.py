"""BR-091 法人税等の概算。あくまで概算であり、申告書の作成は申告ソフトで行う。

端数処理: 課税標準は1,000円未満切捨て、税額は100円未満切捨て。
"""

from __future__ import annotations

from decimal import ROUND_DOWN, Decimal


def _floor_to(x: Decimal | int, unit: int) -> int:
    v = int(Decimal(x).to_integral_value(rounding=ROUND_DOWN))
    return (v // unit) * unit if v > 0 else 0


def apply_loss_carryforwards(income: int, carryforwards: list[dict], is_sme: bool) -> tuple[int, list[dict], int]:
    """古い年度から順に控除する。中小法人は所得の全額まで、それ以外は50%まで。
    返り値: (控除後所得, 控除後の繰越欠損金残高, 控除額)"""
    ordered = sorted(carryforwards, key=lambda c: c["origin_period"])
    if income <= 0:
        return income, ordered, 0
    limit = income if is_sme else income // 2
    used_total = 0
    updated = []
    for cf in ordered:
        remaining = int(cf["remaining_amount"])
        use = min(remaining, limit - used_total)
        used_total += use
        if remaining - use > 0:
            updated.append({**cf, "remaining_amount": remaining - use})
    return income - used_total, updated, used_total


def estimate(*, taxable_income: int, is_sme: bool, per_capita: int, corporate_rate: dict,
             local_corporate_rate: str, defense: dict | None, enterprise_rates: list[dict],
             special_enterprise_rate: str, resident_corporate_rate: str) -> dict:
    base = _floor_to(max(taxable_income, 0), 1000)

    # 法人税（中小法人は年800万円以下の部分に軽減税率）
    threshold = int(corporate_rate["reduced_threshold"])
    if is_sme:
        low = min(base, threshold)
        high = max(base - threshold, 0)
        corp = Decimal(low) * Decimal(corporate_rate["reduced"]) + Decimal(high) * Decimal(corporate_rate["standard"])
    else:
        corp = Decimal(base) * Decimal(corporate_rate["standard"])
    corporate_tax = _floor_to(corp, 100)

    # 防衛特別法人税（2026-04-01以後開始の事業年度。defense が None なら対象外）
    defense_tax = 0
    if defense:
        defense_base = _floor_to(max(corporate_tax - int(defense["basic_deduction"]), 0), 1000)
        defense_tax = _floor_to(Decimal(defense_base) * Decimal(defense["rate"]), 100)

    # 地方法人税（課税標準は法人税額）
    local_corporate_tax = _floor_to(Decimal(_floor_to(corporate_tax, 1000)) * Decimal(local_corporate_rate), 100)

    # 法人事業税（所得割、段階税率）
    ent = Decimal(0)
    prev = 0
    for bracket in enterprise_rates:
        upto = bracket["upto"]
        top = base if upto is None else min(base, int(upto))
        if top > prev:
            ent += Decimal(top - prev) * Decimal(bracket["rate"])
        if upto is None or base <= int(upto):
            break
        prev = int(upto)
    enterprise_tax = _floor_to(ent, 100)

    # 特別法人事業税（標準税率による事業税額 × 37%）
    special_enterprise_tax = _floor_to(Decimal(enterprise_tax) * Decimal(special_enterprise_rate), 100)

    # 法人住民税（法人税割 + 均等割。均等割は赤字でも発生する）
    resident_corporate = _floor_to(Decimal(_floor_to(corporate_tax, 1000)) * Decimal(resident_corporate_rate), 100)

    total = (corporate_tax + defense_tax + local_corporate_tax + enterprise_tax
             + special_enterprise_tax + resident_corporate + int(per_capita))
    return {
        "taxable_income": base,
        "corporate_tax": corporate_tax,
        "defense_special_corporate_tax": defense_tax,
        "local_corporate_tax": local_corporate_tax,
        "enterprise_tax": enterprise_tax,
        "special_enterprise_tax": special_enterprise_tax,
        "resident_tax_corporate": resident_corporate,
        "resident_tax_per_capita": int(per_capita),
        "total": total,
        "is_estimate": True,
    }
