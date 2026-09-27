"""日本の祝日（BR-042 の翌営業日判定用）。

春分・秋分は近似式（1980〜2099年で有効）で求める。
"""

from __future__ import annotations

from datetime import date, timedelta


def _nth_monday(year: int, month: int, n: int) -> date:
    d = date(year, month, 1)
    offset = (0 - d.weekday()) % 7
    return d + timedelta(days=offset + 7 * (n - 1))


def _vernal_equinox(year: int) -> int:
    return int(20.8431 + 0.242194 * (year - 1980) - int((year - 1980) / 4))


def _autumnal_equinox(year: int) -> int:
    return int(23.2488 + 0.242194 * (year - 1980) - int((year - 1980) / 4))


def holidays(year: int) -> set[date]:
    h = {
        date(year, 1, 1),
        _nth_monday(year, 1, 2),
        date(year, 2, 11),
        date(year, 2, 23),
        date(year, 3, _vernal_equinox(year)),
        date(year, 4, 29),
        date(year, 5, 3),
        date(year, 5, 4),
        date(year, 5, 5),
        _nth_monday(year, 7, 3),
        date(year, 8, 11),
        _nth_monday(year, 9, 3),
        date(year, 9, _autumnal_equinox(year)),
        _nth_monday(year, 10, 2),
        date(year, 11, 3),
        date(year, 11, 23),
    }
    # 国民の休日（祝日に挟まれた平日）
    for d in list(h):
        mid = d + timedelta(days=1)
        if mid not in h and (mid + timedelta(days=1)) in h and mid.weekday() != 6:
            h.add(mid)
    # 振替休日
    for d in sorted(h):
        if d.weekday() == 6:
            s = d + timedelta(days=1)
            while s in h:
                s += timedelta(days=1)
            h.add(s)
    return h


def is_business_day(d: date) -> bool:
    if d.weekday() >= 5:
        return False
    if d.month == 1 and d.day <= 3:  # 年始の閉庁日
        return False
    if d.month == 12 and d.day == 31:
        return False
    return d not in holidays(d.year)


def next_business_day(d: date) -> date:
    while not is_business_day(d):
        d += timedelta(days=1)
    return d
