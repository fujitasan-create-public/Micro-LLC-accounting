"""銀行・カード明細 CSV の解析と科目推定（FR-13）。"""

from __future__ import annotations

import csv
import io
import re
from datetime import date

HEADER_ALIASES = {
    "date": ["日付", "取引日", "お取引日", "利用日", "ご利用日", "年月日", "date"],
    "description": ["摘要", "内容", "お取引内容", "取引内容", "利用店名", "ご利用店名", "ご利用先", "description", "memo"],
    "withdrawal": ["出金", "出金額", "お支払金額", "お引出し", "支払金額", "利用金額", "ご利用金額", "withdrawal", "debit"],
    "deposit": ["入金", "入金額", "お預り金額", "お預入れ", "deposit", "credit"],
    "amount": ["金額", "amount"],
}


def decode(data: bytes) -> str:
    for enc in ("utf-8-sig", "cp932", "shift_jis"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _parse_date(s: str) -> date | None:
    s = s.strip()
    m = re.match(r"^(\d{4})[/\-.年](\d{1,2})[/\-.月](\d{1,2})", s)
    if m:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = re.match(r"^(\d{4})(\d{2})(\d{2})$", s)
    if m:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return None


def _parse_amount(s: str | None) -> int | None:
    if s is None:
        return None
    t = s.strip().replace(",", "").replace("¥", "").replace("円", "").replace("\\", "")
    if t in ("", "-"):
        return None
    try:
        return int(float(t))
    except ValueError:
        return None


def _find_columns(header: list[str]) -> dict[str, int]:
    cols: dict[str, int] = {}
    norm = [h.strip().lower() for h in header]
    for key, aliases in HEADER_ALIASES.items():
        for i, h in enumerate(norm):
            if any(h == a.lower() or a.lower() in h for a in aliases):
                cols.setdefault(key, i)
                break
    return cols


def parse(text: str, is_credit_card: bool = False) -> tuple[list[dict], list[str]]:
    """返り値: ([{row_no, transaction_date, description, amount, direction}], エラー)"""
    reader = list(csv.reader(io.StringIO(text)))
    header_idx = None
    cols: dict[str, int] = {}
    for i, row in enumerate(reader[:10]):
        c = _find_columns(row)
        if "date" in c and ("withdrawal" in c or "deposit" in c or "amount" in c):
            header_idx, cols = i, c
            break
    if header_idx is None:
        return [], ["ヘッダー行（日付・摘要・出金／入金 または 金額）が見つかりません"]

    rows, errors = [], []
    for n, row in enumerate(reader[header_idx + 1:], start=header_idx + 2):
        if not row or all(not x.strip() for x in row):
            continue
        get = lambda k: row[cols[k]] if k in cols and cols[k] < len(row) else None  # noqa: E731
        d = _parse_date(get("date") or "")
        if d is None:
            errors.append(f"{n}行目: 日付を読み取れません")
            continue
        desc = (get("description") or "").strip()
        wd, dp, amt = _parse_amount(get("withdrawal")), _parse_amount(get("deposit")), _parse_amount(get("amount"))
        if wd:
            direction, amount = "out", wd
        elif dp:
            direction, amount = "in", dp
        elif amt is not None and amt != 0:
            if is_credit_card:
                direction, amount = ("out", amt) if amt > 0 else ("in", -amt)
            else:
                direction, amount = ("in", amt) if amt > 0 else ("out", -amt)
        else:
            continue
        rows.append({"row_no": n, "transaction_date": d.isoformat(), "description": desc,
                     "amount": amount, "direction": direction})
    return rows, errors


def match_rule(description: str, rules: list[dict]) -> dict | None:
    """摘要にキーワードを含むルールのうち、優先度（小さいほど優先）→キーワードの長い順で最初のもの。"""
    hits = [r for r in rules if r["keyword"] and r["keyword"].lower() in description.lower()]
    if not hits:
        return None
    return sorted(hits, key=lambda r: (r["priority"], -len(r["keyword"])))[0]
