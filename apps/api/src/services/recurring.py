"""定型仕訳の計上。月を指定しての一括作成と、計上日が来たものの自動計上（家賃・口座振替など）。"""

from __future__ import annotations

import calendar
from datetime import date

from common import AppError, now_iso
from db import Database
from domain.journal import LineIn
from repositories.base import loads
from services import journals as svc


def _months(start: str, end: str) -> list[str]:
    y, m = int(start[:4]), int(start[5:7])
    out = []
    while f"{y:04d}-{m:02d}" <= end:
        out.append(f"{y:04d}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def posting_date(template: dict, year_month: str) -> date:
    y, m = int(year_month[:4]), int(year_month[5:7])
    return date(y, m, min(template["day_of_month"], calendar.monthrange(y, m)[1]))


async def post_month(db: Database, template: dict, year_month: str) -> tuple[str, list[dict]]:
    lines = [LineIn(ln["side"], ln["account_code"], ln["amount"], ln.get("tax_code")) for ln in loads(template["lines_json"], [])]
    return await svc.create_entry(
        db, transaction_date=posting_date(template, year_month), description=template["description"], lines=lines,
        source="recurring", counterparty_id=template["counterparty_id"], payment_account_id=template["payment_account_id"],
        extra_statements=lambda entry_id: [(
            "INSERT INTO recurring_runs (template_id, year_month, journal_entry_id, created_at) VALUES (?, ?, ?, ?)",
            [template["id"], year_month, entry_id, now_iso()])],
    )


async def generate_month(db: Database, year_month: str) -> dict:
    templates = await db.all("SELECT * FROM recurring_templates WHERE is_active = 1")
    done = {r["template_id"] for r in await db.all("SELECT template_id FROM recurring_runs WHERE year_month = ?", [year_month])}
    created, skipped, failed, warnings = [], [], [], []
    for t in templates:
        if t["id"] in done:
            skipped.append(t["name"])
            continue
        try:
            eid, w = await post_month(db, t, year_month)
            created.append(eid)
            warnings.extend(w)
        except AppError as e:
            failed.append({"name": t["name"], "message": e.message})
    return {"created": created, "skipped": skipped, "failed": failed, "warnings": warnings}


async def auto_post(db: Database, today: date) -> dict:
    """計上日を過ぎた未計上の月を、自動計上の対象テンプレートについてすべて作る。締め済みの期間は飛ばす。"""
    templates = await db.all("SELECT * FROM recurring_templates WHERE is_active = 1 AND auto_post = 1")
    runs = await db.all("SELECT template_id, year_month FROM recurring_runs")
    done = {(r["template_id"], r["year_month"]) for r in runs}
    this_month = today.strftime("%Y-%m")
    created, failed = [], []
    for t in templates:
        start = t["start_month"] or t["created_at"][:7]
        end = min(t["end_month"] or this_month, this_month)
        for ym in _months(start, end):
            if (t["id"], ym) in done or posting_date(t, ym) > today:
                continue
            try:
                eid, _ = await post_month(db, t, ym)
                created.append({"name": t["name"], "year_month": ym, "entry_id": eid})
            except AppError as e:
                if e.code not in ("period_closed", "no_period"):
                    failed.append({"name": t["name"], "year_month": ym, "message": e.message})
    return {"created": created, "failed": failed}


async def upcoming(db: Database, today: date, cash_codes: set[str]) -> list[dict]:
    """自動計上の予定（次回の日付と、口座から出ていく額）。"""
    templates = await db.all("SELECT * FROM recurring_templates WHERE is_active = 1 AND auto_post = 1")
    runs = {(r["template_id"], r["year_month"]) for r in await db.all("SELECT template_id, year_month FROM recurring_runs")}
    out = []
    for t in templates:
        ym = today.strftime("%Y-%m")
        start = t["start_month"] or t["created_at"][:7]
        if ym < start:
            ym = start
        if (t["id"], ym) in runs or posting_date(t, ym) < today:
            y, m = int(ym[:4]), int(ym[5:7])
            y, m = (y + 1, 1) if m == 12 else (y, m + 1)
            ym = f"{y:04d}-{m:02d}"
        if t["end_month"] and ym > t["end_month"]:
            continue
        lines = loads(t["lines_json"], [])
        outflow = sum(ln["amount"] for ln in lines if ln["side"] == "credit" and ln["account_code"] in cash_codes)
        inflow = sum(ln["amount"] for ln in lines if ln["side"] == "debit" and ln["account_code"] in cash_codes)
        out.append({"name": t["name"], "date": posting_date(t, ym).isoformat(), "description": t["description"],
                    "outflow": outflow, "inflow": inflow})
    return sorted(out, key=lambda x: x["date"])
