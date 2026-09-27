"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Card, ErrorBox, Field, Notice, PageTitle, Warnings } from "@/components/ui";
import { api, useApi, yen, type Warning } from "@/lib/client";

export default function ClosingPage() {
  const periods = useApi<{ items: any[] }>("fiscal-periods");
  const [periodId, setPeriodId] = useState("");
  useEffect(() => {
    if (!periodId && periods.data?.items.length) {
      const open = periods.data.items.find((p) => p.status !== "closed") ?? periods.data.items[periods.data.items.length - 1];
      setPeriodId(open.id);
    }
  }, [periods.data, periodId]);
  const status = useApi<any>(periodId ? `fiscal-periods/${periodId}/closing` : null);
  const [error, setError] = useState<unknown>(null);
  const [warnings, setWarnings] = useState<Warning[]>([]);
  const [message, setMessage] = useState("");

  async function run(path: string, label: string) {
    setError(null);
    setMessage("");
    try {
      const r = await api(path, { body: {} });
      setMessage(`${label}: ${r.amount !== undefined ? `${yen(r.amount)}円` : "完了"}`);
      setWarnings(r.warnings ?? []);
      status.reload();
      periods.reload();
    } catch (err) {
      setError(err);
    }
  }

  async function close() {
    if (!confirm("締め処理を行うと、この期間の仕訳は変更できなくなります（NFR-03）。実行しますか？")) return;
    await run(`fiscal-periods/${periodId}/close`, "締め処理");
  }

  const s = status.data;
  const ct = s?.consumption_tax;
  const tax = s?.tax_estimate;
  const period = periods.data?.items.find((p) => p.id === periodId);

  return (
    <>
      <PageTitle title="決算・締め">決算整理仕訳（FR-60）、消費税（FR-61）、法人税等の概算（FR-62）、締め処理と繰越（FR-63）</PageTitle>
      <Card>
        <div className="form">
          <Field label="会計期間">
            <select value={periodId} onChange={(e) => setPeriodId(e.target.value)}>
              {periods.data?.items.map((p) => <option key={p.id} value={p.id}>{p.start_date}〜{p.end_date}（{p.status === "closed" ? "締め済み" : "入力中"}）</option>)}
            </select>
          </Field>
        </div>
      </Card>
      <ErrorBox error={error || status.error} />
      <Warnings items={warnings} />
      {message ? <Notice>{message}</Notice> : null}
      {s ? (
        <>
          <div className="grid">
            <Card title="チェックリスト">
              <ul className="checklist">
                {s.checklist.map((c: any) => (
                  <li key={c.key}><span className={`badge ${c.done ? "ok" : "ng"}`}>{c.done ? "済" : "未"}</span> {c.label}</li>
                ))}
              </ul>
              <p className="muted small">未払費用・前払費用などのその他の決算整理は <Link href="/journals/new?source=closing_adjustment">決算整理仕訳の入力</Link> から登録します。</p>
            </Card>
            <Card title="損益（決算整理後）">
              <table><tbody>
                <tr><th>売上高</th><td className="num">{yen(s.income_statement.sales)}</td></tr>
                <tr><th>営業利益</th><td className="num">{yen(s.income_statement.operating_income)}</td></tr>
                <tr><th>税引前当期純利益</th><td className="num">{yen(s.income_statement.income_before_taxes)}</td></tr>
                <tr><th>法人税等</th><td className="num">{yen(s.income_statement.income_taxes)}</td></tr>
                <tr><th>当期純利益</th><td className="num"><strong>{yen(s.income_statement.net_income)}</strong></td></tr>
              </tbody></table>
            </Card>
          </div>

          <Card title="1. 減価償却費（FR-50）" actions={<Link href="/assets">固定資産へ</Link>}>
            <button onClick={() => run(`fiscal-periods/${periodId}/depreciation`, "減価償却費")} disabled={period?.status === "closed"}>減価償却費の仕訳を作成</button>
          </Card>

          <Card title="2. 消費税の納付額（FR-61）">
            {ct?.error ? <p className="muted">{ct.error}</p> : ct?.taxable_status === "exempt" ? <p>{ct.message}</p> : ct ? (
              <>
                <p>{ct.basis}</p>
                <table><tbody>
                  <tr><th>売上に係る消費税額（国税）</th><td className="num">{yen(ct.sales_national_tax)}</td></tr>
                  <tr><th>控除税額（国税）</th><td className="num">{yen(ct.deductible_national_tax)}</td></tr>
                  <tr><th>差引税額（国税）</th><td className="num">{yen(ct.national_tax)}</td></tr>
                  <tr><th>地方消費税</th><td className="num">{yen(ct.local_tax)}</td></tr>
                  <tr><th>{ct.is_refund ? "還付税額" : "納付税額 合計"}</th><td className="num"><strong>{yen(ct.payable_total)}</strong></td></tr>
                </tbody></table>
                <button onClick={() => run(`fiscal-periods/${periodId}/closing-entries/consumption-tax`, "未払消費税等")} disabled={period?.status === "closed"}>未払消費税等を計上</button>
              </>
            ) : null}
          </Card>

          <Card title="3. 法人税・地方税の概算（FR-62）">
            <div className="alert alert-warn">概算です。{tax?.notice}</div>
            {tax?.error ? <p>{tax.error}</p> : tax ? (
              <>
                <table><tbody>
                  <tr><th>税引前当期純利益</th><td className="num">{yen(tax.income_before_taxes)}</td></tr>
                  <tr><th>繰越欠損金の控除</th><td className="num">{yen(tax.loss_carryforward_used)}</td></tr>
                  <tr><th>課税所得（概算・千円未満切捨て）</th><td className="num">{yen(tax.taxable_income)}</td></tr>
                  <tr><th>法人税（{tax.is_sme ? "中小法人の軽減税率" : "本則税率"}）</th><td className="num">{yen(tax.corporate_tax)}</td></tr>
                  <tr><th>防衛特別法人税</th><td className="num">{yen(tax.defense_special_corporate_tax)}</td></tr>
                  <tr><th>地方法人税</th><td className="num">{yen(tax.local_corporate_tax)}</td></tr>
                  <tr><th>法人事業税</th><td className="num">{yen(tax.enterprise_tax)}</td></tr>
                  <tr><th>特別法人事業税</th><td className="num">{yen(tax.special_enterprise_tax)}</td></tr>
                  <tr><th>法人住民税（法人税割）</th><td className="num">{yen(tax.resident_tax_corporate)}</td></tr>
                  <tr><th>法人住民税（均等割・赤字でも発生）</th><td className="num">{yen(tax.resident_tax_per_capita)}</td></tr>
                  <tr><th>合計</th><td className="num"><strong>{yen(tax.total)}</strong></td></tr>
                  <tr><th>中間納付額</th><td className="num">{yen(tax.interim_payments_total)}</td></tr>
                  <tr><th>未払法人税等として計上する額</th><td className="num"><strong>{yen(tax.payable_after_interim)}</strong></td></tr>
                </tbody></table>
                <button onClick={() => run(`fiscal-periods/${periodId}/closing-entries/corporate-tax`, "未払法人税等")} disabled={period?.status === "closed"}>未払法人税等を計上</button>
              </>
            ) : null}
          </Card>

          <Carryover periodId={periodId} />

          <Card title="5. 締め処理（FR-63）">
            <p>締めた期間の仕訳は変更できなくなり、資産・負債・純資産の残高を翌期首に繰り越します。締めた期のデータはバックアップに保存します（NFR-01）。</p>
            <div className="actions">
              <button className="primary" onClick={close} disabled={period?.status === "closed"}>この期間を締める</button>
              <Link href="/reports">決算書・申告用の集計資料を出力（FR-64）</Link>
            </div>
          </Card>
        </>
      ) : null}
    </>
  );
}

