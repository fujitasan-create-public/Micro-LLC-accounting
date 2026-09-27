"""売上請求と入金消込（FR-20〜22, BR-023, DM-10）。"""

from __future__ import annotations

import json
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from common import AppError, get_db, new_id, not_found, now_iso
from db import Database
from domain.journal import BuiltLine
from domain.rules.br023_invoice_requirements import missing_requirements, summarize_by_rate
from repositories import masters
from repositories.base import loads
from services import journals as svc

router = APIRouter(prefix="/api/v1")

AR_ACCOUNT = "130"      # 売掛金
SALES_ACCOUNT = "400"   # 売上高
FEE_ACCOUNT = "560"     # 支払手数料
RATE_TO_TAX_CODE = {"0.10": "S10", "0.08": "S08"}


class InvoiceLine(BaseModel):
    description: str = Field(min_length=1)
    amount: int = Field(ge=0, description="税抜金額")
    tax_rate: Literal["0.10", "0.08"] = "0.10"


class InvoiceIn(BaseModel):
    invoice_number: str | None = None
    client_id: str
    issue_date: date
    service_period: str = Field(min_length=1)
    lines: list[InvoiceLine] = Field(min_length=1)
    due_date: date


class ReceiptIn(BaseModel):
    received_date: date
    received_amount: int = Field(gt=0)
    payment_account_id: str
    treat_shortfall_as_fee: bool = True


async def _issuer_registration(db: Database, d: date) -> str | None:
    period = await masters.period_for_date(db, d.isoformat())
    if not period:
        return None
    ct = await masters.get_consumption_tax(db, period["id"])
    return ct["invoice_registration_number"] if ct else None


async def _invoice_out(db: Database, inv: dict) -> dict:
    inv = dict(inv)
    inv["lines"] = loads(inv.pop("lines_json"), [])
    inv["summary_by_rate"] = summarize_by_rate(inv["lines"])
    inv["client"] = await masters.get_counterparty(db, inv["client_id"])
    inv["remaining_amount"] = inv["total_amount"] - inv["received_amount"] - inv["bank_fee_deducted"]
    inv["receipts"] = await db.all(
        "SELECT * FROM sales_invoice_receipts WHERE invoice_id = ? ORDER BY received_date", [inv["id"]])
    return inv


async def _next_number(db: Database, issue_date: date) -> str:
    prefix = f"INV-{issue_date.strftime('%Y%m')}-"
    row = await db.first("SELECT COUNT(*) AS n FROM sales_invoices WHERE invoice_number LIKE ?", [prefix + "%"])
    return f"{prefix}{(row['n'] if row else 0) + 1:03d}"


@router.get("/sales-invoices")
async def list_invoices(status: str | None = None, db: Database = Depends(get_db)):
    where, params = "WHERE si.voided_at IS NULL", []
    if status:
        where += " AND si.status = ?"
        params.append(status)
    rows = await db.all(
        f"""SELECT si.*, cp.name AS client_name FROM sales_invoices si JOIN counterparties cp ON cp.id = si.client_id
            {where} ORDER BY si.issue_date DESC, si.invoice_number DESC""", params)
    for r in rows:
        r.pop("lines_json", None)
        r["remaining_amount"] = r["total_amount"] - r["received_amount"] - r["bank_fee_deducted"]
    return {"items": rows}


@router.get("/sales-invoices/{inv_id}")
async def get_invoice(inv_id: str, db: Database = Depends(get_db)):
    inv = await db.first("SELECT * FROM sales_invoices WHERE id = ?", [inv_id])
    if not inv:
        raise not_found("請求書")
    out = await _invoice_out(db, inv)
    out["issuer"] = await masters.get_company(db)
    out["issuer_registration_number"] = await _issuer_registration(db, date.fromisoformat(inv["issue_date"]))
    return out


