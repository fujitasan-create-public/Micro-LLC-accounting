"use client";

import { useState } from "react";
import { AccountSelect, Card, ErrorBox, Field, PageTitle, Warnings } from "@/components/ui";
import { api, todayIso, useApi, yen, type Warning } from "@/lib/client";

type TLine = { side: "debit" | "credit"; account_code: string; amount: string; tax_code: string };

export default function RecurringPage() {
  const templates = useApi<{ items: any[] }>("recurring-templates");
  const accounts = useApi<{ items: any[] }>("accounts");
  const cps = useApi<{ items: any[] }>("counterparties");
  const pas = useApi<{ items: any[] }>("payment-accounts");
  const [ym, setYm] = useState(todayIso().slice(0, 7));
  const [form, setForm] = useState({ name: "", day_of_month: 25, description: "", counterparty_id: "", payment_account_id: "", start_month: todayIso().slice(0, 7), end_month: "", auto_post: true });
  const [lines, setLines] = useState<TLine[]>([
    { side: "debit", account_code: "", amount: "", tax_code: "" },
    { side: "credit", account_code: "", amount: "", tax_code: "" },
  ]);
  const [error, setError] = useState<unknown>(null);
  const [warnings, setWarnings] = useState<Warning[]>([]);
  const [message, setMessage] = useState("");

  async function generate() {
    setError(null);
    try {
      const r = await api("recurring-templates/generate", { body: { year_month: ym } });
      setWarnings(r.warnings);
      setMessage(`作成 ${r.created.length}件 ／ 作成済みのため省略 ${r.skipped.length}件${r.failed.length ? ` ／ 失敗: ${r.failed.map((f: any) => `${f.name}（${f.message}）`).join("、")}` : ""}`);
    } catch (err) {
      setError(err);
    }
  }

  async function add(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await api("recurring-templates", {
        body: {
          ...form,
          counterparty_id: form.counterparty_id || null,
          payment_account_id: form.payment_account_id || null,
          end_month: form.end_month || null,
          lines: lines.filter((l) => l.account_code).map((l) => ({ ...l, amount: Number(l.amount), tax_code: l.tax_code || null })),
        },
      });
      templates.reload();
    } catch (err) {
      setError(err);
    }
  }

  async function patch(id: string, body: Record<string, unknown>) {
    await api(`recurring-templates/${id}`, { method: "PATCH", body });
    templates.reload();
  }

  const setLine = (i: number, p: Partial<TLine>) => setLines(lines.map((l, j) => (j === i ? { ...l, ...p } : l)));

  return (
    <>
      <PageTitle title="定型仕訳">家賃・口座振替・サブスクリプションなど、毎月決まって発生する取引です。「自動」にしたものは、計上日が来ると自動で記帳されます。</PageTitle>
      <Card title="手動で作成（「自動」にしていないもの・過去の月の分）">
        <div className="form">
          <Field label="対象月"><input type="month" value={ym} onChange={(e) => setYm(e.target.value)} /></Field>
          <button className="primary" onClick={generate}>この月の定型仕訳を作成</button>
        </div>
        {message ? <p>{message}</p> : null}
        <Warnings items={warnings} />
      </Card>
      <Card title="テンプレート">
        <div className="table-wrap">
          <table>
            <thead><tr><th>名前</th><th>毎月</th><th>期間</th><th>摘要</th><th>明細</th><th>記帳</th><th>状態</th><th /></tr></thead>
            <tbody>
              {templates.data?.items.map((t) => (
                <tr key={t.id} className={t.is_active ? undefined : "voided"}>
                  <td>{t.name}</td><td>{t.day_of_month}日</td><td className="small">{t.start_month ?? ""}〜{t.end_month ?? ""}</td><td>{t.description}</td>
                  <td>{t.lines.map((l: any, i: number) => <div key={i}>{l.side === "debit" ? "借" : "貸"} {accounts.data?.items.find((a) => a.code === l.account_code)?.name} {yen(l.amount)}</div>)}</td>
                  <td>
                    <label className="check"><input type="checkbox" checked={!!t.auto_post} onChange={(e) => patch(t.id, { auto_post: e.target.checked })} /> 自動</label>
                  </td>
                  <td>{t.is_active ? "有効" : "停止"}</td>
                  <td><button onClick={() => patch(t.id, { is_active: !t.is_active })}>{t.is_active ? "停止" : "再開"}</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <h3>テンプレートの追加</h3>
        <form onSubmit={add}>
          <div className="form">
            <Field label="名前"><input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required /></Field>
            <Field label="計上日（毎月）"><input type="number" min={1} max={31} className="num" value={form.day_of_month} onChange={(e) => setForm({ ...form, day_of_month: Number(e.target.value) })} /></Field>
            <Field label="摘要"><input value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} required /></Field>
            <Field label="取引先">
              <select value={form.counterparty_id} onChange={(e) => setForm({ ...form, counterparty_id: e.target.value })}>
                <option value="">なし</option>
                {cps.data?.items.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
            </Field>
            <Field label="開始月"><input type="month" value={form.start_month} onChange={(e) => setForm({ ...form, start_month: e.target.value })} required /></Field>
            <Field label="終了月（空欄なら期限なし）"><input type="month" value={form.end_month} onChange={(e) => setForm({ ...form, end_month: e.target.value })} /></Field>
            <Field label="記帳のしかた">
              <label className="check"><input type="checkbox" checked={form.auto_post} onChange={(e) => setForm({ ...form, auto_post: e.target.checked })} /> 計上日が来たら自動で記帳する</label>
            </Field>
            <Field label="支払元">
              <select value={form.payment_account_id} onChange={(e) => setForm({ ...form, payment_account_id: e.target.value })}>
                <option value="">なし</option>
                {pas.data?.items.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
              </select>
            </Field>
          </div>
          <table style={{ marginTop: 8 }}>
            <tbody>
              {lines.map((l, i) => (
                <tr key={i}>
                  <td>
                    <select value={l.side} onChange={(e) => setLine(i, { side: e.target.value as TLine["side"] })}>
                      <option value="debit">借方</option><option value="credit">貸方</option>
                    </select>
                  </td>
                  <td><AccountSelect accounts={accounts.data?.items ?? []} value={l.account_code} onChange={(c) => setLine(i, { account_code: c })} /></td>
                  <td><input type="number" className="num" value={l.amount} onChange={(e) => setLine(i, { amount: e.target.value })} placeholder="金額" /></td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="actions" style={{ marginTop: 8 }}>
            <button type="button" onClick={() => setLines([...lines, { side: "credit", account_code: "", amount: "", tax_code: "" }])}>＋明細</button>
            <button className="primary">追加</button>
          </div>
        </form>
        <ErrorBox error={error} />
      </Card>
    </>
  );
}
