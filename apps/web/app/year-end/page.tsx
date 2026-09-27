"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Card, ErrorBox, Field, Notice, PageTitle } from "@/components/ui";
import { api, useApi, yen } from "@/lib/client";

export default function YearEndPage() {
  const officers = useApi<{ items: any[] }>("officers");
  const officerId = officers.data?.items[0]?.id;
  const [year, setYear] = useState(new Date().getFullYear());
  const result = useApi<any>(officerId ? `year-end-adjustments/${year}` : null, { officer_id: officerId });
  const [form, setForm] = useState<any>({ general: "", medical: "", pension: "", earthquake_insurance_premium: "", small_business_mutual_aid_premium: "", social_insurance_paid_personally: "", spouse_income: "", housing_loan_deduction: "" });
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    const i = result.data?.inputs;
    if (i && Object.keys(i).length) {
      setForm({
        general: i.life_insurance_deduction_inputs?.general ?? "", medical: i.life_insurance_deduction_inputs?.medical ?? "",
        pension: i.life_insurance_deduction_inputs?.pension ?? "", earthquake_insurance_premium: i.earthquake_insurance_premium,
        small_business_mutual_aid_premium: i.small_business_mutual_aid_premium, social_insurance_paid_personally: i.social_insurance_paid_personally,
        spouse_income: i.spouse_income ?? "", housing_loan_deduction: i.housing_loan_deduction,
      });
    }
  }, [result.data]);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    const n = (v: any) => Number(v) || 0;
    try {
      const r = await api(`year-end-adjustments/${year}`, {
        method: "PUT",
        body: {
          officer_id: officerId,
          life_insurance_deduction_inputs: { general: n(form.general), medical: n(form.medical), pension: n(form.pension) },
          earthquake_insurance_premium: n(form.earthquake_insurance_premium),
          small_business_mutual_aid_premium: n(form.small_business_mutual_aid_premium),
          social_insurance_paid_personally: n(form.social_insurance_paid_personally),
          spouse_income: form.spouse_income === "" ? null : n(form.spouse_income),
          housing_loan_deduction: n(form.housing_loan_deduction),
        },
      });
      result.setData(r);
    } catch (err) {
      setError(err);
    }
  }

  if (officers.data && !officerId) return <Notice>先に<Link href="/payroll">役員</Link>を登録してください。</Notice>;
  const r = result.data;
  const num = (k: string, label: string) => (
    <Field label={label}><input type="number" className="num" value={form[k]} onChange={(e) => setForm({ ...form, [k]: e.target.value })} /></Field>
  );

  return (
    <>
      <PageTitle title="年末調整">年末調整の計算（FR-34）。計算は概算です。源泉徴収票の記載内容は「帳票」から出力します（OUT-20）。</PageTitle>
      <Card title="控除の入力（DM-14）" actions={<input type="number" className="num" value={year} onChange={(e) => setYear(Number(e.target.value))} style={{ width: 90 }} />}>
        <form onSubmit={save}>
          <div className="form">
            {num("general", "一般の生命保険料（年額）")}
            {num("medical", "介護医療保険料（年額）")}
            {num("pension", "個人年金保険料（年額）")}
            {num("earthquake_insurance_premium", "地震保険料")}
            {num("small_business_mutual_aid_premium", "小規模企業共済等掛金（iDeCo含む）")}
            {num("social_insurance_paid_personally", "本人が支払った社会保険料（国民年金等）")}
            {num("spouse_income", "配偶者の合計所得（空欄なら扶養情報から）")}
            {num("housing_loan_deduction", "住宅借入金等特別控除額")}
          </div>
          <button className="primary" style={{ marginTop: 8 }}>保存して再計算</button>
        </form>
        <ErrorBox error={error || result.error} />
      </Card>
      {r ? (
        <Card title={`${year}年分の計算結果（概算）`}>
          <table>
            <tbody>
              <tr><th>支給額合計（{r.payment_count}回）</th><td className="num">{yen(r.gross_total)}</td></tr>
              <tr><th>給与所得控除後の金額</th><td className="num">{yen(r.employment_income)}</td></tr>
              <tr><th>社会保険料控除</th><td className="num">{yen(r.deductions.social_insurance)}</td></tr>
              <tr><th>小規模企業共済等掛金控除</th><td className="num">{yen(r.deductions.small_business_mutual_aid)}</td></tr>
              <tr><th>生命保険料控除</th><td className="num">{yen(r.deductions.life_insurance)}</td></tr>
              <tr><th>地震保険料控除</th><td className="num">{yen(r.deductions.earthquake_insurance)}</td></tr>
              <tr><th>配偶者控除</th><td className="num">{yen(r.deductions.spouse)}</td></tr>
              <tr><th>扶養控除</th><td className="num">{yen(r.deductions.dependents)}</td></tr>
              <tr><th>基礎控除</th><td className="num">{yen(r.deductions.basic)}</td></tr>
              <tr><th>課税所得金額</th><td className="num">{yen(r.taxable_income)}</td></tr>
              <tr><th>年税額（復興特別所得税を含む）</th><td className="num">{yen(r.annual_tax)}</td></tr>
              <tr><th>源泉徴収済み税額</th><td className="num">{yen(r.withheld_tax_total)}</td></tr>
              <tr><th>{r.difference >= 0 ? "還付する額" : "追加で徴収する額"}</th><td className="num"><strong>{yen(Math.abs(r.difference))}</strong></td></tr>
            </tbody>
          </table>
          <p className="muted small">配偶者特別控除・障害者控除などは未対応です。税率・控除額は「設定値」で確認・更新できます。</p>
        </Card>
      ) : null}
    </>
  );
}