function Carryover({ periodId }: { periodId: string }) {
  const c = useApi<any>(`fiscal-periods/${periodId}/carryover`);
  const [form, setForm] = useState<any>(null);
  const [error, setError] = useState<unknown>(null);
  useEffect(() => {
    if (c.data) setForm({ ...c.data, business_overview_text: Object.entries(c.data.business_overview ?? {}).map(([k, v]) => `${k}: ${v}`).join("\n") });
  }, [c.data]);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    const overview = Object.fromEntries(
      String(form.business_overview_text || "").split("\n").map((l: string) => l.split(/[:：]/)).filter((p: string[]) => p.length >= 2).map((p: string[]) => [p[0].trim(), p.slice(1).join(":").trim()]),
    );
    try {
      await api(`fiscal-periods/${periodId}/carryover`, {
        method: "PUT",
        body: {
          loss_carryforwards: form.loss_carryforwards,
          prior_corporate_tax: Number(form.prior_corporate_tax) || 0,
          interim_payments: form.interim_payments,
          resident_tax_per_capita: Number(form.resident_tax_per_capita) || 0,
          business_overview: overview,
        },
      });
      c.reload();
    } catch (err) {
      setError(err);
    }
  }

  if (!form) return null;
  return (
    <Card title="4. 繰越情報（DM-17）">
      {c.data?.interim_filing_required ? <div className="alert alert-warn">前期の法人税額が20万円を超えるため、法人税の中間申告が必要です（BR-092）。</div> : null}
      <form onSubmit={save}>
        <div className="form">
          <Field label="前期の法人税額"><input type="number" className="num" value={form.prior_corporate_tax} onChange={(e) => setForm({ ...form, prior_corporate_tax: e.target.value })} /></Field>
          <Field label="法人住民税の均等割額" hint="都道府県＋市区町村。資本金等の額と従業者数で決まる"><input type="number" className="num" value={form.resident_tax_per_capita} onChange={(e) => setForm({ ...form, resident_tax_per_capita: e.target.value })} /></Field>
        </div>
        <h3>繰越欠損金（古い年度から控除）</h3>
        {form.loss_carryforwards.map((l: any, i: number) => (
          <div className="form" key={i}>
            <Field label="発生年度"><input value={l.origin_period} onChange={(e) => setForm({ ...form, loss_carryforwards: form.loss_carryforwards.map((x: any, j: number) => (j === i ? { ...x, origin_period: e.target.value } : x)) })} /></Field>
            <Field label="残高"><input type="number" className="num" value={l.remaining_amount} onChange={(e) => setForm({ ...form, loss_carryforwards: form.loss_carryforwards.map((x: any, j: number) => (j === i ? { ...x, remaining_amount: Number(e.target.value) } : x)) })} /></Field>
          </div>
        ))}
        <button type="button" onClick={() => setForm({ ...form, loss_carryforwards: [...form.loss_carryforwards, { origin_period: "", remaining_amount: 0 }] })}>＋繰越欠損金</button>
        <h3>中間納付</h3>
        {form.interim_payments.map((p: any, i: number) => (
          <div className="form" key={i}>
            <Field label="税目"><input value={p.tax_type} onChange={(e) => setForm({ ...form, interim_payments: form.interim_payments.map((x: any, j: number) => (j === i ? { ...x, tax_type: e.target.value } : x)) })} /></Field>
            <Field label="金額"><input type="number" className="num" value={p.amount} onChange={(e) => setForm({ ...form, interim_payments: form.interim_payments.map((x: any, j: number) => (j === i ? { ...x, amount: Number(e.target.value) } : x)) })} /></Field>
            <Field label="納付日"><input type="date" value={p.paid_date} onChange={(e) => setForm({ ...form, interim_payments: form.interim_payments.map((x: any, j: number) => (j === i ? { ...x, paid_date: e.target.value } : x)) })} /></Field>
          </div>
        ))}
        <button type="button" onClick={() => setForm({ ...form, interim_payments: [...form.interim_payments, { tax_type: "法人税", amount: 0, paid_date: "" }] })}>＋中間納付</button>
        <h3>法人事業概況説明書の項目（「項目: 内容」を1行ずつ）</h3>
        <textarea rows={4} style={{ width: "100%" }} value={form.business_overview_text} onChange={(e) => setForm({ ...form, business_overview_text: e.target.value })} placeholder={"事業内容: ソフトウェア開発の受託\n主要な取引先: ○○株式会社"} />
        <div className="actions" style={{ marginTop: 8 }}><button className="primary">保存</button></div>
      </form>
      <ErrorBox error={error} />
    </Card>
  );
}
