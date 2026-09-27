"use client";

import { useState } from "react";
import { Card, ErrorBox, Field, PageTitle, Warnings } from "@/components/ui";
import { api, todayIso, useApi, yen, type Warning } from "@/lib/client";

const CHANNELS: Record<string, string> = { electronic: "電子取引", paper_scanned: "紙をスキャン", paper: "紙" };

export default function AttachmentsPage() {
  const [filters, setFilters] = useState<any>({ from: "", to: "", amount_min: "", amount_max: "", counterparty: "" });
  const [query, setQuery] = useState<any>({});
  const list = useApi<{ items: any[] }>("attachments", query);
  const [file, setFile] = useState<File | null>(null);
  const [meta, setMeta] = useState({ received_date: todayIso(), transaction_date: todayIso(), amount: "", counterparty_name: "", receipt_channel: "electronic" });
  const [error, setError] = useState<unknown>(null);
  const [warnings, setWarnings] = useState<Warning[]>([]);

  async function upload(e: React.FormEvent) {
    e.preventDefault();
    if (!file) return;
    setError(null);
    try {
      const fd = new FormData();
      fd.set("file", file);
      Object.entries(meta).forEach(([k, v]) => fd.set(k, v));
      const r = await api("attachments", { form: fd });
      setWarnings(r.warnings ?? []);
      setFile(null);
      (e.target as HTMLFormElement).reset();
      list.reload();
    } catch (err) {
      setError(err);
    }
  }

  async function voidAttachment(id: string) {
    if (!confirm("この証憑を取り消しますか？（ファイルは保存期間中は削除されません）")) return;
    try {
      await api(`attachments/${id}/void`, { body: {} });
      list.reload();
    } catch (err) {
      setError(err);
    }
  }

  return (
    <>
      <PageTitle title="証憑">電子で受け取った請求書・領収書は電子データのまま保存します。取引年月日・金額・取引先で検索できます。</PageTitle>
      <Card title="証憑の保存">
        <form className="form" onSubmit={upload}>
          <Field label="ファイル（20MBまで）"><input type="file" required onChange={(e) => setFile(e.target.files?.[0] ?? null)} /></Field>
          <Field label="受領日"><input type="date" value={meta.received_date} onChange={(e) => setMeta({ ...meta, received_date: e.target.value })} required /></Field>
          <Field label="取引年月日"><input type="date" value={meta.transaction_date} onChange={(e) => setMeta({ ...meta, transaction_date: e.target.value })} required /></Field>
          <Field label="取引金額"><input type="number" className="num" value={meta.amount} onChange={(e) => setMeta({ ...meta, amount: e.target.value })} required /></Field>
          <Field label="取引先"><input value={meta.counterparty_name} onChange={(e) => setMeta({ ...meta, counterparty_name: e.target.value })} required /></Field>
          <Field label="受領方法">
            <select value={meta.receipt_channel} onChange={(e) => setMeta({ ...meta, receipt_channel: e.target.value })}>
              {Object.entries(CHANNELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </Field>
          <button className="primary">保存</button>
        </form>
        <p className="muted small">仕訳への紐付けは、仕訳の入力画面で添付するか、保存後に仕訳の画面から行います。</p>
        <ErrorBox error={error} />
        <Warnings items={warnings} />
      </Card>
      <Card title="検索">
        <form className="form" onSubmit={(e) => { e.preventDefault(); setQuery({ ...filters }); }}>
          <Field label="取引日（から）"><input type="date" value={filters.from} onChange={(e) => setFilters({ ...filters, from: e.target.value })} /></Field>
          <Field label="取引日（まで）"><input type="date" value={filters.to} onChange={(e) => setFilters({ ...filters, to: e.target.value })} /></Field>
          <Field label="金額（以上）"><input type="number" className="num" value={filters.amount_min} onChange={(e) => setFilters({ ...filters, amount_min: e.target.value })} /></Field>
          <Field label="金額（以下）"><input type="number" className="num" value={filters.amount_max} onChange={(e) => setFilters({ ...filters, amount_max: e.target.value })} /></Field>
          <Field label="取引先"><input value={filters.counterparty} onChange={(e) => setFilters({ ...filters, counterparty: e.target.value })} /></Field>
          <button className="primary">検索</button>
        </form>
        <div className="table-wrap" style={{ marginTop: 12 }}>
          <table>
            <thead><tr><th>取引年月日</th><th>取引先</th><th className="num">金額</th><th>受領日</th><th>受領方法</th><th>ファイル</th><th>SHA-256</th><th>仕訳</th><th /></tr></thead>
            <tbody>
              {list.data?.items.map((a) => (
                <tr key={a.id}>
                  <td>{a.transaction_date}</td>
                  <td>{a.counterparty_name}</td>
                  <td className="num">{yen(a.amount)}</td>
                  <td>{a.received_date}</td>
                  <td>{CHANNELS[a.receipt_channel]}</td>
                  <td><a href={`/api/proxy/attachments/${a.id}/file`} target="_blank" rel="noreferrer">{a.original_filename}</a></td>
                  <td className="small muted" title={a.sha256}>{a.sha256.slice(0, 12)}…</td>
                  <td>{a.entry_ids ? "紐付けあり" : <span className="muted">なし</span>}</td>
                  <td><button className="danger" onClick={() => voidAttachment(a.id)}>取消</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {list.data?.items.length === 0 ? <p className="muted">該当する証憑はありません。</p> : null}
      </Card>
    </>
  );
}
