"""試算表・決算書（OUT-06, OUT-10〜13）の組み立て。入力は科目ごとの借方・貸方合計。"""

from __future__ import annotations

DEBIT_NATURE = {"asset", "expense"}
RETAINED_EARNINGS = "310"
TAX_EXPENSE = "700"

BS_SECTIONS = {
    "asset": ["流動資産", "有形固定資産", "無形固定資産", "投資その他の資産"],
    "liability": ["流動負債", "固定負債"],
    "equity": ["資本金", "利益剰余金"],
}
PL_ORDER = ["売上高", "売上原価", "販売費及び一般管理費", "営業外収益", "営業外費用", "特別利益", "特別損失", "法人税等"]


def balance_of(row: dict) -> int:
    """科目の性質に応じた残高（資産・費用は借方残、それ以外は貸方残を正とする）。"""
    if row["category"] in DEBIT_NATURE:
        return row["debit"] - row["credit"]
    return row["credit"] - row["debit"]


def trial_balance(rows: list[dict], opening: dict[str, int] | None = None) -> list[dict]:
    """rows: 期間中の科目別合計。opening: 期首残高（科目コード→残高）を別に示す場合。"""
    out = []
    for r in rows:
        bal = balance_of(r)
        op = (opening or {}).get(r["code"], 0)
        if r["debit"] == 0 and r["credit"] == 0 and op == 0:
            continue
        out.append({
            "code": r["code"], "name": r["name"], "category": r["category"],
            "opening": op, "debit": r["debit"], "credit": r["credit"], "closing": op + bal,
        })
    return out


def income_statement(rows: list[dict]) -> dict:
    revenue_expense = [r for r in rows if r["category"] in ("revenue", "expense")]
    sections: dict[str, list[dict]] = {}
    for r in revenue_expense:
        bal = balance_of(r)
        if bal == 0:
            continue
        sections.setdefault(r["statement_section"], []).append({"code": r["code"], "name": r["name"], "amount": bal})
    total = lambda s: sum(x["amount"] for x in sections.get(s, []))  # noqa: E731
    sales = total("売上高")
    cogs = total("売上原価")
    gross_profit = sales - cogs
    sga = total("販売費及び一般管理費")
    operating = gross_profit - sga
    ordinary = operating + total("営業外収益") - total("営業外費用")
    pretax = ordinary + total("特別利益") - total("特別損失")
    taxes = total("法人税等")
    net = pretax - taxes
    return {
        "sections": {k: sections[k] for k in PL_ORDER if k in sections},
        "sales": sales, "gross_profit": gross_profit, "sga": sga, "operating_income": operating,
        "ordinary_income": ordinary, "income_before_taxes": pretax, "income_taxes": taxes, "net_income": net,
    }


def balance_sheet(rows: list[dict], net_income: int) -> dict:
    groups: dict[str, dict[str, list[dict]]] = {"asset": {}, "liability": {}, "equity": {}}
    for r in rows:
        if r["category"] not in groups:
            continue
        bal = balance_of(r)
        if r["code"] == RETAINED_EARNINGS:
            bal += net_income
        if bal == 0:
            continue
        groups[r["category"]].setdefault(r["statement_section"], []).append({"code": r["code"], "name": r["name"], "amount": bal})
    totals = {k: sum(x["amount"] for sec in v.values() for x in sec) for k, v in groups.items()}
    return {
        "assets": groups["asset"], "liabilities": groups["liability"], "equity": groups["equity"],
        "total_assets": totals["asset"], "total_liabilities": totals["liability"], "total_equity": totals["equity"],
        "balanced": totals["asset"] == totals["liability"] + totals["equity"],
    }


def equity_changes(opening_rows: list[dict], movement_rows: list[dict], net_income: int) -> list[dict]:
    """OUT-12 社員資本等変動計算書。opening_rows は期首残高（繰越・開始残高の仕訳）、movement_rows は期中の増減。"""
    op = {r["code"]: balance_of(r) for r in opening_rows if r["category"] == "equity"}
    mv = {r["code"]: balance_of(r) for r in movement_rows if r["category"] == "equity"}
    names = {r["code"]: r["name"] for r in opening_rows + movement_rows if r["category"] == "equity"}
    out = []
    for code in sorted(names):
        change = mv.get(code, 0)
        ni = net_income if code == RETAINED_EARNINGS else 0
        if op.get(code, 0) == 0 and change == 0 and ni == 0:
            continue
        out.append({"code": code, "name": names[code], "opening": op.get(code, 0), "changes": change,
                    "net_income": ni, "closing": op.get(code, 0) + change + ni})
    total = {"code": "", "name": "社員資本合計", **{k: sum(x[k] for x in out) for k in ("opening", "changes", "net_income", "closing")}}
    return out + [total]


def notes(company: dict, assets_methods: set[str], period: dict) -> list[dict]:
    """OUT-13 個別注記表（中小企業の会計に関する指針・要領に準拠した簡易版）。"""
    methods = []
    if assets_methods & {"straight_line"}:
        methods.append("定額法")
    if assets_methods & {"declining_balance"}:
        methods.append("定率法")
    dep = "有形固定資産・無形固定資産は" + ("、".join(methods) if methods else "法人税法の規定による方法") + "によっている。"
    if assets_methods & {"small_sme_special", "lump_sum_3y", "immediate_small"}:
        dep += "なお、少額減価償却資産等については法人税法の規定に基づき一括償却・即時償却している。"
    tax = "税込方式によっている。" if company["accounting_tax_method"] == "tax_included" else "税抜方式によっている。"
    return [
        {"item": "作成基準", "text": "この計算書類は「中小企業の会計に関する基本要領」によって作成している。"},
        {"item": "重要な会計方針 固定資産の減価償却の方法", "text": dep},
        {"item": "重要な会計方針 消費税等の会計処理", "text": "消費税等の会計処理は" + tax},
        {"item": "事業年度", "text": f"{period['start_date']} から {period['end_date']} まで"},
    ]
