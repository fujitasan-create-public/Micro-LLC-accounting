"use client";

import { useState } from "react";
import { Card, DataTable, ErrorBox, Field, PageTitle, PeriodSelect } from "@/components/ui";
import { buildUrl, useApi } from "@/lib/client";

export default function ReportsPage() {
  const reports = useApi<{ items: any[] }>("reports");
  const accounts = useApi<{ items: any[] }>("accounts");
  const [reportId, setReportId] = useState("trial-balance");
  const [periodId, setPeriodId] = useState("");
  const [params, setParams] = useState<Record<string, string>>({ year: String(new Date().getFullYear()), month: "", account: "" });
  const spec = reports.data?.items.find((r) => r.id === reportId);
  const query: Record<string, string> = { period_id: periodId };
  for (const p of spec?.params ?? []) if (params[p]) query[p] = params[p];
  const rep = useApi<any>(reportId ? `reports/${reportId}` : null, query);

  return (
    <>
      <PageTitle title="帳票">帳簿・決算書・申告用の集計資料。印刷またはCSVで出力できます。</PageTitle>
      <Card>
        <div className="form no-print">
          <Field label="帳票">
            <select value={reportId} onChange={(e) => setReportId(e.target.value)}>
              {reports.data?.items.map((r) => <option key={r.id} value={r.id}>{r.title}</option>)}
            </select>
          </Field>
          <Field label="会計期間"><PeriodSelect value={periodId} onChange={setPeriodId} /></Field>
          {spec?.params.includes("month") ? (
            <Field label="月（空欄なら年次）"><input type="month" value={params.month} onChange={(e) => setParams({ ...params, month: e.target.value })} /></Field>
          ) : null}
          {spec?.params.includes("year") ? (
            <Field label="年"><input type="number" className="num" value={params.year} onChange={(e) => setParams({ ...params, year: e.target.value })} /></Field>
          ) : null}
          {spec?.params.includes("account") ? (
            <Field label="勘定科目（空欄ならすべて）">
              <select value={params.account} onChange={(e) => setParams({ ...params, account: e.target.value })}>
                <option value="">すべて</option>
                {accounts.data?.items.map((a) => <option key={a.code} value={a.code}>{a.code} {a.name}</option>)}
              </select>
            </Field>
          ) : null}
          <div className="actions">
            <a className="button" href={buildUrl(`reports/${reportId}`, { ...query, format: "csv" })}>CSVを出力</a>
            <button onClick={() => window.print()}>印刷・PDF</button>
          </div>
        </div>
      </Card>
      <ErrorBox error={rep.error} />
      {rep.data ? (
        <Card>
          <div style={{ marginBottom: 12 }}>
            <h2>{rep.data.title}</h2>
            <div className="muted">{rep.data.company_name} ／ {rep.data.period_label}</div>
          </div>
          {rep.data.sections.map((s: any, i: number) => (
            <div key={i} style={{ marginBottom: 20 }}>
              <h3>{s.title}</h3>
              <DataTable columns={s.columns} rows={s.rows} />
            </div>
          ))}
          {rep.data.notes?.length ? <ul className="muted small">{rep.data.notes.map((n: string, i: number) => <li key={i}>{n}</li>)}</ul> : null}
        </Card>
      ) : rep.loading ? <p className="muted">集計中…</p> : null}
    </>
  );
}
