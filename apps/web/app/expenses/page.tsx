"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { Card, ErrorBox, Field, Notice, PageTitle, Warnings } from "@/components/ui";
import { api, todayIso, useApi, yen, type Warning } from "@/lib/client";

const PAY_TYPES: Record<string, string> = { bank: "口座振込・引落し", credit_card: "クレジットカード", cash: "現金", officer_advance: "社長が立替" };

/** 経費を1件ずつ入れる画面。借方＝経費の科目、貸方＝支払方法に対応する科目 の仕訳を作る */
export default function ExpensesPage() {
  const accounts = useApi<{ items: any[] }>("accounts", { active_only: true });
  const taxCodes = useApi<{ items: any[] }>("tax-codes");
  const cps = useApi<{ items: any[] }>("counterparties");
  const pas = useApi<{ items: any[] }>("payment-accounts");
  const month = todayIso().slice(0, 7);
  const recent = useApi<{ items: any[] }>("journals", { debit_category: "expense", from: `${month}-01` });

  const empty = { date: todayIso(), counterparty_id: "", description: "", account_code: "", amount: "", tax_code: "", payment_account_id: "" };
  const [form, setForm] = useState<any>(empty);
  const [ent, setEnt] = useState({ participants: "", headcount: "", venue: "", is_food_and_drink: true });
  const [file, setFile] = useState<File | null>(null);
  const [channel, setChannel] = useState("electronic");
  const [newCp, setNewCp] = useState<{ name: string; entity_type: string; invoice_registration_number: string } | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [warnings, setWarnings] = useState<Warning[]>([]);
  const [saved, setSaved] = useState("");
  const [busy, setBusy] = useState(false);

  const expenseAccounts = useMemo(
    () => (accounts.data?.items ?? []).filter((a) => a.category === "expense" && !["500", "510", "620", "700"].includes(a.code)),
    [accounts.data],
  );
  const account = expenseAccounts.find((a) => a.code === form.account_code);
  const pa = pas.data?.items.find((p) => p.id === form.payment_account_id);
  const cp = cps.data?.items.find((c) => c.id === form.counterparty_id);
  const amount = Number(form.amount) || 0;
  // 役員報酬・減価償却費・法人税等は経費の一覧に含めない
  const NOT_EXPENSE = ["500", "510", "620", "700"];
  const expenseRows = (recent.data?.items ?? []).filter((e) =>
    e.lines.some((l: any) => l.side === "debit" && !NOT_EXPENSE.includes(l.account_code) && l.account_code !== "160"));
  const perPerson = Number(ent.headcount) > 0 ? Math.floor(amount / Number(ent.headcount)) : null;

  async function addCounterparty() {
    if (!newCp?.name) return;
    try {
      const c = await api("counterparties", { body: { ...newCp, invoice_registration_number: newCp.invoice_registration_number || null } });
      await cps.reload();
      setForm({ ...form, counterparty_id: c.id });
      setNewCp(null);
    } catch (err) {
      setError(err);
    }
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setWarnings([]);
    setSaved("");
    if (!pa) return setError(new Error("支払方法を選んでください"));
    setBusy(true);
    try {
      const r = await api("journals", {
        body: {
          transaction_date: form.date,
          description: form.description || account?.name,
          counterparty_id: form.counterparty_id || null,
          payment_account_id: pa.id,
          lines: [
            { side: "debit", account_code: form.account_code, amount, tax_code: form.tax_code || null },
            { side: "credit", account_code: pa.linked_account_code, amount, tax_code: "NT" },
          ],
          entertainment_detail: form.account_code === "590"
            ? { participants: ent.participants, headcount: Number(ent.headcount) || 0, venue: ent.venue || null, is_food_and_drink: ent.is_food_and_drink, is_internal_only: false }
            : null,
        },
      });
      let ws: Warning[] = r.warnings ?? [];
      if (file) {
        const fd = new FormData();
        fd.set("file", file);
        fd.set("received_date", form.date);
        fd.set("transaction_date", form.date);
        fd.set("amount", String(amount));
        fd.set("counterparty_name", cp?.name ?? (form.description || account?.name || "不明"));
        fd.set("receipt_channel", channel);
        fd.set("entry_id", r.entry.id);
        const a = await api("attachments", { form: fd });
        ws = ws.concat(a.warnings ?? []);
      }
      setWarnings(ws);
      setSaved(`登録しました: ${form.date} ${account?.name} ${yen(amount)}円`);
      setForm({ ...empty, date: form.date, payment_account_id: form.payment_account_id });
      setFile(null);
      (e.target as HTMLFormElement).querySelector<HTMLInputElement>('input[type="file"]')!.value = "";
      recent.reload();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageTitle title="経費の入力">支払った経費を1件ずつ登録します。仕訳は自動で作られます。</PageTitle>
      {pas.data && pas.data.items.length === 0 ? (
        <Notice>先に<Link href="/masters">科目・取引先・口座</Link>で、支払に使う口座・現金・カードを登録してください。</Notice>
      ) : null}
      <Card title="経費を登録">
        <form onSubmit={submit}>
          <div className="form">
            <Field label="支払日"><input type="date" value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} required /></Field>
            <Field label="勘定科目">
              <select value={form.account_code} required
                onChange={(e) => setForm({ ...form, account_code: e.target.value, tax_code: expenseAccounts.find((a) => a.code === e.target.value)?.default_tax_code ?? "" })}>
                <option value="">選択してください</option>
                {expenseAccounts.map((a) => <option key={a.code} value={a.code}>{a.name}</option>)}
              </select>
            </Field>
            <Field label="金額（税込）"><input type="number" min={1} className="num" value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} required /></Field>
            <Field label="支払方法">
              <select value={form.payment_account_id} onChange={(e) => setForm({ ...form, payment_account_id: e.target.value })} required>
                <option value="">選択してください</option>
                {pas.data?.items.map((p) => <option key={p.id} value={p.id}>{p.name}（{PAY_TYPES[p.type]}）</option>)}
              </select>
            </Field>
            <Field label={`支払先${account?.requires_counterparty ? "（必須）" : ""}`}>
              <select value={form.counterparty_id} onChange={(e) => setForm({ ...form, counterparty_id: e.target.value })} required={!!account?.requires_counterparty}>
                <option value="">指定しない</option>
                {cps.data?.items.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
            </Field>
            <Field label=" ">
              <button type="button" onClick={() => setNewCp(newCp ? null : { name: "", entity_type: "corporation", invoice_registration_number: "" })}>＋支払先を追加</button>
            </Field>
            <Field label="内容（摘要）" wide><input value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} placeholder="例: 事務用品（プリンタ用紙）" /></Field>
            <Field label="消費税の区分">
              <select value={form.tax_code} onChange={(e) => setForm({ ...form, tax_code: e.target.value })}>
                <option value="">科目の初期値</option>
                {taxCodes.data?.items.filter((t) => ["taxable_purchase", "non_taxable"].includes(t.kind)).map((t) => <option key={t.code} value={t.code}>{t.name}</option>)}
              </select>
            </Field>
            <Field label="領収書・請求書のファイル"><input type="file" onChange={(e) => setFile(e.target.files?.[0] ?? null)} /></Field>
            {file ? (
              <Field label="受け取り方">
                <select value={channel} onChange={(e) => setChannel(e.target.value)}>
                  <option value="electronic">メール・Webで受け取った</option>
                  <option value="paper_scanned">紙をスキャンした</option>
                  <option value="paper">紙（原本を保管）</option>
                </select>
              </Field>
            ) : null}
          </div>

          {newCp ? (
            <div className="alert alert-info">
              <div className="form">
                <Field label="支払先の名称"><input value={newCp.name} onChange={(e) => setNewCp({ ...newCp, name: e.target.value })} /></Field>
                <Field label="法人・個人">
                  <select value={newCp.entity_type} onChange={(e) => setNewCp({ ...newCp, entity_type: e.target.value })}>
                    <option value="corporation">法人</option><option value="individual">個人</option>
                  </select>
                </Field>
                <Field label="インボイス登録番号（分かれば）"><input value={newCp.invoice_registration_number} onChange={(e) => setNewCp({ ...newCp, invoice_registration_number: e.target.value })} placeholder="T1234567890123" /></Field>
                <button type="button" className="primary" onClick={addCounterparty}>追加して選択</button>
              </div>
            </div>
          ) : null}

          {form.account_code === "590" ? (
            <div className="alert alert-info">
              <strong>交際費の記録</strong>（1人あたり1万円以下の飲食費は、記録があれば交際費から除けます）
              <div className="form" style={{ marginTop: 6 }}>
                <Field label="参加者（氏名・関係）" wide><input value={ent.participants} onChange={(e) => setEnt({ ...ent, participants: e.target.value })} placeholder="例: ○○社 山田部長、当社 代表社員" /></Field>
                <Field label="人数"><input type="number" min={1} className="num" value={ent.headcount} onChange={(e) => setEnt({ ...ent, headcount: e.target.value })} /></Field>
                <Field label="店名"><input value={ent.venue} onChange={(e) => setEnt({ ...ent, venue: e.target.value })} /></Field>
                <Field label="飲食"><span className="check"><input type="checkbox" checked={ent.is_food_and_drink} onChange={(e) => setEnt({ ...ent, is_food_and_drink: e.target.checked })} /> 飲食代</span></Field>
              </div>
              {perPerson !== null ? <p style={{ margin: "4px 0 0" }}>1人あたり {yen(perPerson)}円</p> : null}
            </div>
          ) : null}

          {amount >= 100000 ? (
            <Notice>10万円以上のパソコン・機器などは、経費ではなく<Link href="/assets">固定資産</Link>として登録すると、償却方法を選べます。</Notice>
          ) : null}
          {pa?.type === "officer_advance" ? <Notice>社長が個人のお金で立て替えた経費として、「役員借入金」（会社から社長への借り）で記録します。</Notice> : null}
          {cp && !cp.invoice_registration_number && ["P10", "P08", ""].includes(form.tax_code) && account?.default_tax_code?.startsWith("P") ? (
            <Notice>支払先にインボイス登録番号がないため、消費税の控除は経過措置（一部のみ控除）で計算します。</Notice>
          ) : null}

          <div className="actions" style={{ marginTop: 10 }}>
            <button className="primary" disabled={busy}>登録</button>
            <span className="muted small">借方: {account?.name ?? "（勘定科目）"} ／ 貸方: {pa ? accounts.data?.items.find((a) => a.code === pa.linked_account_code)?.name : "（支払方法）"}</span>
          </div>
        </form>
        <ErrorBox error={error} />
        <Warnings items={warnings} />
        {saved ? <p>{saved}</p> : null}
      </Card>

      <Card title={`今月の経費（${month}）`} actions={<Link href="/journals">すべての仕訳を見る</Link>}>
        <div className="table-wrap">
          <table>
            <thead><tr><th>日付</th><th>勘定科目</th><th>内容</th><th>支払先</th><th>支払方法</th><th className="num">金額</th><th>領収書</th></tr></thead>
            <tbody>
              {expenseRows.map((e) => (
                <tr key={e.id}>
                  <td>{e.transaction_date}</td>
                  <td>{e.lines.filter((l: any) => l.side === "debit").map((l: any) => l.account_name).join("、")}</td>
                  <td>{e.description}</td>
                  <td>{e.counterparty_name}</td>
                  <td>{e.payment_account_name}</td>
                  <td className="num">{yen(e.total_amount)}</td>
                  <td>{e.attachment_ids.map((a: string, i: number) => <a key={a} href={`/api/proxy/attachments/${a}/file`} target="_blank" rel="noreferrer">表示{e.attachment_ids.length > 1 ? i + 1 : ""} </a>)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {recent.data && expenseRows.length === 0 ? <p className="muted">今月の経費はまだありません。</p> : null}
      </Card>
    </>
  );
}
