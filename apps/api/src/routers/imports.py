"""明細CSVの取込（FR-13）と定型仕訳（FR-14）。"""

from __future__ import annotations

import calendar
import json
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import BaseModel, Field

from common import AppError, get_db, new_id, not_found, now_iso
from db import Database
from domain import bank_csv
from domain.journal import LineIn
from repositories import masters
from repositories.base import insert, loads, update
from services import journals as svc

router = APIRouter(prefix="/api/v1")


# ---------------------------------------------------------------------------
# 科目推定ルール
# ---------------------------------------------------------------------------


class ImportRuleIn(BaseModel):
    keyword: str = Field(min_length=1)
    account_code: str
    tax_code: str | None = None
    counterparty_id: str | None = None
    priority: int = 100


@router.get("/import-rules")
async def list_rules(db: Database = Depends(get_db)):
    return {"items": await db.all(
        """SELECT r.*, a.name AS account_name, cp.name AS counterparty_name FROM import_rules r
           JOIN accounts a ON a.code = r.account_code LEFT JOIN counterparties cp ON cp.id = r.counterparty_id
           ORDER BY r.priority, r.keyword""")}


@router.post("/import-rules", status_code=201)
async def create_rule(body: ImportRuleIn, db: Database = Depends(get_db)):
    if not await masters.get_account(db, body.account_code):
        raise AppError(422, "invalid_account", "勘定科目が存在しません")
    rid = new_id()
    await insert(db, "import_rules", {"id": rid, **body.model_dump(), "created_at": now_iso()})
    return {"id": rid}


@router.delete("/import-rules/{rule_id}")
async def delete_rule(rule_id: str, db: Database = Depends(get_db)):
    # 推定ルールは帳簿ではないため物理削除してよい
    await db.run("DELETE FROM import_rules WHERE id = ?", [rule_id])
    return {"ok": True}


# ---------------------------------------------------------------------------
# CSV 取込: 候補の作成 → 確認後に登録
# ---------------------------------------------------------------------------


@router.post("/imports/bank-csv")
async def import_bank_csv(
    file: UploadFile = File(...),
    payment_account_id: str = Form(...),
    db: Database = Depends(get_db),
):
    pa = await masters.get_payment_account(db, payment_account_id)
    if not pa:
        raise not_found("口座・支払手段")
    text = bank_csv.decode(await file.read())
    rows, errors = bank_csv.parse(text, is_credit_card=pa["type"] == "credit_card")
    rules = await db.all("SELECT * FROM import_rules")
    accounts = {a["code"]: a for a in await masters.list_accounts(db)}
    # 既に取り込んだ明細と同じ（日付・金額・摘要）ものは重複候補として印を付ける
    existing = await db.all(
        """SELECT je.transaction_date, je.description,
                  (SELECT SUM(amount) FROM journal_lines WHERE entry_id = je.id AND side = 'debit') AS total
           FROM journal_entries je WHERE je.source = 'csv_import' AND je.payment_account_id = ? AND je.voided_at IS NULL""",
        [payment_account_id],
    )
    seen = {(e["transaction_date"], e["description"], e["total"]) for e in existing}
    candidates = []
    for r in rows:
        rule = bank_csv.match_rule(r["description"], rules)
        acct = rule["account_code"] if rule else None
        candidates.append({
            **r,
            "account_code": acct,
            "tax_code": (rule.get("tax_code") if rule else None) or (accounts[acct]["default_tax_code"] if acct else None),
            "counterparty_id": rule.get("counterparty_id") if rule else None,
            "matched_rule": rule["keyword"] if rule else None,
            "duplicate": (r["transaction_date"], r["description"], r["amount"]) in seen,
        })
    return {"payment_account": pa, "candidates": candidates, "errors": errors}


class CandidateIn(BaseModel):
    transaction_date: date
    description: str = Field(min_length=1)
    amount: int = Field(gt=0)
    direction: Literal["in", "out"]
    account_code: str
    tax_code: str | None = None
    counterparty_id: str | None = None


class CommitIn(BaseModel):
    payment_account_id: str
    candidates: list[CandidateIn]


