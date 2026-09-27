"""仕訳の組み立てと検証（FR-10〜12, FR-15, FR-17、設計書 5.4）。

入力された金額の扱い:
- 税込経理（tax_included）: 明細の金額は税込。tax_amount は内税として計算して記録する。
- 税抜経理（tax_excluded）: 入力は税込で受け取り、本体（税抜）と仮払消費税等／仮受消費税等に分けて記録する。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_DOWN, Decimal
from typing import Any

from domain.rules import br022_invoice_transitional as br022
from domain.rules import br041_individual_fee_withholding as br041
from domain.rules import br071_entertainment as br071

INPUT_TAX_ACCOUNT = "160"   # 仮払消費税等
OUTPUT_TAX_ACCOUNT = "245"  # 仮受消費税等
TAX_ACCOUNTS = {INPUT_TAX_ACCOUNT, OUTPUT_TAX_ACCOUNT}


class JournalValidationError(Exception):
    def __init__(self, code: str, message: str, rule_id: str | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.rule_id = rule_id


@dataclass
class LineIn:
    side: str
    account_code: str
    amount: int
    tax_code: str | None = None
    tax_amount: int | None = None


@dataclass
class BuiltLine:
    line_no: int
    side: str
    account_code: str
    amount: int
    tax_code: str
    tax_amount: int
    deductible_rate_pct: int | None


@dataclass
class BuildResult:
    lines: list[BuiltLine]
    warnings: list[dict] = field(default_factory=list)
    entertainment: dict | None = None


def included_tax(gross: int, rate: str | None) -> int:
    """税込金額に含まれる消費税額（1円未満切捨て）。"""
    if not rate:
        return 0
    r = Decimal(rate)
    return int((Decimal(gross) * r / (Decimal(1) + r)).to_integral_value(rounding=ROUND_DOWN))


def validate_balance(lines: list[BuiltLine] | list[LineIn]) -> None:
    """FR-11: 借方合計と貸方合計の一致。"""
    debit = sum(ln.amount for ln in lines if ln.side == "debit")
    credit = sum(ln.amount for ln in lines if ln.side == "credit")
    if not any(ln.side == "debit" for ln in lines) or not any(ln.side == "credit" for ln in lines):
        raise JournalValidationError("unbalanced", "借方と貸方の両方に明細が必要です", "FR-11")
    if debit != credit:
        raise JournalValidationError(
            "unbalanced", f"借方合計（{debit:,}円）と貸方合計（{credit:,}円）が一致しません", "FR-11")
    if debit <= 0:
        raise JournalValidationError("zero_amount", "金額が0円の仕訳は登録できません", "FR-11")


def build_lines(
    *,
    lines_in: list[LineIn],
    transaction_date: date,
    accounts: dict[str, dict[str, Any]],
    tax_codes: dict[str, dict[str, Any]],
    counterparty: dict[str, Any] | None,
    accounting_tax_method: str,
    transitional_schedule: list[tuple[date, date | None, Any]],
    entertainment_detail: dict | None = None,
    entertainment_limit: int = 10_000,
    fee_withholding_params: dict | None = None,
) -> BuildResult:
    warnings: list[dict] = []
    if not lines_in:
        raise JournalValidationError("no_lines", "明細を入力してください")

    # 入力段階でも借貸一致を確認（税抜経理の分割は借貸それぞれの内部で行うので一致は保たれる）
    validate_balance(lines_in)

    has_invoice = bool(counterparty and counterparty.get("invoice_registration_number"))
    built: list[BuiltLine] = []
    extra: list[BuiltLine] = []

    for ln in lines_in:
        acct = accounts.get(ln.account_code)
        if not acct:
            raise JournalValidationError("invalid_account", f"勘定科目 {ln.account_code} が存在しません")
        if not acct["is_active"]:
            raise JournalValidationError("inactive_account", f"勘定科目「{acct['name']}」は非表示（無効）です")
        if ln.amount < 0:
            raise JournalValidationError("negative_amount", "金額は0以上で入力してください")
        if acct["requires_counterparty"] and not counterparty:
            raise JournalValidationError(
                "counterparty_required", f"勘定科目「{acct['name']}」では取引先の入力が必要です", "DM-08")

        tax_code = ln.tax_code or acct["default_tax_code"]
        tc = tax_codes.get(tax_code)
        if not tc:
            raise JournalValidationError("invalid_tax_code", f"税区分 {tax_code} が存在しません")

        # FR-12 / BR-022: 取引先にインボイス登録番号が無ければ経過措置の区分にする
        if tc["kind"] == "taxable_purchase" and counterparty is not None:
            new_code = br022.purchase_tax_code_for(tax_code, has_invoice)
            if new_code != tax_code and new_code in tax_codes:
                if not has_invoice:
                    warnings.append({
                        "rule_id": "BR-022",
                        "message": f"取引先「{counterparty['name']}」にインボイス登録番号が無いため、税区分を経過措置（{tax_codes[new_code]['name']}）にしました",
                    })
                tax_code = new_code
                tc = tax_codes[new_code]

        deductible = None
        if tc["kind"] == "taxable_purchase":
            deductible = br022.deductible_rate_pct(
                transaction_date, tc["invoice_status"] == "qualified", transitional_schedule)

        is_taxable = tc["kind"] in ("taxable_sales", "taxable_purchase") and tc["rate"]
        tax = ln.tax_amount if ln.tax_amount is not None else (included_tax(ln.amount, tc["rate"]) if is_taxable else 0)
        if tax < 0 or tax > ln.amount:
            raise JournalValidationError("invalid_tax_amount", "消費税額が正しくありません")

        if accounting_tax_method == "tax_excluded" and is_taxable and tax > 0 and ln.account_code not in TAX_ACCOUNTS:
            built.append(BuiltLine(0, ln.side, ln.account_code, ln.amount - tax, tax_code, tax, deductible))
            tax_account = OUTPUT_TAX_ACCOUNT if tc["kind"] == "taxable_sales" else INPUT_TAX_ACCOUNT
            extra.append(BuiltLine(0, ln.side, tax_account, tax, "NT", 0, None))
        else:
            built.append(BuiltLine(0, ln.side, ln.account_code, ln.amount, tax_code, tax, deductible))

        # BR-041: 個人への報酬
        w = br041.warning_if_needed(ln.account_code, counterparty.get("entity_type") if counterparty else None,
                                    ln.amount, fee_withholding_params)
        if w and ln.side == "debit":
            warnings.append(w)

    all_lines = built + extra
    for i, bl in enumerate(all_lines, start=1):
        bl.line_no = i
    validate_balance(all_lines)

    # BR-071 / FR-17: 交際費
    entertainment = None
    ent_total = sum(ln.amount for ln in lines_in
                    if ln.account_code == br071.ENTERTAINMENT_ACCOUNT_CODE and ln.side == "debit")
    if ent_total > 0:
        result = br071.evaluate(ent_total, entertainment_detail, entertainment_limit)
        warnings.extend(result["warnings"])
        if entertainment_detail:
            entertainment = {**entertainment_detail, "per_person_amount": result["per_person"],
                             "excludable_food_expense": result["excludable"]}

    return BuildResult(lines=all_lines, warnings=warnings, entertainment=entertainment)


def reverse_lines(lines: list[dict[str, Any]]) -> list[BuiltLine]:
    """逆仕訳の明細（貸借を入れ替える）。"""
    out = []
    for i, ln in enumerate(sorted(lines, key=lambda x: x["line_no"]), start=1):
        out.append(BuiltLine(i, "credit" if ln["side"] == "debit" else "debit", ln["account_code"], ln["amount"],
                             ln["tax_code"], ln["tax_amount"], ln.get("deductible_rate_pct")))
    return out
