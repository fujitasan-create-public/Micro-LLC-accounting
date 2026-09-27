"use client";

import Link from "next/link";
import { useState } from "react";
import { Card, ErrorBox, Field, PageTitle } from "@/components/ui";
import { api, useApi, yen } from "@/lib/client";

const SOURCE_LABELS: Record<string, string> = {
  manual: "手入力",
  csv_import: "CSV取込",
  recurring: "定型",
  closing_adjustment: "決算整理",
  opening_balance: "開始残高",
  carryover: "繰越",
};

export default function JournalsPage() {
  const accounts = useApi<{ items: any[] }>("accounts");
  const [filters, setFilters] = useState<any>({ from: "", to: "", amount_min: "", amount_max: "", counterparty: "", account: "", keyword: "", include_voided: false });
  const [query, setQuery] = useState<any>({});
  const list = useApi<{ items: any[] }>("journals", query);
  const [error, setError] = useState<unknown>(null);
  const [message, setMessage] = useState("");

  async function voidEntry(id: string) {
    if (!confirm("この仕訳を取り消しますか？（締め済みの期間の仕訳は当期に逆仕訳を作ります）")) return;
    setError(null);
    try {
      const r = await api(`journals/${id}/void`, { body: {} });
      setMessage(r.reversal_entry_id ? "逆仕訳を作成しました" : "取り消しました");
      list.reload();
    } catch (err) {
      setError(err);
    }
  }

  return (
    <>
      <PageTitle title="仕訳">取引年月日・金額・取引先などを組み合わせて検索できます（FR-70）。</PageTitle>
      <Card title="検索" actions={<Link className="button primary" href="/journals/new">仕訳を入力</Link>}>
        <form className="form" onSubmit={(e) => { e.preventDefault(); setQuery({ ...filters }); }}>
          <Field label="取引日（から）"><input type="date" value={filters.from} onChange={(e) => setFilters({ ...filters, from: e.target.value })} /></Field>
          <Field label="取引日（まで）"><input type="date" value={filters.to} onChange={(e) => setFilters({ ...filters, to: e.target.value })} /></Field>
          <Field label="金額（以上）"><input type="number" className="num" value={filters.amount_min} onChange={(e) => setFilters({ ...filters, amount_min: e.target.value })} /></Field>
          <Field label="金額（以下）"><input type="number" className="num" value={filters.amount_max} onChange={(e) => setFilters({ ...filters, amount_max: e.target.value })} /></Field>
          <Field label="取引先"><input value={filters.counterparty} onChange={(e) => setFilters({ ...filters, counterparty: e.target.value })} /></Field>
          <Field label="勘定科目">
            <select value={filters.account} onChange={(e) => setFilters({ ...filters, account: e.target.value })}>
              <option value="">すべて</option>
              {accounts.data?.items.map((a) => <option key={a.code} value={a.code}>{a.code} {a.name}</option>)}
            </select>
          </Field>
          <Field label="摘要"><input value={filters.keyword} onChange={(e) => setFilters({ ...filters, keyword: e.target.value })} /></Field>
          <Field label="取消済み">
            <span className="check"><input type="checkbox" checked={filters.include_voided} onChange={(e) => setFilters({ ...filters, include_voided: e.target.checked })} /> 含める</span>
          </Field>
          <button className="primary">検索</button>
        </form>
      </Card>
      <ErrorBox error={error || list.error} />
      {message ? <p className="muted">{message}</p> : null}
      <Card>
        <div className="table-wrap">
          <table>
            <thead>
              <tr><th>日付</th><th>摘要</th><th>取引先</th><th>借方</th><th>貸方</th><th className="num">金額</th><th>入力元</th><th>証憑</th><th /></tr>
            </thead>
            <tbody>
              {list.data?.items.map((e) => (
                <tr key={e.id} className={e.voided_at ? "voided" : undefined}>
                  <td>{e.transaction_date}</td>
                  <td>
                    {e.description}
                    {e.entertainment?.per_person_amount != null ? <div className="small muted">1人あたり {yen(e.entertainment.per_person_amount)}円</div> : null}
                  </td>
                  <td>{e.counterparty_name}</td>
                  <td>{e.lines.filter((l: any) => l.side === "debit").map((l: any) => <div key={l.id}>{l.account_name} <span className="muted small">{l.tax_code}</span></div>)}</td>
                  <td>{e.lines.filter((l: any) => l.side === "credit").map((l: any) => <div key={l.id}>{l.account_name}</div>)}</td>
                  <td className="num">{yen(e.total_amount)}</td>
                  <td><span className="badge">{SOURCE_LABELS[e.source] ?? e.source}</span></td>
                  <td>{e.attachment_ids.map((a: string, i: number) => <a key={a} href={`/api/proxy/attachments/${a}/file`} target="_blank" rel="noreferrer">📎{i + 1} </a>)}</td>
                  <td className="actions">
                    <Link href={`/journals/new?copy=${e.id}`}>複製</Link>
                    {!e.voided_at && e.source !== "carryover" ? <button className="danger" onClick={() => voidEntry(e.id)}>取消</button> : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {list.data && list.data.items.length === 0 ? <p className="muted">該当する仕訳はありません。</p> : null}
      </Card>
    </>
  );
}
