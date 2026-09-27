"use client";

import { useEffect, useState } from "react";
import { Card, DataTable, ErrorBox, Field, PageTitle, PeriodSelect, Warnings } from "@/components/ui";
import { api, useApi, yen, type Warning } from "@/lib/client";

const METHODS: Record<string, string> = {
  immediate_small: "取得年度に全額費用化（10万円未満）",
  lump_sum_3y: "一括償却資産（3年均等）",
  small_sme_special: "中小企業者等の少額減価償却資産の特例",
  straight_line: "定額法",
  declining_balance: "定率法",
};

export default function AssetsPage() {
  const list = useApi<{ items: any[] }>("fixed-assets");
  const pas = useApi<{ items: any[] }>("payment-accounts");
  const periods = useApi<{ items: any[] }>("fiscal-periods");
  const [periodId, setPeriodId] = useState("");
  const effectivePeriod = periodId || periods.data?.items.find((p) => p.status !== "closed")?.id || "";
  const plan = useApi<any>(effectivePeriod ? `fiscal-periods/${effectivePeriod}/depreciation` : null);
  const empty = { name: "", asset_category: "器具備品", account_code: "170", acquisition_date: "", service_start_date: "", acquisition_cost: "", useful_life_years: 4, depreciation_method: "", payment_account_id: "" };
  const [form, setForm] = useState<any>(empty);
  const [options, setOptions] = useState<string[]>([]);
  const [error, setError] = useState<unknown>(null);
  const [warnings, setWarnings] = useState<Warning[]>([]);

  // FR-51: 取得価額と取得日から選べる償却方法を提示
  useEffect(() => {
    if (!form.acquisition_cost || !form.acquisition_date) return setOptions([]);
    const t = setTimeout(() => {
      api("fixed-assets/options", { query: { acquisition_cost: form.acquisition_cost, acquisition_date: form.acquisition_date } })
        .then((r) => {
          setOptions(r.options);
          if (!r.options.includes(form.depreciation_method)) setForm((f: any) => ({ ...f, depreciation_method: r.options[0] }));
        })
        .catch(() => setOptions([]));
    }, 300);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [form.acquisition_cost, form.acquisition_date]);

  async function add(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const r = await api("fixed-assets", {
        body: { ...form, acquisition_cost: Number(form.acquisition_cost), useful_life_years: Number(form.useful_life_years), payment_account_id: form.payment_account_id || null, subject_to_depreciable_asset_return: form.account_code !== "180" },
      });
      setWarnings(r.warnings);
      setForm(empty);
      list.reload();
      plan.reload();
    } catch (err) {
      setError(err);
    }
  }

  async function book() {
    setError(null);
    try {
      const r = await api(`fiscal-periods/${effectivePeriod}/depreciation`, { body: {} });
      setWarnings([{ rule_id: "FR-50", message: r.entry_id ? `減価償却費 ${r.items.length}件の仕訳を作成しました` : r.message }]);
      plan.reload();
      list.reload();
    } catch (err) {
      setError(err);
    }
  }

  async function dispose(id: string) {
    const d = prompt("除却・売却日（YYYY-MM-DD）");
    if (!d) return;
    try {
      await api(`fixed-assets/${id}`, { method: "PATCH", body: { disposal_date: d } });
      list.reload();
    } catch (err) {
      setError(err);
    }
  }

  return (
    <>
      <PageTitle title="固定資産">固定資産台帳（FR-50）と償却方法の候補（FR-51）、少額減価償却資産の特例の上限チェック（FR-52）</PageTitle>
      <ErrorBox error={error} />
      <Warnings items={warnings} />
      <Card title="固定資産台帳">
        <div className="table-wrap">
          <table>
            <thead><tr><th>資産名</th><th>種類</th><th>取得日</th><th>事業供用日</th><th className="num">取得価額</th><th>耐用年数</th><th>償却方法</th><th className="num">償却累計</th><th className="num">帳簿価額</th><th>除却日</th><th /></tr></thead>
            <tbody>
              {list.data?.items.map((a) => (
                <tr key={a.id}>
                  <td>{a.name}</td><td>{a.asset_category}</td><td>{a.acquisition_date}</td><td>{a.service_start_date}</td>
                  <td className="num">{yen(a.acquisition_cost)}</td><td>{a.useful_life_years}年</td><td>{METHODS[a.depreciation_method]}</td>
                  <td className="num">{yen(a.accumulated_depreciation)}</td><td className="num">{yen(a.book_value)}</td><td>{a.disposal_date}</td>
                  <td>{!a.disposal_date ? <button onClick={() => dispose(a.id)}>除却</button> : null}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
      <Card title="減価償却費の計上" actions={<PeriodSelect value={periodId} onChange={setPeriodId} />}>
        {plan.data ? (
          <>
            <DataTable
              columns={[["name", "資産名"], ["method_label", "償却方法"], ["book_value_before", "期首帳簿価額"], ["amount", "当期償却額"], ["status", "状態"]]}
              rows={plan.data.items.map((i: any) => ({ ...i, method_label: METHODS[i.method], status: i.already_booked ? "計上済み" : i.amount > 0 ? "未計上" : "" }))}
            />
            <p className="muted">少額減価償却資産の特例: 当期の合計 {yen(plan.data.sme_cap.total)}円 ／ 上限 {yen(plan.data.sme_cap.cap)}円</p>
            <Warnings items={plan.data.sme_cap.warnings} />
            <button className="primary" onClick={book}>期末の減価償却費の仕訳を作成</button>
          </>
        ) : <p className="muted">会計期間がありません。</p>}
      </Card>
      <Card title="資産の登録">
        <form className="form" onSubmit={add}>
          <Field label="資産名"><input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required /></Field>
          <Field label="種類"><input value={form.asset_category} onChange={(e) => setForm({ ...form, asset_category: e.target.value })} required /></Field>
          <Field label="勘定科目">
            <select value={form.account_code} onChange={(e) => setForm({ ...form, account_code: e.target.value })}>
              <option value="170">工具器具備品</option><option value="180">ソフトウェア（償却資産申告の対象外）</option>
            </select>
          </Field>
          <Field label="取得日"><input type="date" value={form.acquisition_date} onChange={(e) => setForm({ ...form, acquisition_date: e.target.value, service_start_date: form.service_start_date || e.target.value })} required /></Field>
          <Field label="事業に使い始めた日" hint="償却の起点"><input type="date" value={form.service_start_date} onChange={(e) => setForm({ ...form, service_start_date: e.target.value })} required /></Field>
          <Field label="取得価額" hint="経理方式に応じて税込または税抜"><input type="number" className="num" value={form.acquisition_cost} onChange={(e) => setForm({ ...form, acquisition_cost: e.target.value })} required /></Field>
          <Field label="法定耐用年数"><input type="number" min={1} className="num" value={form.useful_life_years} onChange={(e) => setForm({ ...form, useful_life_years: e.target.value })} required /></Field>
          <Field label="償却方法（BR-051 の候補）">
            <select value={form.depreciation_method} onChange={(e) => setForm({ ...form, depreciation_method: e.target.value })} required>
              {options.length === 0 ? <option value="">取得価額と取得日を入力</option> : null}
              {options.map((o) => <option key={o} value={o}>{METHODS[o]}</option>)}
            </select>
          </Field>
          <Field label="取得の仕訳も作る場合の支払元">
            <select value={form.payment_account_id} onChange={(e) => setForm({ ...form, payment_account_id: e.target.value })}>
              <option value="">作らない（手入力済み）</option>
              {pas.data?.items.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          </Field>
          <button className="primary">登録</button>
        </form>
      </Card>
    </>
  );
}
