"use client";

import { useState } from "react";
import { AccountSelect, Card, ErrorBox, Field, PageTitle, Warnings } from "@/components/ui";
import { api, useApi, yen, type Warning } from "@/lib/client";

export default function ImportsPage() {
  const pas = useApi<{ items: any[] }>("payment-accounts");
  const accounts = useApi<{ items: any[] }>("accounts");
  const cps = useApi<{ items: any[] }>("counterparties");
  const taxCodes = useApi<{ items: any[] }>("tax-codes");
  const [paId, setPaId] = useState("");
  const [candidates, setCandidates] = useState<any[]>([]);
  const [selected, setSelected] = useState<boolean[]>([]);
  const [parseErrors, setParseErrors] = useState<string[]>([]);
  const [error, setError] = useState<unknown>(null);
  const [warnings, setWarnings] = useState<Warning[]>([]);
  const [result, setResult] = useState<string>("");

  async function upload(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    setResult("");
    const fd = new FormData(e.currentTarget);
    try {
      const r = await api("imports/bank-csv", { form: fd });
      setCandidates(r.candidates);
      setSelected(r.candidates.map((c: any) => !c.duplicate));
      setParseErrors(r.errors);
    } catch (err) {
      setError(err);
    }
  }

  const update = (i: number, patch: any) => setCandidates(candidates.map((c, j) => (j === i ? { ...c, ...patch } : c)));

  async function commit() {
    setError(null);
    const chosen = candidates.filter((_, i) => selected[i]);
    if (chosen.some((c) => !c.account_code)) {
      setError(new Error("勘定科目が未選択の明細があります"));
      return;
    }
    try {
      const r = await api("imports/bank-csv/commit", {
        body: {
          payment_account_id: paId,
          candidates: chosen.map((c) => ({ ...c, tax_code: c.tax_code || null, counterparty_id: c.counterparty_id || null })),
        },
      });
      setWarnings(r.warnings);
      setResult(`${r.created.length}件を登録しました。${r.failed.length ? `失敗 ${r.failed.length}件: ${r.failed.map((f: any) => f.message).join(" / ")}` : ""}`);
      setCandidates([]);
    } catch (err) {
      setError(err);
    }
  }

  return (
    <>
      <PageTitle title="明細CSVの取込">銀行・カードの明細CSVから仕訳の候補を作ります。摘要のキーワードで科目を推定するルールを登録できます。</PageTitle>
      <Card title="1. CSVを読み込む">
        <form className="form" onSubmit={upload}>
          <Field label="口座・カード">
            <select name="payment_account_id" value={paId} onChange={(e) => setPaId(e.target.value)} required>
              <option value="">選択</option>
              {pas.data?.items.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          </Field>
          <Field label="CSVファイル" hint="日付・摘要・出金/入金（または金額）の列が必要。UTF-8／Shift_JIS 対応"><input type="file" name="file" accept=".csv,text/csv" required /></Field>
          <button className="primary">読み込む</button>
        </form>
        {parseErrors.length ? <div className="alert alert-warn"><ul>{parseErrors.map((e, i) => <li key={i}>{e}</li>)}</ul></div> : null}
      </Card>

      {candidates.length ? (
        <Card title="2. 候補を確認して登録" actions={<button className="primary" onClick={commit}>選択した{selected.filter(Boolean).length}件を登録</button>}>
          <div className="table-wrap">
            <table>
              <thead><tr><th /><th>日付</th><th>摘要</th><th>入出金</th><th className="num">金額</th><th>相手科目</th><th>税区分</th><th>取引先</th><th>推定</th></tr></thead>
              <tbody>
                {candidates.map((c, i) => (
                  <tr key={i} className={c.duplicate ? "voided" : undefined}>
                    <td><input type="checkbox" checked={selected[i] ?? false} onChange={(e) => setSelected(selected.map((s, j) => (j === i ? e.target.checked : s)))} /></td>
                    <td>{c.transaction_date}</td>
                    <td><input value={c.description} onChange={(e) => update(i, { description: e.target.value })} /></td>
                    <td>{c.direction === "out" ? "出金" : "入金"}</td>
                    <td className="num">{yen(c.amount)}</td>
                    <td>
                      <AccountSelect accounts={accounts.data?.items ?? []} value={c.account_code ?? ""}
                        onChange={(code) => update(i, { account_code: code, tax_code: accounts.data?.items.find((a) => a.code === code)?.default_tax_code })} />
                    </td>
                    <td>
                      <select value={c.tax_code ?? ""} onChange={(e) => update(i, { tax_code: e.target.value })}>
                        <option value="">初期値</option>
                        {taxCodes.data?.items.map((t) => <option key={t.code} value={t.code}>{t.name}</option>)}
                      </select>
                    </td>
                    <td>
                      <select value={c.counterparty_id ?? ""} onChange={(e) => update(i, { counterparty_id: e.target.value })}>
                        <option value="">なし</option>
                        {cps.data?.items.map((cp) => <option key={cp.id} value={cp.id}>{cp.name}</option>)}
                      </select>
                    </td>
                    <td className="small muted">{c.duplicate ? "取込済みの可能性" : c.matched_rule ? `ルール「${c.matched_rule}」` : ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      ) : null}
      <ErrorBox error={error} />
      <Warnings items={warnings} />
      {result ? <p>{result}</p> : null}
      <Rules accounts={accounts.data?.items ?? []} cps={cps.data?.items ?? []} />
    </>
  );
}

function Rules({ accounts, cps }: { accounts: any[]; cps: any[] }) {
  const rules = useApi<{ items: any[] }>("import-rules");
  const [form, setForm] = useState({ keyword: "", account_code: "", counterparty_id: "", priority: 100 });
  const [error, setError] = useState<unknown>(null);

  async function add(e: React.FormEvent) {
    e.preventDefault();
    try {
      await api("import-rules", { body: { ...form, counterparty_id: form.counterparty_id || null } });
      setForm({ keyword: "", account_code: "", counterparty_id: "", priority: 100 });
      rules.reload();
    } catch (err) {
      setError(err);
    }
  }

  async function remove(id: string) {
    await api(`import-rules/${id}`, { method: "DELETE" });
    rules.reload();
  }

  return (
    <Card title="科目の推定ルール">
      <div className="table-wrap">
        <table>
          <thead><tr><th>キーワード（摘要に含む）</th><th>勘定科目</th><th>取引先</th><th>優先度</th><th /></tr></thead>
          <tbody>
            {rules.data?.items.map((r) => (
              <tr key={r.id}><td>{r.keyword}</td><td>{r.account_code} {r.account_name}</td><td>{r.counterparty_name}</td><td>{r.priority}</td><td><button onClick={() => remove(r.id)}>削除</button></td></tr>
            ))}
          </tbody>
        </table>
      </div>
      <form className="form" onSubmit={add} style={{ marginTop: 12 }}>
        <Field label="キーワード"><input value={form.keyword} onChange={(e) => setForm({ ...form, keyword: e.target.value })} required /></Field>
        <Field label="勘定科目"><AccountSelect accounts={accounts} value={form.account_code} onChange={(c) => setForm({ ...form, account_code: c })} /></Field>
        <Field label="取引先">
          <select value={form.counterparty_id} onChange={(e) => setForm({ ...form, counterparty_id: e.target.value })}>
            <option value="">なし</option>
            {cps.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </Field>
        <Field label="優先度" hint="小さいほど優先"><input type="number" className="num" value={form.priority} onChange={(e) => setForm({ ...form, priority: Number(e.target.value) })} /></Field>
        <button className="primary">追加</button>
      </form>
      <ErrorBox error={error} />
    </Card>
  );
}
