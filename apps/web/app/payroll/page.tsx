"use client";

import { useEffect, useState } from "react";
import { Card, DataTable, ErrorBox, Field, Notice, PageTitle, Warnings } from "@/components/ui";
import { api, todayIso, useApi, yen, type Warning } from "@/lib/client";

const REASONS: Record<string, string> = { regular: "通常改定", performance_deterioration: "業績悪化改定", other: "その他" };

export default function PayrollPage() {
  const officers = useApi<{ items: any[] }>("officers");
  const [officerId, setOfficerId] = useState("");
  useEffect(() => {
    if (!officerId && officers.data?.items.length) setOfficerId(officers.data.items[0].id);
  }, [officers.data, officerId]);
  const officer = officers.data?.items.find((o) => o.id === officerId);

  return (
    <>
      <PageTitle title="役員報酬・給与">改定履歴（FR-30）、月次の支給実績と仕訳の自動作成（FR-31, FR-32）</PageTitle>
      <OfficerForm officer={officer} onSaved={(id) => { officers.reload(); setOfficerId(id); }} />
      {officer ? (
        <>
          <Compensations officerId={officer.id} />
          <PayrollEntry officerId={officer.id} />
          <SocialInsurance />
        </>
      ) : null}
    </>
  );
}

function OfficerForm({ officer, onSaved }: { officer?: any; onSaved: (id: string) => void }) {
  const [form, setForm] = useState<any>({ name: "", address: "", dependents: [] });
  const [error, setError] = useState<unknown>(null);
  useEffect(() => {
    if (officer) setForm({ name: officer.name, address: officer.address, dependents: officer.dependents });
  }, [officer]);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const body = { ...form, dependents: form.dependents.map((d: any) => ({ ...d, birth_date: d.birth_date || null, income: Number(d.income) || 0 })) };
      const r = officer ? await api(`officers/${officer.id}`, { method: "PUT", body }) : await api("officers", { body });
      onSaved(r.id);
    } catch (err) {
      setError(err);
    }
  }

  const setDep = (i: number, p: any) => setForm({ ...form, dependents: form.dependents.map((d: any, j: number) => (j === i ? { ...d, ...p } : d)) });

  return (
    <Card title="役員（代表社員）">
      <Notice>マイナンバーは本システムに保存しません（NFR-05）。源泉徴収票などの提出時に別途記入してください。</Notice>
      <form onSubmit={save}>
        <div className="form">
          <Field label="氏名"><input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required /></Field>
          <Field label="住所" wide><input value={form.address} onChange={(e) => setForm({ ...form, address: e.target.value })} required /></Field>
        </div>
        <h3>扶養親族（源泉徴収税額表の扶養人数・年末調整に使用）</h3>
        {form.dependents.map((d: any, i: number) => (
          <div className="form" key={i} style={{ marginBottom: 8 }}>
            <Field label="氏名"><input value={d.name} onChange={(e) => setDep(i, { name: e.target.value })} /></Field>
            <Field label="続柄">
              <select value={d.relation} onChange={(e) => setDep(i, { relation: e.target.value })}>
                <option value="spouse">配偶者</option><option value="child">子</option><option value="parent">親</option><option value="other">その他</option>
              </select>
            </Field>
            <Field label="生年月日"><input type="date" value={d.birth_date ?? ""} onChange={(e) => setDep(i, { birth_date: e.target.value })} /></Field>
            <Field label="年間の合計所得"><input type="number" className="num" value={d.income} onChange={(e) => setDep(i, { income: e.target.value })} /></Field>
            <button type="button" onClick={() => setForm({ ...form, dependents: form.dependents.filter((_: any, j: number) => j !== i) })}>削除</button>
          </div>
        ))}
        <div className="actions">
          <button type="button" onClick={() => setForm({ ...form, dependents: [...form.dependents, { name: "", relation: "child", birth_date: "", income: 0 }] })}>＋扶養親族</button>
          <button className="primary">{officer ? "更新" : "登録"}</button>
        </div>
      </form>
      <ErrorBox error={error} />
    </Card>
  );
}

