"""設定値（BR-000）の選択。判定日で有効な値を返す純粋関数。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any


@dataclass(frozen=True)
class SettingRow:
    key: str
    value: Any
    effective_from: date
    effective_to: date | None


def pick_value(rows: list[SettingRow], on: date, default: Any = None) -> Any:
    candidates = [r for r in rows if r.effective_from <= on and (r.effective_to is None or on <= r.effective_to)]
    if not candidates:
        return default
    # 期間が重なる場合は開始日の新しいものを優先
    return max(candidates, key=lambda r: r.effective_from).value


def schedule_of(rows: list[SettingRow]) -> list[tuple[date, date | None, Any]]:
    return [(r.effective_from, r.effective_to, r.value) for r in sorted(rows, key=lambda r: r.effective_from)]
