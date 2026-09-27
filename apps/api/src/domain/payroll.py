"""給与（FR-31, FR-32）。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from domain.journal import BuiltLine

OFFICER_COMP = "500"         # 役員報酬
LEGAL_WELFARE = "510"        # 法定福利費
ACCRUED_EXPENSES = "210"     # 未払費用
WITHHOLDING_PAYABLE = "220"  # 預り金（源泉所得税）
RESIDENT_PAYABLE = "221"     # 預り金（住民税）
SOCIAL_PAYABLE = "222"       # 預り金（社会保険料）
RENT = "520"                 # 地代家賃（社宅家賃の徴収分を戻す）

# 源泉控除対象配偶者・扶養親族の所得要件（2025年分以後）。設定値で上書きできるよう引数にしている
SPOUSE_WITHHOLDING_INCOME_LIMIT = 950_000
DEPENDENT_INCOME_LIMIT = 580_000


@dataclass
class PayrollInput:
    gross_amount: int
    health_insurance_employee: int
    pension_employee: int
    health_insurance_employer: int
    pension_employer: int
    withholding_income_tax: int
    resident_tax: int
    company_housing_deduction: int = 0


def net_amount(p: PayrollInput) -> int:
    return (p.gross_amount - p.health_insurance_employee - p.pension_employee
            - p.withholding_income_tax - p.resident_tax - p.company_housing_deduction)


def taxable_after_social_insurance(p: PayrollInput) -> int:
    """源泉徴収税額表を引くときの「社会保険料等控除後の給与等の金額」。"""
    return p.gross_amount - p.health_insurance_employee - p.pension_employee


def journal_lines(p: PayrollInput, bank_account_code: str) -> list[BuiltLine]:
    """FR-31: 役員報酬・法定福利費（会社負担分は未払費用に計上）・預り金の仕訳。"""
    net = net_amount(p)
    employer = p.health_insurance_employer + p.pension_employer
    employee_si = p.health_insurance_employee + p.pension_employee
    raw: list[tuple[str, str, int, str]] = [("debit", OFFICER_COMP, p.gross_amount, "NT")]
    if employer:
        raw.append(("debit", LEGAL_WELFARE, employer, "NT"))
    if employee_si:
        raw.append(("credit", SOCIAL_PAYABLE, employee_si, "NT"))
    if p.withholding_income_tax:
        raw.append(("credit", WITHHOLDING_PAYABLE, p.withholding_income_tax, "NT"))
    if p.resident_tax:
        raw.append(("credit", RESIDENT_PAYABLE, p.resident_tax, "NT"))
    if p.company_housing_deduction:
        # 住宅の家賃は非課税（FR-42）
        raw.append(("credit", RENT, p.company_housing_deduction, "PEX"))
    if employer:
        raw.append(("credit", ACCRUED_EXPENSES, employer, "NT"))
    if net:
        raw.append(("credit", bank_account_code, net, "NT"))
    return [BuiltLine(i, s, a, amt, tc, 0, None) for i, (s, a, amt, tc) in enumerate(raw, start=1)]


def age_on(birth: date, on: date) -> int:
    return on.year - birth.year - ((on.month, on.day) < (birth.month, birth.day))


def withholding_dependents_count(dependents: list[dict], on: date,
                                 spouse_limit: int = SPOUSE_WITHHOLDING_INCOME_LIMIT,
                                 dependent_limit: int = DEPENDENT_INCOME_LIMIT) -> int:
    """扶養親族等の数（源泉控除対象配偶者 + 16歳以上の控除対象扶養親族）。年齢は12月31日現在で判定する。"""
    year_end = date(on.year, 12, 31)
    n = 0
    for d in dependents:
        income = int(d.get("income") or 0)
        if d.get("relation") == "spouse":
            if income <= spouse_limit:
                n += 1
            continue
        birth = d.get("birth_date")
        if birth and income <= dependent_limit and age_on(date.fromisoformat(birth), year_end) >= 16:
            n += 1
    return n


def lookup_withholding(rows: list[dict], amount: int, dependents: int) -> int | None:
    """月額表・甲欄の行データ（min_amount 以上 max_amount 未満）から税額を引く。7人を超える場合は7人の欄を使う。"""
    dep = min(dependents, 7)
    for r in rows:
        if r["dependents"] != dep:
            continue
        if r["min_amount"] <= amount and (r["max_amount"] is None or amount < r["max_amount"]):
            return int(r["tax_amount"])
    return None
