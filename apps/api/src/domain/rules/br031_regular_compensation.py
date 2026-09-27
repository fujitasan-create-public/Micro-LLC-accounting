"""BR-031 定期同額給与のチェック。"""

from __future__ import annotations

import calendar
from datetime import date


def add_months(d: date, months: int) -> date:
    y, m = divmod(d.month - 1 + months, 12)
    y += d.year
    m += 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def revision_warnings(period_start: date, period_end: date, compensations: list[dict],
                      revision_months: int = 3) -> list[dict]:
    """
    compensations: [{effective_from: date, monthly_amount, revision_reason}]（全履歴）
    同一事業年度内で monthly_amount が変わり、effective_from が期首から revision_months か月を超え、
    理由が regular の場合に警告する。
    """
    warnings = []
    ordered = sorted(compensations, key=lambda c: c["effective_from"])
    limit = add_months(period_start, revision_months)
    for prev, cur in zip(ordered, ordered[1:]):
        eff = cur["effective_from"]
        if not (period_start <= eff <= period_end):
            continue
        if cur["monthly_amount"] == prev["monthly_amount"]:
            continue
        if eff >= limit and cur["revision_reason"] == "regular":
            warnings.append({
                "rule_id": "BR-031",
                "message": f"{eff.isoformat()} からの役員報酬の改定は期首から{revision_months}か月を超えています。"
                           "定期同額給与に当たらず、改定前後の差額が損金不算入になる可能性があります",
            })
    return warnings


def compensation_for_month(compensations: list[dict], pay_date: date) -> dict | None:
    """pay_date に有効な改定レコード（effective_from が pay_date 以前で最新のもの）を返す。"""
    current = None
    for c in sorted(compensations, key=lambda c: c["effective_from"]):
        if c["effective_from"] <= pay_date:
            current = c
    return current


def payment_mismatch_warning(compensations: list[dict], pay_date: date, gross_amount: int) -> dict | None:
    c = compensation_for_month(compensations, pay_date)
    if c is None:
        return {"rule_id": "BR-031", "message": "この支給日に有効な役員報酬の決定（改定履歴）がありません"}
    if c["monthly_amount"] != gross_amount:
        return {
            "rule_id": "BR-031",
            "message": f"支給額 {gross_amount:,}円 が、決定済みの月額報酬 {c['monthly_amount']:,}円 と異なります（定期同額給与の要件）",
        }
    return None
