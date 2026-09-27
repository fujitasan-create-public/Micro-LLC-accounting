"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Card, ErrorBox, Field, Notice, PageTitle } from "@/components/ui";
import { api, useApi } from "@/lib/client";

const EMPTY_COMPANY = {
  trade_name: "",
  corporate_number: "",
  head_office_address: "",
  representative_name: "",
  incorporation_date: "",
  capital_amount: 0,
  fiscal_year_start_month: 4,
  blue_return_approved: true,
  blue_return_effective_from: "",
  tax_office: "",
  prefecture: "",
  municipality: "",
  accounting_tax_method: "tax_included",
};

const METHOD_LABELS: Record<string, string> = {
  standard: "本則課税",
  simplified: "簡易課税",
  two_tenths_special: "2割特例",
};

export default function SetupPage() {
  const status = useApi<any>("setup/status");
  return (
    <>
      <PageTitle title="初期設定">会社設定・会計期間・消費税設定を入力します（FR-01）。</PageTitle>
      {status.data?.completed ? (
        <Notice>
          初期設定は完了しています。設立初年度の開始残高（資本金の払込など）は<Link href="/journals/new?source=opening_balance">開始残高の入力</Link>
          から登録できます（FR-03）。
        </Notice>
      ) : null}
      <CompanyForm onSaved={status.reload} />
      <PeriodForm onSaved={status.reload} />
      <ConsumptionTaxForm onSaved={status.reload} />
    </>
  );
}

function CompanyForm({ onSaved }: { onSaved: () => void }) {
  const { data } = useApi<any>("company");
  const [form, setForm] = useState<any>(EMPTY_COMPANY);
  const [error, setError] = useState<unknown>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (data?.company) {
      setForm({ ...EMPTY_COMPANY, ...data.company, blue_return_approved: !!data.company.blue_return_approved,
        blue_return_effective_from: data.company.blue_return_effective_from ?? "" });
    }
  }, [data]);

  const set = (k: string) => (e: any) =>
    setForm({ ...form, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.type === "number" ? Number(e.target.value) : e.target.value });

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await api("company", { method: "PUT", body: { ...form, blue_return_effective_from: form.blue_return_effective_from || null } });
      setSaved(true);
      onSaved();
    } catch (err) {
      setError(err);
    }
  }

  return (
    <Card title="会社設定（DM-01）">
      <form className="form" onSubmit={save}>
        <Field label="商号"><input value={form.trade_name} onChange={set("trade_name")} required /></Field>
        <Field label="法人番号（13桁）"><input value={form.corporate_number} onChange={set("corporate_number")} pattern="\d{13}" required /></Field>
        <Field label="代表社員名"><input value={form.representative_name} onChange={set("representative_name")} required /></Field>
        <Field label="本店所在地" wide><input value={form.head_office_address} onChange={set("head_office_address")} required /></Field>
        <Field label="設立日"><input type="date" value={form.incorporation_date} onChange={set("incorporation_date")} required /></Field>
        <Field label="資本金の額（円）"><input type="number" className="num" value={form.capital_amount} onChange={set("capital_amount")} min={0} required /></Field>
        <Field label="期首月">
          <select value={form.fiscal_year_start_month} onChange={(e) => setForm({ ...form, fiscal_year_start_month: Number(e.target.value) })}>
            {Array.from({ length: 12 }, (_, i) => i + 1).map((m) => <option key={m} value={m}>{m}月</option>)}
          </select>
        </Field>
        <Field label="経理方式">
          <select value={form.accounting_tax_method} onChange={set("accounting_tax_method")}>
            <option value="tax_included">税込経理</option>
            <option value="tax_excluded">税抜経理</option>
          </select>
        </Field>
        <Field label="青色申告の承認">
          <span className="check"><input type="checkbox" checked={form.blue_return_approved} onChange={set("blue_return_approved")} /> 承認あり</span>
        </Field>
        <Field label="承認が有効になる事業年度の開始日"><input type="date" value={form.blue_return_effective_from} onChange={set("blue_return_effective_from")} /></Field>
        <Field label="所轄の税務署"><input value={form.tax_office} onChange={set("tax_office")} required /></Field>
        <Field label="都道府県"><input value={form.prefecture} onChange={set("prefecture")} required /></Field>
        <Field label="市区町村"><input value={form.municipality} onChange={set("municipality")} required /></Field>
        <div className="actions field wide"><button className="primary">保存</button>{saved ? <span className="muted">保存しました</span> : null}</div>
      </form>
      {data?.company ? <p className="muted small">中小法人の判定（BR-010）: {data.is_sme ? "中小法人" : "中小法人ではない"}</p> : null}
      <ErrorBox error={error} />
    </Card>
  );
}

