"use client";

import Link from "next/link";
import { useState } from "react";
import { Card, ErrorBox, Field, PageTitle, Warnings } from "@/components/ui";
import { api, todayIso, useApi, yen, type Warning } from "@/lib/client";

const STATUS: Record<string, string> = { issued: "未入金", partially_paid: "一部入金", paid: "入金済み" };

type Line = { description: string; amount: string; tax_rate: "0.10" | "0.08" };

export default function InvoicesPage() {
  const list = useApi<{ items: any[] }>("sales-invoices");
  const cps = useApi<{ items: any[] }>("counterparties");
  const [form, setForm] = useState({ client_id: "", issue_date: todayIso(), service_period: "", due_date: "", invoice_number: "" });
  const [lines, setLines] = useState<Line[]>([{ description: "", amount: "", tax_rate: "0.10" }]);
  const [error, setError] = useState<unknown>(null);
  const [warnings, setWarnings] = useState<Warning[]>([]);

  const net = lines.reduce((a, l) => a + (Number(l.amount) || 0), 0);
  const setLine = (i: number, p: Partial<Line>) => setLines(lines.map((l, j) => (j === i ? { ...l, ...p } : l)));

  async function create(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const r = await api("sales-invoices", {
        body: { ...form, invoice_number: form.invoice_number || null, lines: lines.filter((l) => l.description).map((l) => ({ ...l, amount: Number(l.amount) })) },
      });
      setWarnings(r.warnings);
      setLines([{ description: "", amount: "", tax_rate: "0.10" }]);
      list.reload();
    } catch (err) {
      setError(err);
    }
  }

  return (
    <>
      <PageTitle title="請求書">発行時に「売掛金／売上高」の仕訳を自動で作ります。印刷画面からPDFにできます。</PageTitle>
      <Card title="請求書の一覧">
        <div className="table-wrap">
          <table>
            <thead><tr><th>番号</th><th>発行日</th><th>請求先</th><th>取引期間</th><th>支払期日</th><th className="num">請求額</th><th className="num">残高</th><th>状況</th></tr></thead>
            <tbody>
              {list.data?.items.map((i) => (
                <tr key={i.id}>
                  <td><Link href={`/invoices/${i.id}`}>{i.invoice_number}</Link></td>
                  <td>{i.issue_date}</td><td>{i.client_name}</td><td>{i.service_period}</td><td>{i.due_date}</td>
                  <td className="num">{yen(i.total_amount)}</td><td className="num">{yen(i.remaining_amount)}</td>
                  <td><span className={`badge${i.status === "paid" ? " ok" : ""}`}>{STATUS[i.status]}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {list.data?.items.length === 0 ? <p className="muted">請求書はまだありません。</p> : null}
      </Card>
      <Card title="請求書の作成">
        <form onSubmit={create}>
          <div className="form">
            <Field label="請求先">
              <select value={form.client_id} onChange={(e) => setForm({ ...form, client_id: e.target.value })} required>
                <option value="">選択</option>
                {cps.data?.items.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
            </Field>
            <Field label="発行日"><input type="date" value={form.issue_date} onChange={(e) => setForm({ ...form, issue_date: e.target.value })} required /></Field>
            <Field label="取引年月日・役務提供期間"><input value={form.service_period} onChange={(e) => setForm({ ...form, service_period: e.target.value })} placeholder="例: 2026年9月1日〜9月30日" required /></Field>
            <Field label="支払期日"><input type="date" value={form.due_date} onChange={(e) => setForm({ ...form, due_date: e.target.value })} required /></Field>
            <Field label="請求書番号" hint="空欄なら自動採番"><input value={form.invoice_number} onChange={(e) => setForm({ ...form, invoice_number: e.target.value })} /></Field>
          </div>
          <table style={{ marginTop: 12 }}>
            <thead><tr><th>取引内容</th><th className="num">金額（税抜）</th><th>税率</th><th /></tr></thead>
            <tbody>
              {lines.map((l, i) => (
                <tr key={i}>
                  <td><input style={{ width: "100%" }} value={l.description} onChange={(e) => setLine(i, { description: e.target.value })} /></td>
                  <td><input type="number" className="num" value={l.amount} onChange={(e) => setLine(i, { amount: e.target.value })} /></td>
                  <td>
                    <select value={l.tax_rate} onChange={(e) => setLine(i, { tax_rate: e.target.value as Line["tax_rate"] })}>
                      <option value="0.10">10%</option><option value="0.08">8%（軽減）</option>
                    </select>
                  </td>
                  <td>{lines.length > 1 ? <button type="button" onClick={() => setLines(lines.filter((_, j) => j !== i))}>削除</button> : null}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="muted">税抜合計 {yen(net)}円（消費税は税率ごとにまとめて端数処理します）</p>
          <div className="actions">
            <button type="button" onClick={() => setLines([...lines, { description: "", amount: "", tax_rate: "0.10" }])}>＋明細</button>
            <button className="primary">発行</button>
          </div>
        </form>
        <ErrorBox error={error} />
        <Warnings items={warnings} />
      </Card>
    </>
  );
}
