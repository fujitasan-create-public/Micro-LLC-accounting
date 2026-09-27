"use client";

import { useState } from "react";
import { CATEGORY_LABELS, Card, ErrorBox, Field, PageTitle } from "@/components/ui";
import { api, useApi } from "@/lib/client";

export default function MastersPage() {
  return (
    <>
      <PageTitle title="科目・取引先・口座">勘定科目の追加・名称変更・非表示、取引先、口座・支払手段</PageTitle>
      <Counterparties />
      <PaymentAccounts />
      <Accounts />
    </>
  );
}

function Accounts() {
  const accounts = useApi<{ items: any[] }>("accounts");
  const taxCodes = useApi<{ items: any[] }>("tax-codes");
  const [form, setForm] = useState({ code: "", name: "", category: "expense", statement_section: "販売費及び一般管理費", default_tax_code: "P10", requires_counterparty: false });
  const [error, setError] = useState<unknown>(null);

  async function add(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await api("accounts", { body: { ...form, is_active: true } });
      setForm({ ...form, code: "", name: "" });
      accounts.reload();
    } catch (err) {
      setError(err);
    }
  }

  async function patch(code: string, body: any) {
    setError(null);
    try {
      await api(`accounts/${code}`, { method: "PATCH", body });
      accounts.reload();
    } catch (err) {
      setError(err);
    }
  }

  return (
    <Card title="勘定科目">
      <ErrorBox error={error} />
      <div className="table-wrap">
        <table>
          <thead>
            <tr><th>コード</th><th>科目名</th><th>区分</th><th>表示区分</th><th>税区分の初期値</th><th>取引先必須</th><th>表示</th></tr>
          </thead>
          <tbody>
            {accounts.data?.items.map((a) => (
              <tr key={a.code} className={a.is_active ? undefined : "voided"}>
                <td>{a.code}</td>
                <td>
                  <input defaultValue={a.name} onBlur={(e) => e.target.value !== a.name && patch(a.code, { name: e.target.value })} />
                </td>
                <td>{CATEGORY_LABELS[a.category]}</td>
                <td>{a.statement_section}</td>
                <td>
                  <select value={a.default_tax_code} onChange={(e) => patch(a.code, { default_tax_code: e.target.value })}>
                    {taxCodes.data?.items.map((t) => <option key={t.code} value={t.code}>{t.name}</option>)}
                  </select>
                </td>
                <td><input type="checkbox" checked={!!a.requires_counterparty} onChange={(e) => patch(a.code, { requires_counterparty: e.target.checked })} /></td>
                <td>
                  <button onClick={() => patch(a.code, { is_active: !a.is_active })}>{a.is_active ? "非表示にする" : "表示する"}</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <h3>科目の追加</h3>
      <form className="form" onSubmit={add}>
        <Field label="コード"><input value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })} required /></Field>
        <Field label="科目名"><input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required /></Field>
        <Field label="区分">
          <select value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })}>
            {Object.entries(CATEGORY_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </Field>
        <Field label="決算書上の表示区分">
          <input list="sections" value={form.statement_section} onChange={(e) => setForm({ ...form, statement_section: e.target.value })} required />
          <datalist id="sections">
            {["流動資産", "有形固定資産", "無形固定資産", "投資その他の資産", "流動負債", "固定負債", "資本金", "利益剰余金", "売上高", "販売費及び一般管理費", "営業外収益", "営業外費用", "特別利益", "特別損失", "法人税等"].map((s) => <option key={s} value={s} />)}
          </datalist>
        </Field>
        <Field label="税区分の初期値">
          <select value={form.default_tax_code} onChange={(e) => setForm({ ...form, default_tax_code: e.target.value })}>
            {taxCodes.data?.items.map((t) => <option key={t.code} value={t.code}>{t.name}</option>)}
          </select>
        </Field>
        <Field label="取引先必須">
          <span className="check"><input type="checkbox" checked={form.requires_counterparty} onChange={(e) => setForm({ ...form, requires_counterparty: e.target.checked })} /> 必須</span>
        </Field>
        <button className="primary">追加</button>
      </form>
    </Card>
  );
}