function PeriodForm({ onSaved }: { onSaved: () => void }) {
  const periods = useApi<{ items: any[] }>("fiscal-periods");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [error, setError] = useState<unknown>(null);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await api("fiscal-periods", { body: { start_date: start, end_date: end } });
      setStart("");
      setEnd("");
      periods.reload();
      onSaved();
    } catch (err) {
      setError(err);
    }
  }

  return (
    <Card title="会計期間（DM-03）">
      <ul>
        {periods.data?.items.map((p) => (
          <li key={p.id}>
            {p.start_date} 〜 {p.end_date} <span className="badge">{p.status === "open" ? "入力中" : p.status === "closing" ? "締め処理中" : "締め済み"}</span>
          </li>
        ))}
      </ul>
      <form className="form" onSubmit={create}>
        <Field label="期首日"><input type="date" value={start} onChange={(e) => setStart(e.target.value)} required /></Field>
        <Field label="期末日"><input type="date" value={end} onChange={(e) => setEnd(e.target.value)} required /></Field>
        <button className="primary">会計期間を追加</button>
      </form>
      <ErrorBox error={error} />
    </Card>
  );
}

function ConsumptionTaxForm({ onSaved }: { onSaved: () => void }) {
  const periods = useApi<{ items: any[] }>("fiscal-periods");
  const [periodId, setPeriodId] = useState("");
  const current = useApi<any>(periodId ? `fiscal-periods/${periodId}/consumption-tax` : null);
  const [form, setForm] = useState<any>({ taxable_status: "exempt", invoice_registration_number: "", calculation_method: "standard", simplified_business_category: "5", interim_filing_required: false });
  const [error, setError] = useState<unknown>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (!periodId && periods.data?.items.length) setPeriodId(periods.data.items[periods.data.items.length - 1].id);
  }, [periods.data, periodId]);

  useEffect(() => {
    const s = current.data?.setting;
    if (s) setForm({ ...s, invoice_registration_number: s.invoice_registration_number ?? "", simplified_business_category: s.simplified_business_category ?? "5", interim_filing_required: !!s.interim_filing_required });
  }, [current.data]);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSaved(false);
    try {
      await api(`fiscal-periods/${periodId}/consumption-tax`, {
        method: "PUT",
        body: { ...form, simplified_business_category: form.calculation_method === "simplified" ? form.simplified_business_category : null },
      });
      setSaved(true);
      current.reload();
      onSaved();
    } catch (err) {
      setError(err);
    }
  }

  const allowed: string[] = current.data?.allowed_calculation_methods ?? ["standard", "simplified"];
  const hint = current.data?.status_hint;

  return (
    <Card title="消費税設定（DM-02）">
      {!periods.data?.items.length ? <p className="muted">先に会計期間を追加してください。</p> : (
        <form className="form" onSubmit={save}>
          <Field label="対象の事業年度">
            <select value={periodId} onChange={(e) => setPeriodId(e.target.value)}>
              {periods.data.items.map((p) => <option key={p.id} value={p.id}>{p.start_date}〜{p.end_date}</option>)}
            </select>
          </Field>
          <Field label="課税区分">
            <select value={form.taxable_status} onChange={(e) => setForm({ ...form, taxable_status: e.target.value })}>
              <option value="exempt">免税事業者</option>
              <option value="taxable">課税事業者</option>
            </select>
          </Field>
          <Field label="インボイス登録番号" hint="T＋13桁"><input value={form.invoice_registration_number} onChange={(e) => setForm({ ...form, invoice_registration_number: e.target.value })} pattern="T\d{13}" /></Field>
          <Field label="計算方式" hint="2割特例は2026年9月30日を含む課税期間まで（BR-021）">
            <select value={form.calculation_method} onChange={(e) => setForm({ ...form, calculation_method: e.target.value })}>
              {["standard", "simplified", "two_tenths_special"].map((m) => (
                <option key={m} value={m} disabled={!allowed.includes(m)}>{METHOD_LABELS[m]}{allowed.includes(m) ? "" : "（選択不可）"}</option>
              ))}
            </select>
          </Field>
          {form.calculation_method === "simplified" ? (
            <Field label="簡易課税の事業区分" hint="コンサル・IT などの役務提供は通常第5種">
              <select value={form.simplified_business_category} onChange={(e) => setForm({ ...form, simplified_business_category: e.target.value })}>
                {["1", "2", "3", "4", "5", "6"].map((c) => <option key={c} value={c}>第{c}種</option>)}
              </select>
            </Field>
          ) : null}
          <Field label="中間申告">
            <span className="check"><input type="checkbox" checked={form.interim_filing_required} onChange={(e) => setForm({ ...form, interim_filing_required: e.target.checked })} /> 必要</span>
          </Field>
          <div className="actions field wide"><button className="primary">保存</button>{saved ? <span className="muted">保存しました</span> : null}</div>
        </form>
      )}
      {hint ? (
        <p className="muted small">
          判定の補助（BR-020）: {hint.suggested === "taxable" ? "課税事業者" : hint.suggested === "exempt" ? "免税事業者" : "要確認"} — {hint.reasons.join(" ")}
        </p>
      ) : null}
      <ErrorBox error={error} />
    </Card>
  );
}
