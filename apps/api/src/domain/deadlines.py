"""年間の期限一覧（要件定義書 第7章）。期限が土日祝日なら翌営業日にする。"""

from __future__ import annotations

import calendar
from datetime import date, timedelta

from domain.rules.br031_regular_compensation import add_months
from domain.rules.jp_holidays import next_business_day


def _month_end(d: date) -> date:
    return date(d.year, d.month, calendar.monthrange(d.year, d.month)[1])


def compute(*, start: date, end: date, periods: list[dict], special_withholding: bool,
            interim_required_period_ids: set[str], has_payroll: bool = True) -> list[dict]:
    items: list[dict] = []

    def add(d: date, title: str, rule_id: str, detail: str = "") -> None:
        due = next_business_day(d)
        if start <= due <= end:
            items.append({"date": due.isoformat(), "title": title, "rule_id": rule_id, "detail": detail})

    for y in range(start.year - 1, end.year + 2):
        if has_payroll:
            if special_withholding:
                add(date(y, 7, 10), "源泉所得税の納付（1〜6月支払分・納期の特例）", "BR-042")
                add(date(y, 1, 20), "源泉所得税の納付（前年7〜12月支払分・納期の特例）", "BR-042")
            else:
                for m in range(1, 13):
                    prev = (y - 1, 12) if m == 1 else (y, m - 1)
                    add(date(y, m, 10), f"源泉所得税の納付（{prev[0]}年{prev[1]}月支払分）", "BR-042")
            d = date(y, 12, 1)
            if start <= d <= end:
                items.append({"date": d.isoformat(), "title": "年末調整（12月の給与支給時まで）", "rule_id": "FR-34", "detail": ""})
        add(date(y, 1, 31), "法定調書合計表・源泉徴収票の提出、給与支払報告書の提出、償却資産申告", "OUT-17/20/21")

    for p in periods:
        ps, pe = date.fromisoformat(p["start_date"]), date.fromisoformat(p["end_date"])
        add(_month_end(add_months(pe, 2)), f"法人税・地方税・消費税の確定申告と納付（{p['start_date']}〜{p['end_date']}）", "FR-64",
            "申告期限の延長の特例を受けている場合は、法人税・地方税は1か月延長されます")
        if p["id"] in interim_required_period_ids:
            add(_month_end(add_months(ps, 7)), f"中間申告と納付（{p['start_date']}開始の事業年度）", "BR-092")
        add(add_months(ps, 3) - timedelta(days=1), f"役員報酬の改定期限（{p['start_date']}開始の事業年度）", "BR-031",
            "期首から3か月以内の改定であれば定期同額給与として扱われます")

    items.sort(key=lambda x: x["date"])
    return items
