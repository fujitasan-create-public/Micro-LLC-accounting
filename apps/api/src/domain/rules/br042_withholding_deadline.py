"""BR-042 源泉所得税の納付期限。土日祝日・年末年始は翌営業日。"""

from __future__ import annotations

from datetime import date

from domain.rules.jp_holidays import next_business_day


def deadline_for_payment(pay_date: date, special_payment_deadline: bool) -> date:
    if special_payment_deadline:
        base = date(pay_date.year, 7, 10) if pay_date.month <= 6 else date(pay_date.year + 1, 1, 20)
    else:
        y, m = (pay_date.year + 1, 1) if pay_date.month == 12 else (pay_date.year, pay_date.month + 1)
        base = date(y, m, 10)
    return next_business_day(base)


def period_label(pay_date: date, special_payment_deadline: bool) -> str:
    if special_payment_deadline:
        return f"{pay_date.year}-H{1 if pay_date.month <= 6 else 2}"
    return f"{pay_date.year}-{pay_date.month:02d}"
