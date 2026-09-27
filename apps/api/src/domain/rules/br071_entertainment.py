"""BR-071 交際費の判定補助。"""

from __future__ import annotations

ENTERTAINMENT_ACCOUNT_CODE = "590"


def per_person_amount(total: int, headcount: int) -> int:
    """1人あたり金額（切捨て）。"""
    if headcount <= 0:
        return total
    return total // headcount


def evaluate(total: int, detail: dict | None, per_person_limit: int = 10_000) -> dict:
    """
    detail: {participants, headcount, is_food_and_drink, venue?, is_internal_only?}
    返り値: {per_person, excludable, warnings}
    """
    warnings: list[dict] = []
    if not detail:
        warnings.append({"rule_id": "BR-071", "message": "交際費の参加者・人数・飲食かどうかを入力してください"})
        return {"per_person": None, "excludable": False, "warnings": warnings}
    headcount = int(detail.get("headcount") or 0)
    per = per_person_amount(total, headcount)
    excludable = (
        bool(detail.get("is_food_and_drink"))
        and not detail.get("is_internal_only")
        and headcount > 0
        and per <= per_person_limit
    )
    if excludable:
        labels = {"participants": "参加者の氏名・関係", "venue": "店名"}
        missing = [label for key, label in labels.items() if not detail.get(key)]
        if missing:
            warnings.append({
                "rule_id": "BR-071",
                "message": f"1人あたり{per_person_limit:,}円以下の飲食費として交際費から除外するには、"
                           f"{'・'.join(missing)}の記録が必要です",
            })
    return {"per_person": per, "excludable": excludable, "warnings": warnings}
