"use client";

import { useState } from "react";
import { Card, ErrorBox, Field, PageTitle } from "@/components/ui";
import { api, todayIso, useApi, yen } from "@/lib/client";

export default function WithholdingPage() {
  const [year, setYear] = useState(new Date().getFullYear());
  const settings = useApi<any>("withholding/settings");
  const status = useApi<any>("withholding/status", { year });
  const pas = useApi<{ items: any[] }>("payment-accounts");
  const [pay, setPay] = useState({ period: "", amount: "", paid_date: todayIso(), payment_account_id: "" });
  const [error, setError] = useState<unknown>(null);
  const [tableMsg, setTableMsg] = useState("");

  async function toggleSpecial(v: boolean) {
    try {
      await api("withholding/settings", { method: "PUT", body: { special_payment_deadline: v } });
      settings.reload();
      status.reload();
    } catch (err) {
      setError(err);
    }
  }

  async function payTax(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await api("withholding/payments", { body: { ...pay, amount: Number(pay.amount) } });
      status.reload();
    } catch (err) {
      setError(err);
    }
  }

  async function importTable(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    const fd = new FormData(e.currentTarget);
    const y = fd.get("year");
    fd.delete("year");
    try {
      const r = await api(`withholding-tables/${y}/import`, { form: fd });
      setTableMsg(`${r.year}年の税額表を ${r.rows} 行取り込みました`);
    } catch (err) {
      setError(err);
    }
  }

  return (
    <>
      <PageTitle title="源泉所得税">納付期限の表示（FR-33 / BR-042）と、源泉徴収税額表の差し替え（FR-32 / NFR-07）</PageTitle>
      <ErrorBox error={error} />
      <Card title="納期の特例（DM-13）">
        <label className="check">
          <input type="checkbox" checked={!!settings.data?.special_payment_deadline} onChange={(e) => toggleSpecial(e.target.checked)} />
          納期の特例の承認を受けている（1〜6月分は7月10日、7〜12月分は翌年1月20日が期限）
        </label>
      </Card>
      <Card title="納付状況" actions={<input type="number" className="num" value={year} onChange={(e) => setYear(Number(e.target.value))} style={{ width: 90 }} />}>
        <div className="table-wrap">
          <table>
            <thead><tr><th>納付単位</th><th className="num">支給額</th><th className="num">源泉徴収額</th><th className="num">納付済み</th><th className="num">未納付</th><th>納付期限</th><th /></tr></thead>
            <tbody>
              {status.data?.items.map((p: any) => (
                <tr key={p.period}>
                  <td>{p.period}</td><td className="num">{yen(p.gross)}</td><td className="num">{yen(p.withheld)}</td><td className="num">{yen(p.paid)}</td>
                  <td className="num">{yen(p.unpaid)}</td><td>{p.deadline}</td>
                  <td>{p.unpaid > 0 ? <button onClick={() => setPay({ ...pay, period: p.period, amount: String(p.unpaid) })}>納付を記録</button> : <span className="badge ok">納付済み</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {status.data?.items.length === 0 ? <p className="muted">この年の給与支給はありません。</p> : null}
        <h3>納付の記録（預り金を消し込む仕訳を作成）</h3>
        <form className="form" onSubmit={payTax}>
          <Field label="納付単位" hint="例: 2026-09 / 2026-H1"><input value={pay.period} onChange={(e) => setPay({ ...pay, period: e.target.value })} required /></Field>
          <Field label="金額"><input type="number" className="num" value={pay.amount} onChange={(e) => setPay({ ...pay, amount: e.target.value })} required /></Field>
          <Field label="納付日"><input type="date" value={pay.paid_date} onChange={(e) => setPay({ ...pay, paid_date: e.target.value })} required /></Field>
          <Field label="支払口座">
            <select value={pay.payment_account_id} onChange={(e) => setPay({ ...pay, payment_account_id: e.target.value })} required>
              <option value="">選択</option>
              {pas.data?.items.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          </Field>
          <button className="primary">記録</button>
        </form>
      </Card>
      <Card title="源泉徴収税額表（月額表・甲欄）の取込">
        <p className="muted small">国税庁が公表する税額表を「以上,未満,扶養0人,1人,…,7人」の列のCSVにして取り込みます。同じ年のデータは置き換えます。</p>
        <form className="form" onSubmit={importTable}>
          <Field label="適用年"><input name="year" type="number" className="num" defaultValue={year} /></Field>
          <Field label="CSV"><input name="file" type="file" accept=".csv" required /></Field>
          <button className="primary">取り込む</button>
        </form>
        {tableMsg ? <p>{tableMsg}</p> : null}
      </Card>
    </>
  );
}
