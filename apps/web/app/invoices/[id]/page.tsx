"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { Card, ErrorBox, Field, Warnings } from "@/components/ui";
import { api, todayIso, useApi, yen, type Warning } from "@/lib/client";

export default function InvoiceDetail() {
  const { id } = useParams<{ id: string }>();
  const inv = useApi<any>(`sales-invoices/${id}`);
  const pas = useApi<{ items: any[] }>("payment-accounts");
  const [receipt, setReceipt] = useState({ received_date: todayIso(), received_amount: "", payment_account_id: "", treat_shortfall_as_fee: true });
  const [error, setError] = useState<unknown>(null);
  const [warnings, setWarnings] = useState<Warning[]>([]);

  if (inv.error) return <ErrorBox error={inv.error} />;
  const d = inv.data;
  if (!d) return <p className="muted">読み込み中…</p>;

  async function receive(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const r = await api(`sales-invoices/${id}/receipts`, { body: { ...receipt, received_amount: Number(receipt.received_amount) } });
      setWarnings(r.warnings);
      inv.reload();
    } catch (err) {
      setError(err);
    }
  }

  const shortfall = d.remaining_amount - (Number(receipt.received_amount) || 0);

  return (
    <>
      <div className="actions no-print" style={{ marginBottom: 12 }}>
        <Link href="/invoices">← 一覧へ</Link>
        <button onClick={() => window.print()}>印刷・PDFに保存</button>
      </div>
      {!d.issuer_registration_number ? (
        <div className="alert alert-warn no-print">発行者の登録番号が設定されていないため、適格請求書の要件（BR-023）を満たしません。初期設定の消費税設定で登録番号を入力してください。</div>
      ) : null}

      <div className="invoice">
        <h1>請求書</h1>
        <div className="parties">
          <div>
            <div style={{ fontSize: 18, fontWeight: 700 }}>{d.client?.name} 御中</div>
            {d.client?.address ? <div>{d.client.address}</div> : null}
            <div className="total">ご請求金額 ¥{yen(d.total_amount)}（税込）</div>
            <div>取引年月日: {d.service_period}</div>
            <div>お支払期日: {d.due_date}</div>
          </div>
          <div style={{ textAlign: "right" }}>
            <div>請求書番号: {d.invoice_number}</div>
            <div>発行日: {d.issue_date}</div>
            <div style={{ marginTop: 12, fontWeight: 700 }}>{d.issuer?.trade_name}</div>
            <div>{d.issuer?.head_office_address}</div>
            <div>登録番号: {d.issuer_registration_number ?? "（未登録）"}</div>
          </div>
        </div>
        <table>
          <thead><tr><th>取引内容</th><th>税率</th><th className="num">金額（税抜）</th></tr></thead>
          <tbody>
            {d.lines.map((l: any, i: number) => (
              <tr key={i}>
                <td>{l.description}{l.tax_rate === "0.08" ? " ※" : ""}</td>
                <td>{l.tax_rate === "0.08" ? "8%" : "10%"}</td>
                <td className="num">{yen(l.amount)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <table style={{ marginTop: 16, width: "60%", marginLeft: "auto" }}>
          <thead><tr><th>税率区分</th><th className="num">対価の額（税抜）</th><th className="num">消費税額</th><th className="num">合計</th></tr></thead>
          <tbody>
            {d.summary_by_rate.map((s: any) => (
              <tr key={s.rate}>
                <td>{s.rate === "0.10" ? "10%対象" : "8%対象（軽減税率）"}</td>
                <td className="num">{yen(s.net_total)}</td>
                <td className="num">{yen(s.tax)}</td>
                <td className="num">{yen(s.gross_total)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {d.lines.some((l: any) => l.tax_rate === "0.08") ? <p className="small">※は軽減税率（8%）対象品目です。</p> : null}
      </div>

      <div className="no-print" style={{ marginTop: 16 }}>
        <Card title="入金の消込（FR-22）">
          <p>請求額 {yen(d.total_amount)}円 ／ 入金済み {yen(d.received_amount)}円 ／ 振込手数料 {yen(d.bank_fee_deducted)}円 ／ 残高 <strong>{yen(d.remaining_amount)}円</strong></p>
          {d.receipts.length ? (
            <ul>{d.receipts.map((r: any) => <li key={r.id}>{r.received_date} 入金 {yen(r.received_amount)}円{r.bank_fee ? `（手数料 ${yen(r.bank_fee)}円）` : ""}</li>)}</ul>
          ) : null}
          {d.remaining_amount > 0 ? (
            <form className="form" onSubmit={receive}>
              <Field label="入金日"><input type="date" value={receipt.received_date} onChange={(e) => setReceipt({ ...receipt, received_date: e.target.value })} required /></Field>
              <Field label="入金額"><input type="number" className="num" value={receipt.received_amount} onChange={(e) => setReceipt({ ...receipt, received_amount: e.target.value })} required /></Field>
              <Field label="入金先">
                <select value={receipt.payment_account_id} onChange={(e) => setReceipt({ ...receipt, payment_account_id: e.target.value })} required>
                  <option value="">選択</option>
                  {pas.data?.items.filter((p) => p.type === "bank" || p.type === "cash").map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                </select>
              </Field>
              <Field label="不足額の扱い" hint={shortfall > 0 && receipt.received_amount ? `差額 ${yen(shortfall)}円` : undefined}>
                <span className="check"><input type="checkbox" checked={receipt.treat_shortfall_as_fee} onChange={(e) => setReceipt({ ...receipt, treat_shortfall_as_fee: e.target.checked })} /> 振込手数料（支払手数料）として処理</span>
              </Field>
              <button className="primary">消し込む</button>
            </form>
          ) : <p className="badge ok">入金済み</p>}
          <ErrorBox error={error} />
          <Warnings items={warnings} />
        </Card>
      </div>
    </>
  );
}
