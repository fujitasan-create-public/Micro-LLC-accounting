"use client";

import type { ReactNode } from "react";
import { ApiError, useApi, yen, type Warning } from "@/lib/client";

export function PageTitle({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="page-title">
      <h1>{title}</h1>
      {children ? <p className="muted">{children}</p> : null}
    </div>
  );
}

export function Card({ title, children, actions }: { title?: string; children: ReactNode; actions?: ReactNode }) {
  return (
    <section className="card">
      {title || actions ? (
        <div className="card-head">
          {title ? <h2>{title}</h2> : <span />}
          {actions}
        </div>
      ) : null}
      <div className="card-body">{children}</div>
    </section>
  );
}

export function ErrorBox({ error }: { error: unknown }) {
  if (!error) return null;
  const e = error as ApiError;
  return (
    <div className="alert alert-error" role="alert">
      {e.message ?? String(error)}
    </div>
  );
}

export function Warnings({ items }: { items?: Warning[] | null }) {
  if (!items || items.length === 0) return null;
  return (
    <div className="alert alert-warn" role="status">
      <ul>
        {items.map((w, i) => (
          <li key={i}>
            {w.message}
          </li>
        ))}
      </ul>
    </div>
  );
}

export function Notice({ children }: { children: ReactNode }) {
  return <div className="alert alert-info">{children}</div>;
}

export function Field({ label, children, hint, wide }: { label: string; children: ReactNode; hint?: string; wide?: boolean }) {
  return (
    <label className={`field${wide ? " wide" : ""}`}>
      <span className="field-label">{label}</span>
      {children}
      {hint ? <span className="hint">{hint}</span> : null}
    </label>
  );
}

export type Column = [string, string];

export function DataTable({ columns, rows, empty = "データがありません" }: { columns: Column[]; rows: any[]; empty?: string }) {
  if (!rows || rows.length === 0) return <p className="muted">{empty}</p>;
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            {columns.map(([k, label]) => (
              <th key={k}>{label}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i}>
              {columns.map(([k]) => {
                const v = r[k];
                const num = typeof v === "number";
                return (
                  <td key={k} className={num ? "num" : undefined}>
                    {num ? yen(v) : v === true ? "✓" : v === false ? "" : String(v ?? "")}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function PeriodSelect({ value, onChange }: { value: string; onChange: (id: string) => void }) {
  const { data } = useApi<{ items: any[] }>("fiscal-periods");
  return (
    <select value={value} onChange={(e) => onChange(e.target.value)}>
      <option value="">（当期）</option>
      {data?.items.map((p) => (
        <option key={p.id} value={p.id}>
          {p.start_date}〜{p.end_date}
          {p.status === "closed" ? "（締め済み）" : ""}
        </option>
      ))}
    </select>
  );
}

export function AccountSelect({
  accounts,
  value,
  onChange,
  filter,
}: {
  accounts: any[];
  value: string;
  onChange: (code: string) => void;
  filter?: (a: any) => boolean;
}) {
  return (
    <select value={value} onChange={(e) => onChange(e.target.value)}>
      <option value="">科目を選択</option>
      {accounts
        .filter((a) => a.is_active && (!filter || filter(a)))
        .map((a) => (
          <option key={a.code} value={a.code}>
            {a.code} {a.name}
          </option>
        ))}
    </select>
  );
}

export function Money({ value }: { value: number | null | undefined }) {
  return <span className="num">{yen(value ?? 0)}</span>;
}

export const CATEGORY_LABELS: Record<string, string> = {
  asset: "資産",
  liability: "負債",
  equity: "純資産",
  revenue: "収益",
  expense: "費用",
};
