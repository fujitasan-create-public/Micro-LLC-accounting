"""年末調整の計算（FR-34）。役員1名・主たる給与のみを前提とした簡易計算。

未対応: 配偶者特別控除、障害者控除・寡婦控除・ひとり親控除・勤労学生控除、所得金額調整控除、
給与所得控除の「所得税法別表第五」による端数調整（660万円未満）。
"""

from __future__ import annotations

from datetime import date
from decimal import ROUND_DOWN, Decimal

from domain.payroll import age_on


def _floor(x: Decimal) -> int:
    return int(x.to_integral_value(rounding=ROUND_DOWN))


def employment_income(gross: int, table: list[dict]) -> int:
    for b in table:
        if b["upto"] is None or gross <= int(b["upto"]):
            deduction = int(b["fixed"]) if "fixed" in b else _floor(Decimal(gross) * Decimal(b["rate"]) + int(b["add"]))
            return max(gross - deduction, 0)
    return gross


def basic_deduction(total_income: int, table: list[dict]) -> int:
    for b in table:
        if b["upto"] is None or total_income <= int(b["upto"]):
            return int(b["amount"])
    return 0


def life_insurance_deduction(inputs: dict) -> int:
    """新制度: 一般・介護医療・個人年金それぞれ最大4万円、合計12万円。inputs = {general, medical, pension}（年間保険料）"""
    def one(p: int) -> int:
        if p <= 20_000:
            return p
        if p <= 40_000:
            return p // 2 + 10_000
        if p <= 80_000:
            return p // 4 + 20_000
        return 40_000

    total = sum(one(int(inputs.get(k) or 0)) for k in ("general", "medical", "pension"))
    return min(total, 120_000)


def dependent_deduction(dependents: list[dict], year: int, params: dict) -> int:
    year_end = date(year, 12, 31)
    total = 0
    for d in dependents:
        if d.get("relation") == "spouse" or not d.get("birth_date"):
            continue
        if int(d.get("income") or 0) > int(params["dependent_income_limit"]):
            continue
        age = age_on(date.fromisoformat(d["birth_date"]), year_end)
        if age < 16:
            continue
        if 19 <= age <= 22:
            total += int(params["specific"])
        elif age >= 70:
            total += int(params["elderly_cohabiting"] if d.get("cohabiting_parent") else params["elderly"])
        else:
            total += int(params["general"])
    return total


def income_tax(taxable: int, brackets: list[dict]) -> int:
    for b in brackets:
        if b["upto"] is None or taxable <= int(b["upto"]):
            return max(_floor(Decimal(taxable) * Decimal(b["rate"])) - int(b["deduct"]), 0)
    return 0


def calculate(*, year: int, gross_total: int, social_insurance_withheld: int, withheld_tax_total: int,
              dependents: list[dict], inputs: dict, settings: dict) -> dict:
    emp_income = employment_income(gross_total, settings["employment_income_deduction"])
    social = social_insurance_withheld + int(inputs.get("social_insurance_paid_personally") or 0)
    mutual_aid = int(inputs.get("small_business_mutual_aid_premium") or 0)
    life = life_insurance_deduction(inputs.get("life_insurance_deduction_inputs") or {})
    quake = min(int(inputs.get("earthquake_insurance_premium") or 0), int(settings["earthquake_cap"]))
    dp = settings["dependent_deductions"]
    spouse = 0
    spouse_income = inputs.get("spouse_income")
    if spouse_income is None:
        spouse_income = next((d.get("income") or 0 for d in dependents if d.get("relation") == "spouse"), None)
    if spouse_income is not None and int(spouse_income) <= int(dp["spouse_income_limit"]) \
            and emp_income <= int(dp["taxpayer_income_limit_for_spouse"]):
        spouse = int(dp["spouse"])
    dependents_amt = dependent_deduction(dependents, year, dp)
    basic = basic_deduction(emp_income, settings["basic_deduction"])

    deductions = social + mutual_aid + life + quake + spouse + dependents_amt + basic
    taxable = max(emp_income - deductions, 0) // 1000 * 1000
    calc_tax = income_tax(taxable, settings["income_tax_brackets"])
    after_credit = max(calc_tax - int(inputs.get("housing_loan_deduction") or 0), 0)
    annual_tax = _floor(Decimal(after_credit) * (Decimal(1) + Decimal(settings["reconstruction_rate"]))) // 100 * 100
    return {
        "year": year,
        "gross_total": gross_total,
        "employment_income": emp_income,
        "deductions": {
            "social_insurance": social, "small_business_mutual_aid": mutual_aid, "life_insurance": life,
            "earthquake_insurance": quake, "spouse": spouse, "dependents": dependents_amt, "basic": basic,
            "total": deductions,
        },
        "taxable_income": taxable,
        "calculated_tax": calc_tax,
        "housing_loan_deduction": int(inputs.get("housing_loan_deduction") or 0),
        "annual_tax": annual_tax,
        "withheld_tax_total": withheld_tax_total,
        "difference": withheld_tax_total - annual_tax,  # 正なら還付、負なら追加徴収
        "is_estimate": True,
    }
