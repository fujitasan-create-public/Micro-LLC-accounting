"use client";

import { useState } from "react";
import { Card, ErrorBox, Field, PageTitle } from "@/components/ui";
import { api, todayIso, useApi } from "@/lib/client";

const size = (n: number) => (n >= 1024 * 1024 ? `${(n / 1024 / 1024).toFixed(1)}MB` : `${Math.max(1, Math.round(n / 1024))}KB`);

export default function DocumentsPage() {
  const cats = useApi<{ items: string[] }>("documents/categories");
  const [filters, setFilters] = useState({ category: "", keyword: "", include_archived: false });
  const [query, setQuery] = useState<any>({});
  const list = useApi<{ items: any[] }>("documents", query);
  const empty = { title: "", category: "契約書", party: "", document_date: "", expiry_date: "", notes: "" };
  const [form, setForm] = useState(empty);
  const [editing, setEditing] = useState<any>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  async function upload(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    const input = e.currentTarget.querySelector<HTMLInputElement>('input[type="file"]')!;
    const files = Array.from(input.files ?? []);
    if (files.length === 0) return;
    setBusy(true);
    try {
      // 複数ファイルを選んだ場合は1ファイル1件として登録する（書類名が空ならファイル名を使う）
      for (const f of files) {
        const fd = new FormData();
        fd.set("file", f);
        fd.set("title", form.title && files.length === 1 ? form.title : form.title ? `${form.title}（${f.name}）` : f.name.replace(/\.[^.]+$/, ""));
        fd.set("category", form.category);
        for (const k of ["party", "document_date", "expiry_date", "notes"] as const) if (form[k]) fd.set(k, form[k]);
        await api("documents", { form: fd });
      }
      setForm({ ...empty, category: form.category });
      input.value = "";
      list.reload();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  async function saveEdit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await api(`documents/${editing.id}`, {
        method: "PATCH",
        body: {
          title: editing.title, category: editing.category, party: editing.party || null, notes: editing.notes || null,
          document_date: editing.document_date || null, expiry_date: editing.expiry_date || null,
        },
      });
      setEditing(null);
      list.reload();
    } catch (err) {
      setError(err);
    }
  }

  async function archive(d: any, archived: boolean) {
    if (archived && !confirm(`「${d.title}」を非表示にしますか？（ファイルは残り、「非表示の書類も表示」で戻せます）`)) return;
    try {
      await api(`documents/${d.id}`, { method: "PATCH", body: { archived } });
      list.reload();
    } catch (err) {
      setError(err);
    }
  }

  const today = todayIso();
  const categories = cats.data?.items ?? [];

  return (
    <>
      <PageTitle title="書類管理">契約書・登記・口座開設・届出など、会社の書類をまとめて保管します。</PageTitle>
      <ErrorBox error={error} />
      <Card title="書類を追加">
        <form className="form" onSubmit={upload}>
          <Field label="ファイル（複数選択可・30MBまで）"><input type="file" multiple required /></Field>
          <Field label="種類">
            <select value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })}>
              {categories.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
          </Field>
          <Field label="書類名" hint="空欄ならファイル名"><input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} placeholder="例: 業務委託契約書" /></Field>
          <Field label="相手方・提出先"><input value={form.party} onChange={(e) => setForm({ ...form, party: e.target.value })} placeholder="例: ○○株式会社、○○銀行、渋谷税務署" /></Field>
          <Field label="書類の日付"><input type="date" value={form.document_date} onChange={(e) => setForm({ ...form, document_date: e.target.value })} /></Field>
          <Field label="期限・更新日"><input type="date" value={form.expiry_date} onChange={(e) => setForm({ ...form, expiry_date: e.target.value })} /></Field>
          <Field label="メモ" wide><input value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} /></Field>
          <button className="primary" disabled={busy}>{busy ? "保存中…" : "保存"}</button>
        </form>
      </Card>

      <Card title="書類の一覧">
        <form className="form" onSubmit={(e) => { e.preventDefault(); setQuery({ ...filters }); }} style={{ marginBottom: 10 }}>
          <Field label="種類">
            <select value={filters.category} onChange={(e) => setFilters({ ...filters, category: e.target.value })}>
              <option value="">すべて</option>
              {categories.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
          </Field>
          <Field label="キーワード" hint="書類名・相手方・メモ・ファイル名"><input value={filters.keyword} onChange={(e) => setFilters({ ...filters, keyword: e.target.value })} /></Field>
          <Field label=" "><span className="check"><input type="checkbox" checked={filters.include_archived} onChange={(e) => setFilters({ ...filters, include_archived: e.target.checked })} /> 非表示の書類も表示</span></Field>
          <button>検索</button>
        </form>
        <div className="table-wrap">
          <table>
            <thead><tr><th>種類</th><th>書類名</th><th>相手方・提出先</th><th>書類の日付</th><th>期限・更新日</th><th>メモ</th><th>ファイル</th><th /></tr></thead>
            <tbody>
              {list.data?.items.map((d) => (
                <tr key={d.id} className={d.archived_at ? "voided" : undefined}>
                  <td>{d.category}</td>
                  <td>{d.title}</td>
                  <td>{d.party}</td>
                  <td>{d.document_date}</td>
                  <td>{d.expiry_date ? <span style={d.expiry_date < today ? { color: "var(--danger)" } : undefined}>{d.expiry_date}{d.expiry_date < today ? "（期限切れ）" : ""}</span> : ""}</td>
                  <td>{d.notes}</td>
                  <td>
                    <a href={`/api/proxy/documents/${d.id}/file`} target="_blank" rel="noreferrer">開く</a>{" "}
                    <a href={`/api/proxy/documents/${d.id}/file?download=true`}>保存</a>
                    <div className="small muted">{d.original_filename}（{size(d.size_bytes)}）</div>
                  </td>
                  <td className="actions">
                    <button onClick={() => setEditing({ ...d, party: d.party ?? "", notes: d.notes ?? "", document_date: d.document_date ?? "", expiry_date: d.expiry_date ?? "" })}>編集</button>
                    {d.archived_at ? <button onClick={() => archive(d, false)}>戻す</button> : <button onClick={() => archive(d, true)}>非表示</button>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {list.data?.items.length === 0 ? <p className="muted">書類はまだありません。</p> : null}
      </Card>

      {editing ? (
        <Card title={`書類の編集: ${editing.original_filename}`}>
          <form className="form" onSubmit={saveEdit}>
            <Field label="種類">
              <select value={editing.category} onChange={(e) => setEditing({ ...editing, category: e.target.value })}>
                {categories.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
            </Field>
            <Field label="書類名"><input value={editing.title} onChange={(e) => setEditing({ ...editing, title: e.target.value })} required /></Field>
            <Field label="相手方・提出先"><input value={editing.party} onChange={(e) => setEditing({ ...editing, party: e.target.value })} /></Field>
            <Field label="書類の日付"><input type="date" value={editing.document_date} onChange={(e) => setEditing({ ...editing, document_date: e.target.value })} /></Field>
            <Field label="期限・更新日"><input type="date" value={editing.expiry_date} onChange={(e) => setEditing({ ...editing, expiry_date: e.target.value })} /></Field>
            <Field label="メモ" wide><input value={editing.notes} onChange={(e) => setEditing({ ...editing, notes: e.target.value })} /></Field>
            <div className="actions"><button className="primary">保存</button><button type="button" onClick={() => setEditing(null)}>キャンセル</button></div>
          </form>
        </Card>
      ) : null}
    </>
  );
}