@router.post("/sales-invoices", status_code=201)
async def create_invoice(body: InvoiceIn, db: Database = Depends(get_db)):
    client = await masters.get_counterparty(db, body.client_id)
    if not client:
        raise AppError(422, "invalid_client", "請求先が存在しません")
    company = await masters.get_company(db)
    reg = await _issuer_registration(db, body.issue_date)
    lines = [ln.model_dump() for ln in body.lines]
    warnings = []
    missing = missing_requirements(company["trade_name"] if company else None, reg, body.service_period, lines, client["name"])
    if missing:
        warnings.append({"rule_id": "BR-023",
                         "message": f"適格請求書の記載事項が不足しています（{'、'.join(missing)}）。適格請求書として扱われません"})

    summary = summarize_by_rate(lines)
    total = sum(s["gross_total"] for s in summary)
    if total <= 0:
        raise AppError(422, "zero_amount", "請求金額が0円です")
    number = body.invoice_number or await _next_number(db, body.issue_date)
    if await db.first("SELECT id FROM sales_invoices WHERE invoice_number = ?", [number]):
        raise AppError(409, "duplicate", f"請求書番号 {number} は既に使われています")

    # 売掛金／売上高（税率ごとに1行。消費税額は請求書と同じ端数処理の値を使う）
    company_method = company["accounting_tax_method"] if company else "tax_included"
    built = [BuiltLine(1, "debit", AR_ACCOUNT, total, "NT", 0, None)]
    for s in summary:
        code = RATE_TO_TAX_CODE[s["rate"]]
        if company_method == "tax_excluded":
            built.append(BuiltLine(0, "credit", SALES_ACCOUNT, s["net_total"], code, s["tax"], None))
            built.append(BuiltLine(0, "credit", "245", s["tax"], "NT", 0, None))
        else:
            built.append(BuiltLine(0, "credit", SALES_ACCOUNT, s["gross_total"], code, s["tax"], None))
    for i, b in enumerate(built, start=1):
        b.line_no = i

    inv_id = new_id()
    now = now_iso()

    def extra(entry_id: str):
        return [(
            """INSERT INTO sales_invoices (id, invoice_number, client_id, issue_date, service_period, lines_json, due_date,
                 status, total_amount, received_amount, bank_fee_deducted, journal_entry_id, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'issued', ?, 0, 0, ?, ?, ?)""",
            [inv_id, number, body.client_id, body.issue_date.isoformat(), body.service_period,
             json.dumps(lines, ensure_ascii=False), body.due_date.isoformat(), total, entry_id, now, now],
        )]

    await svc.create_entry(
        db, transaction_date=body.issue_date, description=f"請求書 {number} {client['name']}",
        lines=[], prebuilt=built, source="manual", counterparty_id=client["id"], extra_statements=extra,
    )
    return {"invoice": await get_invoice(inv_id, db), "warnings": warnings}


@router.post("/sales-invoices/{inv_id}/receipts")
async def receive(inv_id: str, body: ReceiptIn, db: Database = Depends(get_db)):
    """FR-22: 入金の消込。入金額が請求残高より少ない場合、差額を振込手数料（支払手数料）として処理できる。"""
    inv = await db.first("SELECT * FROM sales_invoices WHERE id = ? AND voided_at IS NULL", [inv_id])
    if not inv:
        raise not_found("請求書")
    pa = await masters.get_payment_account(db, body.payment_account_id)
    if not pa:
        raise not_found("口座・支払手段")
    remaining = inv["total_amount"] - inv["received_amount"] - inv["bank_fee_deducted"]
    if remaining <= 0:
        raise AppError(409, "already_paid", "この請求書は入金済みです")
    if body.received_amount > remaining:
        raise AppError(422, "over_receipt", f"入金額が請求残高（{remaining:,}円）を超えています")
    fee = remaining - body.received_amount if body.treat_shortfall_as_fee else 0
    cleared = body.received_amount + fee
    new_received = inv["received_amount"] + body.received_amount
    new_fee = inv["bank_fee_deducted"] + fee
    status = "paid" if new_received + new_fee >= inv["total_amount"] else "partially_paid"
    client = await masters.get_counterparty(db, inv["client_id"])

    from domain.journal import LineIn

    lines = [LineIn("debit", pa["linked_account_code"], body.received_amount, "NT")]
    if fee:
        lines.append(LineIn("debit", FEE_ACCOUNT, fee, "P10"))
    lines.append(LineIn("credit", AR_ACCOUNT, cleared, "NT"))
    now = now_iso()
    rid = new_id()

    def extra(entry_id: str):
        return [
            ("""INSERT INTO sales_invoice_receipts (id, invoice_id, received_date, received_amount, bank_fee,
                  payment_account_id, journal_entry_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
             [rid, inv_id, body.received_date.isoformat(), body.received_amount, fee, pa["id"], entry_id, now]),
            ("UPDATE sales_invoices SET received_amount = ?, bank_fee_deducted = ?, status = ?, updated_at = ? WHERE id = ?",
             [new_received, new_fee, status, now, inv_id]),
        ]

    _, warnings = await svc.create_entry(
        db, transaction_date=body.received_date, description=f"入金 請求書 {inv['invoice_number']} {client['name']}",
        lines=lines, source="manual", counterparty_id=inv["client_id"], payment_account_id=pa["id"],
        extra_statements=extra,
    )
    return {"invoice": await get_invoice(inv_id, db), "warnings": warnings}