@router.post("/imports/bank-csv/commit")
async def commit_candidates(body: CommitIn, db: Database = Depends(get_db)):
    pa = await masters.get_payment_account(db, body.payment_account_id)
    if not pa:
        raise not_found("口座・支払手段")
    created, failed, warnings = [], [], []
    for i, c in enumerate(body.candidates):
        counter_side = "debit" if c.direction == "out" else "credit"
        own_side = "credit" if c.direction == "out" else "debit"
        try:
            eid, w = await svc.create_entry(
                db, transaction_date=c.transaction_date, description=c.description, source="csv_import",
                counterparty_id=c.counterparty_id or None, payment_account_id=pa["id"],
                lines=[LineIn(counter_side, c.account_code, c.amount, c.tax_code),
                       LineIn(own_side, pa["linked_account_code"], c.amount, "NT")],
            )
            created.append(eid)
            warnings.extend(w)
        except AppError as e:
            failed.append({"index": i, "message": e.message})
    return {"created": created, "failed": failed, "warnings": warnings}


# ---------------------------------------------------------------------------
# 定型仕訳（FR-14）
# ---------------------------------------------------------------------------


class TemplateLine(BaseModel):
    side: Literal["debit", "credit"]
    account_code: str
    amount: int = Field(ge=0)
    tax_code: str | None = None


class TemplateIn(BaseModel):
    name: str = Field(min_length=1)
    day_of_month: int = Field(ge=1, le=31)
    description: str = Field(min_length=1)
    counterparty_id: str | None = None
    payment_account_id: str | None = None
    lines: list[TemplateLine] = Field(min_length=2)
    is_active: bool = True


class GenerateIn(BaseModel):
    year_month: str = Field(pattern=r"^\d{4}-\d{2}$")


def _template_out(t: dict) -> dict:
    t = dict(t)
    t["lines"] = loads(t.pop("lines_json"), [])
    return t


@router.get("/recurring-templates")
async def list_templates(db: Database = Depends(get_db)):
    rows = await db.all("SELECT * FROM recurring_templates ORDER BY day_of_month, name")
    return {"items": [_template_out(r) for r in rows]}


@router.post("/recurring-templates", status_code=201)
async def create_template(body: TemplateIn, db: Database = Depends(get_db)):
    debit = sum(ln.amount for ln in body.lines if ln.side == "debit")
    credit = sum(ln.amount for ln in body.lines if ln.side == "credit")
    if debit != credit:
        raise AppError(422, "unbalanced", "借方合計と貸方合計が一致しません", "FR-11")
    now = now_iso()
    tid = new_id()
    data = body.model_dump()
    data["lines_json"] = json.dumps(data.pop("lines"), ensure_ascii=False)
    data["counterparty_id"] = data["counterparty_id"] or None
    data["payment_account_id"] = data["payment_account_id"] or None
    await insert(db, "recurring_templates", {"id": tid, **data, "created_at": now, "updated_at": now})
    return {"id": tid}


@router.patch("/recurring-templates/{tid}")
async def toggle_template(tid: str, is_active: bool, db: Database = Depends(get_db)):
    await update(db, "recurring_templates", "id", tid, {"is_active": is_active, "updated_at": now_iso()})
    return {"ok": True}


@router.post("/recurring-templates/generate")
async def generate(body: GenerateIn, db: Database = Depends(get_db)):
    """指定した月の定型仕訳をまとめて作る。同じ月に作成済みのテンプレートは飛ばす。"""
    y, m = int(body.year_month[:4]), int(body.year_month[5:])
    templates = await db.all("SELECT * FROM recurring_templates WHERE is_active = 1")
    done = {r["template_id"] for r in await db.all("SELECT template_id FROM recurring_runs WHERE year_month = ?", [body.year_month])}
    created, skipped, failed, warnings = [], [], [], []
    for t in templates:
        if t["id"] in done:
            skipped.append(t["name"])
            continue
        d = date(y, m, min(t["day_of_month"], calendar.monthrange(y, m)[1]))
        lines = [LineIn(ln["side"], ln["account_code"], ln["amount"], ln.get("tax_code")) for ln in loads(t["lines_json"], [])]
        try:
            eid, w = await svc.create_entry(
                db, transaction_date=d, description=t["description"], lines=lines, source="recurring",
                counterparty_id=t["counterparty_id"], payment_account_id=t["payment_account_id"],
                extra_statements=lambda entry_id, t=t: [(
                    "INSERT INTO recurring_runs (template_id, year_month, journal_entry_id, created_at) VALUES (?, ?, ?, ?)",
                    [t["id"], body.year_month, entry_id, now_iso()])],
            )
            created.append(eid)
            warnings.extend(w)
        except AppError as e:
            failed.append({"name": t["name"], "message": e.message})
    return {"created": created, "skipped": skipped, "failed": failed, "warnings": warnings}