function Counterparties() {
  const cps = useApi<{ items: any[] }>("counterparties");
  const empty = { name: "", entity_type: "corporation", invoice_registration_number: "", address: "", bank_account: "", is_client: false };
  const [form, setForm] = useState<any>(empty);
  const [editing, setEditing] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const body = { ...form, invoice_registration_number: form.invoice_registration_number || null };
      if (editing) await api(`counterparties/${editing}`, { method: "PATCH", body });
      else await api("counterparties", { body });
      setForm(empty);
      setEditing(null);
      cps.reload();
    } catch (err) {
      setError(err);
    }
  }

  return (
    <Card title="取引先">
      <div className="table-wrap">
        <table>
          <thead><tr><th>名称</th><th>種別</th><th>インボイス登録番号</th><th>住所</th><th>報酬の支払元</th><th /></tr></thead>
          <tbody>
            {cps.data?.items.map((c) => (
              <tr key={c.id}>
                <td>{c.name}</td>
                <td>{c.entity_type === "corporation" ? "法人" : "個人"}</td>
                <td>{c.invoice_registration_number ?? <span className="muted">なし（仕入は経過措置）</span>}</td>
                <td>{c.address}</td>
                <td>{c.is_client ? "✓" : ""}</td>
                <td><button onClick={() => { setEditing(c.id); setForm({ ...c, invoice_registration_number: c.invoice_registration_number ?? "", address: c.address ?? "", bank_account: c.bank_account ?? "", is_client: !!c.is_client }); }}>編集</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <h3>{editing ? "取引先の編集" : "取引先の追加"}</h3>
      <form className="form" onSubmit={save}>
        <Field label="名称"><input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required /></Field>
        <Field label="種別" hint="個人への報酬は源泉徴収の警告が出ます">
          <select value={form.entity_type} onChange={(e) => setForm({ ...form, entity_type: e.target.value })}>
            <option value="corporation">法人</option>
            <option value="individual">個人</option>
          </select>
        </Field>
        <Field label="インボイス登録番号" hint="T＋13桁"><input value={form.invoice_registration_number} onChange={(e) => setForm({ ...form, invoice_registration_number: e.target.value })} pattern="T\d{13}" /></Field>
        <Field label="住所" hint="地代家賃の内訳書に必要"><input value={form.address} onChange={(e) => setForm({ ...form, address: e.target.value })} /></Field>
        <Field label="振込先"><input value={form.bank_account} onChange={(e) => setForm({ ...form, bank_account: e.target.value })} /></Field>
        <Field label="報酬の支払元（売上先）">
          <span className="check"><input type="checkbox" checked={form.is_client} onChange={(e) => setForm({ ...form, is_client: e.target.checked })} /> はい</span>
        </Field>
        <div className="actions">
          <button className="primary">{editing ? "更新" : "追加"}</button>
          {editing ? <button type="button" onClick={() => { setEditing(null); setForm(empty); }}>キャンセル</button> : null}
        </div>
      </form>
      <ErrorBox error={error} />
    </Card>
  );
}

const PA_TYPES: Record<string, [string, string]> = {
  bank: ["銀行口座", "110"],
  credit_card: ["クレジットカード", "200"],
  cash: ["現金", "100"],
  officer_advance: ["役員による立替", "250"],
};

function PaymentAccounts() {
  const pas = useApi<{ items: any[] }>("payment-accounts");
  const accounts = useApi<{ items: any[] }>("accounts", { active_only: true });
  const empty = { name: "", type: "bank", bank_name: "", branch_name: "", account_kind: "普通", account_number: "", linked_account_code: "110", csv_import_format: "" };
  const [form, setForm] = useState<any>(empty);
  const [error, setError] = useState<unknown>(null);

  async function add(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await api("payment-accounts", { body: form });
      setForm(empty);
      pas.reload();
    } catch (err) {
      setError(err);
    }
  }

  return (
    <Card title="口座・支払手段">
      <div className="table-wrap">
        <table>
          <thead><tr><th>表示名</th><th>種類</th><th>金融機関</th><th>支店</th><th>種別</th><th>口座番号</th><th>勘定科目</th></tr></thead>
          <tbody>
            {pas.data?.items.map((p) => (
              <tr key={p.id}>
                <td>{p.name}</td><td>{PA_TYPES[p.type][0]}</td><td>{p.bank_name}</td><td>{p.branch_name}</td><td>{p.account_kind}</td><td>{p.account_number}</td>
                <td>{accounts.data?.items.find((a) => a.code === p.linked_account_code)?.name ?? p.linked_account_code}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <h3>口座・支払手段の追加</h3>
      <form className="form" onSubmit={add}>
        <Field label="表示名"><input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required /></Field>
        <Field label="種類" hint="役員による立替は役員借入金に紐付きます">
          <select value={form.type} onChange={(e) => setForm({ ...form, type: e.target.value, linked_account_code: PA_TYPES[e.target.value][1] })}>
            {Object.entries(PA_TYPES).map(([k, [label]]) => <option key={k} value={k}>{label}</option>)}
          </select>
        </Field>
        {form.type === "bank" ? (
          <>
            <Field label="金融機関名"><input value={form.bank_name} onChange={(e) => setForm({ ...form, bank_name: e.target.value })} /></Field>
            <Field label="支店名"><input value={form.branch_name} onChange={(e) => setForm({ ...form, branch_name: e.target.value })} /></Field>
            <Field label="種別"><input value={form.account_kind} onChange={(e) => setForm({ ...form, account_kind: e.target.value })} /></Field>
            <Field label="口座番号"><input value={form.account_number} onChange={(e) => setForm({ ...form, account_number: e.target.value })} /></Field>
          </>
        ) : null}
        <Field label="対応する勘定科目">
          <select value={form.linked_account_code} onChange={(e) => setForm({ ...form, linked_account_code: e.target.value })}>
            {accounts.data?.items.filter((a) => a.category === "asset" || a.category === "liability").map((a) => <option key={a.code} value={a.code}>{a.code} {a.name}</option>)}
          </select>
        </Field>
        <button className="primary">追加</button>
      </form>
      <ErrorBox error={error} />
    </Card>
  );
}
