"use client";

import { useState } from "react";
import { Card, ErrorBox, Field, PageTitle } from "@/components/ui";
import { api, buildUrl, useApi } from "@/lib/client";

export default function SettingsPage() {
  const list = useApi<{ items: any[] }>("rule-settings");
  const [filter, setFilter] = useState("");
  const [form, setForm] = useState({ key: "", value: "", effective_from: "", effective_to: "", note: "" });
  const [error, setError] = useState<unknown>(null);
  const [exporting, setExporting] = useState(false);

  async function add(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    let value: unknown;
    try {
      value = JSON.parse(form.value);
    } catch {
      setError(new Error("値は JSON で入力してください（数値はそのまま、文字列は \"...\" で囲む）"));
      return;
    }
    try {
      await api("rule-settings", { body: { ...form, value, effective_to: form.effective_to || null, note: form.note || null } });
      list.reload();
    } catch (err) {
      setError(err);
    }
  }

  async function exportAll() {
    setExporting(true);
    setError(null);
    try {
      const res = await fetch(buildUrl("exports"), { method: "POST" });
      if (!res.ok) throw new Error(`エクスポートに失敗しました（${res.status}）`);
      const blob = await res.blob();
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `accounting-export-${new Date().toISOString().slice(0, 10)}.zip`;
      a.click();
      URL.revokeObjectURL(a.href);
    } catch (err) {
      setError(err);
    } finally {
      setExporting(false);
    }
  }

  const rows = (list.data?.items ?? []).filter((r) => !filter || r.key.includes(filter) || (r.note ?? "").includes(filter));

  return (
    <>
      <PageTitle title="設定値・エクスポート">税率・控除率・しきい値は適用期間つきの設定値として管理します（BR-000 / NFR-07）。</PageTitle>
      <ErrorBox error={error} />
      <Card title="全データのエクスポート（FR-71 / NFR-04）">
        <p>仕訳・マスタ・証憑をまとめて ZIP（JSON Lines・CSV・証憑ファイル）でダウンロードします。本番のマイグレーション前には必ず実行してください。</p>
        <button className="primary" onClick={exportAll} disabled={exporting}>{exporting ? "作成中…" : "エクスポート"}</button>
      </Card>
      <Card title="設定値" actions={<input placeholder="キー・備考で絞り込み" value={filter} onChange={(e) => setFilter(e.target.value)} />}>
        <div className="table-wrap">
          <table>
            <thead><tr><th>キー</th><th>値</th><th>適用開始</th><th>適用終了</th><th>備考</th></tr></thead>
            <tbody>
              {rows.map((r) => (
                <tr key={`${r.key}-${r.effective_from}`}>
                  <td>{r.key}</td><td><code className="small">{r.value}</code></td><td>{r.effective_from}</td><td>{r.effective_to ?? ""}</td><td>{r.note}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <h3>設定値の追加・更新（同じキー・適用開始日なら上書き）</h3>
        <form className="form" onSubmit={add}>
          <Field label="キー"><input list="keys" value={form.key} onChange={(e) => setForm({ ...form, key: e.target.value })} required /></Field>
          <datalist id="keys">{[...new Set((list.data?.items ?? []).map((r) => r.key))].map((k) => <option key={k} value={k} />)}</datalist>
          <Field label="値（JSON）" wide><input value={form.value} onChange={(e) => setForm({ ...form, value: e.target.value })} required /></Field>
          <Field label="適用開始日"><input type="date" value={form.effective_from} onChange={(e) => setForm({ ...form, effective_from: e.target.value })} required /></Field>
          <Field label="適用終了日"><input type="date" value={form.effective_to} onChange={(e) => setForm({ ...form, effective_to: e.target.value })} /></Field>
          <Field label="備考"><input value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} /></Field>
          <button className="primary">保存</button>
        </form>
      </Card>
    </>
  );
}
