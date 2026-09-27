"use client";

import { useState } from "react";
import { Card, ErrorBox, Field, PageTitle, Warnings } from "@/components/ui";
import { api, todayIso, useApi, yen, type Warning } from "@/lib/client";

const METHOD: Record<string, string> = { small: "小規模住宅", large: "小規模住宅以外", luxury: "豪華社宅（時価）" };

export default function HousingPage() {
  const list = useApi<{ items: any[] }>("housings");
  const cps = useApi<{ items: any[] }>("counterparties");
  const pas = useApi<{ items: any[] }>("payment-accounts");
  const empty = {
    landlord_id: "", address: "", contract_start: "", contract_end: "", monthly_rent: "", monthly_common_fee: "", floor_area_sqm: "",
    structure: "non_wooden", building_tax_base: "", land_tax_base: "", is_luxury: false, market_rent: "", collection_amount: "", collection_method: "payroll_deduction",
  };
  const [form, setForm] = useState<any>(empty);
  const [jr, setJr] = useState({ year_month: todayIso().slice(0, 7), payment_account_id: "", pay_day: 27 });
  const [error, setError] = useState<unknown>(null);
  const [warnings, setWarnings] = useState<Warning[]>([]);

  async function add(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const n = (v: any) => (v === "" ? 0 : Number(v));
      const r = await api("housings", {
        body: {
          ...form, monthly_rent: n(form.monthly_rent), monthly_common_fee: n(form.monthly_common_fee), building_tax_base: n(form.building_tax_base),
          land_tax_base: n(form.land_tax_base), collection_amount: n(form.collection_amount), market_rent: form.market_rent === "" ? null : n(form.market_rent),
        },
      });
      setWarnings(r.imputed_rent.warnings);
      setForm(empty);
      list.reload();
    } catch (err) {
      setError(err);
    }
  }

  async function journals(id: string) {
    setError(null);
    try {
      const r = await api(`housings/${id}/journals`, { body: jr });
      setWarnings([{ rule_id: "FR-42", message: `${r.created.length}件の仕訳を作成しました` }, ...r.warnings]);
    } catch (err) {
      setError(err);
    }
  }

  const set = (k: string) => (e: any) => setForm({ ...form, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value });

  return (
    <>
      <PageTitle title="借上げ社宅">賃料相当額の計算（FR-40 / BR-081）、徴収額の不足の警告（FR-41）、家賃と徴収の仕訳（FR-42）</PageTitle>
      <ErrorBox error={error} />
      <Warnings items={warnings} />
      {list.data?.items.map((h) => (
        <Card key={h.id} title={h.address}>
          <div className="stats">
            <div className="stat"><div className="label">月額家賃＋共益費</div><div className="value">{yen(h.monthly_rent + h.monthly_common_fee)}</div></div>
            <div className="stat"><div className="label">賃料相当額（{METHOD[h.imputed_rent.method]}）</div><div className="value">{yen(h.imputed_rent.amount)}</div></div>
            <div className="stat"><div className="label">役員からの徴収額</div><div className="value">{yen(h.collection_amount)}</div></div>
            <div className="stat"><div className="label">不足額（役員報酬として課税）</div><div className="value">{yen(h.imputed_rent.shortfall)}</div></div>
          </div>
          <Warnings items={h.imputed_rent.warnings} />
          <p className="muted small">貸主: {h.landlord_name} ／ 契約 {h.contract_start}〜{h.contract_end} ／ {h.floor_area_sqm}㎡ {h.structure === "wooden" ? "木造" : "非木造"} ／ 徴収方法: {h.collection_method === "payroll_deduction" ? "給与から天引き（給与の登録で処理）" : "振込"}</p>
          <div className="form">
            <Field label="対象月"><input type="month" value={jr.year_month} onChange={(e) => setJr({ ...jr, year_month: e.target.value })} /></Field>
            <Field label="支払日"><input type="number" min={1} max={31} className="num" value={jr.pay_day} onChange={(e) => setJr({ ...jr, pay_day: Number(e.target.value) })} /></Field>
            <Field label="支払口座">
              <select value={jr.payment_account_id} onChange={(e) => setJr({ ...jr, payment_account_id: e.target.value })}>
                <option value="">選択</option>
                {pas.data?.items.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
              </select>
            </Field>
            <button className="primary" disabled={!jr.payment_account_id} onClick={() => journals(h.id)}>家賃の仕訳を作成（非課税）</button>
          </div>
        </Card>
      ))}
      <Card title="社宅の登録（DM-15）">
        <form className="form" onSubmit={add}>
          <Field label="貸主（取引先）">
            <select value={form.landlord_id} onChange={set("landlord_id")} required>
              <option value="">選択</option>
              {cps.data?.items.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </Field>
          <Field label="物件の所在地" wide><input value={form.address} onChange={set("address")} required /></Field>
          <Field label="契約開始"><input type="date" value={form.contract_start} onChange={set("contract_start")} required /></Field>
          <Field label="契約終了"><input type="date" value={form.contract_end} onChange={set("contract_end")} required /></Field>
          <Field label="月額家賃"><input type="number" className="num" value={form.monthly_rent} onChange={set("monthly_rent")} required /></Field>
          <Field label="共益費・管理費"><input type="number" className="num" value={form.monthly_common_fee} onChange={set("monthly_common_fee")} /></Field>
          <Field label="床面積（㎡）"><input type="number" step="0.01" className="num" value={form.floor_area_sqm} onChange={set("floor_area_sqm")} required /></Field>
          <Field label="構造">
            <select value={form.structure} onChange={set("structure")}><option value="non_wooden">非木造</option><option value="wooden">木造</option></select>
          </Field>
          <Field label="建物の固定資産税の課税標準額"><input type="number" className="num" value={form.building_tax_base} onChange={set("building_tax_base")} required /></Field>
          <Field label="土地の固定資産税の課税標準額"><input type="number" className="num" value={form.land_tax_base} onChange={set("land_tax_base")} required /></Field>
          <Field label="豪華社宅"><span className="check"><input type="checkbox" checked={form.is_luxury} onChange={set("is_luxury")} /> 該当（床面積240㎡超など）</span></Field>
          {form.is_luxury ? <Field label="時価（月額）"><input type="number" className="num" value={form.market_rent} onChange={set("market_rent")} /></Field> : null}
          <Field label="役員から受け取る月額"><input type="number" className="num" value={form.collection_amount} onChange={set("collection_amount")} required /></Field>
          <Field label="徴収方法">
            <select value={form.collection_method} onChange={set("collection_method")}><option value="payroll_deduction">給与から天引き</option><option value="transfer">振込</option></select>
          </Field>
          <button className="primary">登録</button>
        </form>
      </Card>
    </>
  );
}
