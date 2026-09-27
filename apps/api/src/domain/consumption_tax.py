"""消費税の納付額の計算（FR-61）と集計表（OUT-16）。

計算は「割戻し計算」を前提とする。【要確認】積上げ計算・売上の積上げは未対応。
- 課税標準額: 税率ごとの税込対価 × 100/(100+税率) を 1,000円未満切捨て
- 消費税額（国税）: 課税標準額 × 7.8%（軽減税率は 6.24%）
- 控除対象仕入税額（本則）: 税率ごとの税込仕入 × 7.8/110（6.24/108）× 控除率（経過措置）
- 簡易課税: 売上税額 × みなし仕入率、2割特例: 売上税額 × 80%
- 差引税額は100円未満切捨て、地方消費税は差引税額 × 22/78（100円未満切捨て）
"""

from __future__ import annotations

from decimal import ROUND_DOWN, Decimal

NATIONAL_RATE = {"0.10": Decimal("0.078"), "0.08": Decimal("0.0624")}


def _floor(x: Decimal, unit: int = 1) -> int:
    v = int(x.to_integral_value(rounding=ROUND_DOWN))
    return v // unit * unit


def summarize(rows: list[dict], accounting_tax_method: str) -> dict:
    """tax_code_totals の行から、税率別・控除率別の税込金額を作る。"""
    sales: dict[str, int] = {}
    exempt_sales = 0
    purchases: dict[tuple[str, int], int] = {}
    for r in rows:
        if r["kind"] == "taxable_sales":
            net_amount = r["credit_amount"] - r["debit_amount"]
            net_tax = r["credit_tax"] - r["debit_tax"]
            gross = net_amount + (net_tax if accounting_tax_method == "tax_excluded" else 0)
            sales[r["rate"]] = sales.get(r["rate"], 0) + gross
        elif r["kind"] == "exempt_sales":
            exempt_sales += r["credit_amount"] - r["debit_amount"]
        elif r["kind"] == "taxable_purchase":
            net_amount = r["debit_amount"] - r["credit_amount"]
            net_tax = r["debit_tax"] - r["credit_tax"]
            gross = net_amount + (net_tax if accounting_tax_method == "tax_excluded" else 0)
            key = (r["rate"], int(r["deductible_rate_pct"]))
            purchases[key] = purchases.get(key, 0) + gross
    return {"sales_gross_by_rate": sales, "exempt_sales": exempt_sales, "purchases_gross_by_rate_and_pct": purchases}


def calculate(summary: dict, *, taxable_status: str, method: str, deemed_pct: int | None = None,
              two_tenths_pct: int = 80) -> dict:
    if taxable_status == "exempt":
        return {"taxable_status": "exempt", "payable_total": 0, "message": "免税事業者のため納付税額はありません"}

    sales_lines = []
    sales_tax = Decimal(0)
    for rate, gross in sorted(summary["sales_gross_by_rate"].items(), reverse=True):
        r = Decimal(rate)
        base = _floor(Decimal(gross) / (Decimal(1) + r), 1000)
        tax = Decimal(base) * NATIONAL_RATE[rate]
        sales_tax += tax
        sales_lines.append({"rate": rate, "gross": gross, "tax_base": base, "national_tax": _floor(tax)})
    sales_tax_int = _floor(sales_tax)

    purchase_lines = []
    if method == "standard":
        deductible = Decimal(0)
        for (rate, pct), gross in sorted(summary["purchases_gross_by_rate_and_pct"].items(), reverse=True):
            r = Decimal(rate)
            full = Decimal(gross) * NATIONAL_RATE[rate] / (Decimal(1) + r)
            ded = full * Decimal(pct) / Decimal(100)
            deductible += ded
            purchase_lines.append({"rate": rate, "deductible_rate_pct": pct, "gross": gross, "deductible_national_tax": _floor(ded)})
        deductible_int = _floor(deductible)
        basis = "本則課税（割戻し計算）"
    elif method == "simplified":
        deductible_int = _floor(Decimal(sales_tax_int) * Decimal(deemed_pct or 0) / Decimal(100))
        basis = f"簡易課税（みなし仕入率 {deemed_pct}%）"
    elif method == "two_tenths_special":
        deductible_int = _floor(Decimal(sales_tax_int) * Decimal(two_tenths_pct) / Decimal(100))
        basis = f"2割特例（売上税額の{two_tenths_pct}%を控除）"
    else:
        raise ValueError(method)

    diff = sales_tax_int - deductible_int
    national = _floor(Decimal(diff), 100) if diff >= 0 else -_floor(Decimal(-diff))
    local = _floor(Decimal(national) * Decimal(22) / Decimal(78), 100) if national >= 0 else -_floor(Decimal(-national) * Decimal(22) / Decimal(78))
    return {
        "taxable_status": "taxable",
        "method": method,
        "basis": basis,
        "sales": sales_lines,
        "purchases": purchase_lines,
        "exempt_sales": summary["exempt_sales"],
        "sales_national_tax": sales_tax_int,
        "deductible_national_tax": deductible_int,
        "national_tax": national,
        "local_tax": local,
        "payable_total": national + local,
        "is_refund": national < 0,
    }