function Compensations({ officerId }: { officerId: string }) {
  const list = useApi<{ items: any[]; warnings: Warning[] }>(`officers/${officerId}/compensations`);
  const [form, setForm] = useState({ effective_from: todayIso(), monthly_amount: "", payment_day: 25, resolution_date: todayIso(), revision_reason: "regular" });
  const [error, setError] = useState<unknown>(null);

  async function add(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const r = await api(`officers/${officerId}/compensations`, { body: { ...form, monthly_amount: Number(form.monthly_amount) } });
      list.setData(r);
    } catch (err) {
      setError(err);
    }
  }

  return (
    <Card title="役員報酬の改定履歴（FR-30 / BR-031）">
      <Warnings items={list.data?.warnings} />
      <DataTable
        columns={[["effective_from", "適用開始"], ["monthly_amount", "月額報酬"], ["payment_day", "支給日"], ["resolution_date", "社員総会の決定日"], ["reason", "改定理由"]]}
        rows={(list.data?.items ?? []).map((c) => ({ ...c, reason: REASONS[c.revision_reason] }))}
      />
      <form className="form" onSubmit={add} style={{ marginTop: 12 }}>
        <Field label="適用開始日"><input type="date" value={form.effective_from} onChange={(e) => setForm({ ...form, effective_from: e.target.value })} /></Field>
        <Field label="月額報酬"><input type="number" className="num" value={form.monthly_amount} onChange={(e) => setForm({ ...form, monthly_amount: e.target.value })} required /></Field>
        <Field label="支給日"><input type="number" min={1} max={31} className="num" value={form.payment_day} onChange={(e) => setForm({ ...form, payment_day: Number(e.target.value) })} /></Field>
        <Field label="社員総会の決定日"><input type="date" value={form.resolution_date} onChange={(e) => setForm({ ...form, resolution_date: e.target.value })} /></Field>
        <Field label="改定理由">
          <select value={form.revision_reason} onChange={(e) => setForm({ ...form, revision_reason: e.target.value })}>
            {Object.entries(REASONS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </Field>
        <button className="primary">追加</button>
      </form>
      <ErrorBox error={error} />
    </Card>
  );
}

function PayrollEntry({ officerId }: { officerId: string }) {
  const [year, setYear] = useState(new Date().getFullYear());
  const list = useApi<{ items: any[] }>("payroll", { year });
  const pas = useApi<{ items: any[] }>("payment-accounts");
  const empty = {
    pay_date: todayIso(), gross_amount: "", health_insurance_employee: "", pension_employee: "", health_insurance_employer: "",
    pension_employer: "", standard_monthly_remuneration: "", withholding_income_tax: "", resident_tax: "", company_housing_deduction: "", payment_account_id: "",
  };
  const [form, setForm] = useState<any>(empty);
  const [error, setError] = useState<unknown>(null);
  const [warnings, setWarnings] = useState<Warning[]>([]);
  const n = (k: string) => Number(form[k]) || 0;
  const net = n("gross_amount") - n("health_insurance_employee") - n("pension_employee") - n("withholding_income_tax") - n("resident_tax") - n("company_housing_deduction");

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const body: any = { officer_id: officerId, pay_date: form.pay_date, payment_account_id: form.payment_account_id };
      for (const k of Object.keys(empty)) {
        if (k === "pay_date" || k === "payment_account_id") continue;
        body[k] = form[k] === "" ? (k === "withholding_income_tax" ? null : 0) : Number(form[k]);
      }
      const r = await api("payroll", { body });
      setWarnings(r.warnings);
      list.reload();
    } catch (err) {
      setError(err);
    }
  }

  const num = (k: string, label: string, hint?: string) => (
    <Field label={label} hint={hint}><input type="number" className="num" value={form[k]} onChange={(e) => setForm({ ...form, [k]: e.target.value })} /></Field>
  );

  return (
    <Card title="給与支給実績（FR-31）" actions={<input type="number" className="num" value={year} onChange={(e) => setYear(Number(e.target.value))} style={{ width: 90 }} />}>
      <DataTable
        columns={[["pay_date", "支給日"], ["gross_amount", "総支給額"], ["health_insurance_employee", "健康保険"], ["pension_employee", "厚生年金"], ["withholding_income_tax", "源泉所得税"], ["resident_tax", "住民税"], ["company_housing_deduction", "社宅天引き"], ["net_amount", "差引支給額"]]}
        rows={list.data?.items ?? []}
      />
      <h3>支給の登録（役員報酬・法定福利費・預り金の仕訳を自動作成）</h3>
      <form onSubmit={save}>
        <div className="form">
          <Field label="支給日"><input type="date" value={form.pay_date} onChange={(e) => setForm({ ...form, pay_date: e.target.value })} required /></Field>
          {num("gross_amount", "総支給額")}
          {num("standard_monthly_remuneration", "標準報酬月額")}
          {num("health_insurance_employee", "健康保険料（本人）")}
          {num("pension_employee", "厚生年金保険料（本人）")}
          {num("health_insurance_employer", "健康保険料（会社）")}
          {num("pension_employer", "厚生年金保険料（会社）")}
          {num("withholding_income_tax", "源泉所得税", "空欄なら税額表から自動計算（FR-32）")}
          {num("resident_tax", "住民税（特別徴収）")}
          {num("company_housing_deduction", "社宅家賃の天引き")}
          <Field label="支払口座">
            <select value={form.payment_account_id} onChange={(e) => setForm({ ...form, payment_account_id: e.target.value })} required>
              <option value="">選択</option>
              {pas.data?.items.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          </Field>
        </div>
        <p className="muted">差引支給額（源泉所得税を入力した場合の目安）: {yen(net)}円</p>
        <button className="primary">登録</button>
      </form>
      <ErrorBox error={error} />
      <Warnings items={warnings} />
    </Card>
  );
}

function SocialInsurance() {
  const pas = useApi<{ items: any[] }>("payment-accounts");
  const [form, setForm] = useState({ paid_date: todayIso(), employee_amount: "", employer_amount: "", payment_account_id: "" });
  const [error, setError] = useState<unknown>(null);
  const [done, setDone] = useState(false);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await api("payroll/social-insurance-payments", { body: { ...form, employee_amount: Number(form.employee_amount) || 0, employer_amount: Number(form.employer_amount) || 0 } });
      setDone(true);
    } catch (err) {
      setError(err);
    }
  }

  return (
    <Card title="社会保険料の納付（口座振替）">
      <form className="form" onSubmit={save}>
        <Field label="納付日"><input type="date" value={form.paid_date} onChange={(e) => setForm({ ...form, paid_date: e.target.value })} /></Field>
        <Field label="本人負担分（預り金）"><input type="number" className="num" value={form.employee_amount} onChange={(e) => setForm({ ...form, employee_amount: e.target.value })} /></Field>
        <Field label="会社負担分（未払費用）"><input type="number" className="num" value={form.employer_amount} onChange={(e) => setForm({ ...form, employer_amount: e.target.value })} /></Field>
        <Field label="支払口座">
          <select value={form.payment_account_id} onChange={(e) => setForm({ ...form, payment_account_id: e.target.value })} required>
            <option value="">選択</option>
            {pas.data?.items.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </Field>
        <button className="primary">仕訳を作成</button>
      </form>
      {done ? <p className="muted">仕訳を作成しました。</p> : null}
      <ErrorBox error={error} />
    </Card>
  );
}
