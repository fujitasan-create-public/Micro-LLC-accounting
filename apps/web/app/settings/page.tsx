"use client";

import { Fragment, useState } from "react";
import { Card, ErrorBox, Field, Notice, PageTitle } from "@/components/ui";
import { api, todayIso, useApi } from "@/lib/client";
import { GROUP_ORDER, RULES, display, fromInput, inputUnit, toInput, type RuleDef, type Shape } from "@/lib/rule-catalog";

type Row = { key: string; value: unknown; effective_from: string; effective_to: string | null; note: string | null };

function parse(v: string): unknown {
  try {
    return JSON.parse(v);
  } catch {
    return v;
  }
}

function status(r: Row, rows: Row[], today: string): "current" | "future" | "past" {
  if (r.effective_from > today) return "future";
  if (r.effective_to && r.effective_to < today) return "past";
  const active = rows.filter((x) => x.effective_from <= today && (!x.effective_to || x.effective_to >= today));
  const latest = active.sort((a, b) => b.effective_from.localeCompare(a.effective_from))[0];
  return latest === r ? "current" : "past";
}

function ValueView({ shape, value }: { shape: Shape; value: any }) {
  if (shape.type === "scalar") return <>{display(shape.kind, value, shape.unit)}</>;
  if (shape.type === "object")
    return (
      <>
        {shape.fields.map((f) => (
          <div key={f.key}>{f.label}: {display(f.kind, value?.[f.key], f.unit)}</div>
        ))}
      </>
    );
  if (shape.type === "map")
    return <>{shape.entries.map((e) => `${e.label} ${display(shape.kind, value?.[e.key])}`).join("、")}</>;
  return (
    <table style={{ width: "auto" }}>
      <thead><tr>{shape.columns.map((c) => <th key={c.key}>{c.label}</th>)}</tr></thead>
      <tbody>
        {(value as any[] | undefined)?.map((row, i) => (
          <tr key={i}>
            {shape.columns.map((c) => (
              <td key={c.key} className="num">{c.key === "upto" && row[c.key] == null ? "上限なし" : display(c.kind, row[c.key])}</td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/** 画面の入力欄の状態（すべて文字列）と保存形式の相互変換 */
function toDraft(shape: Shape, value: any): any {
  if (shape.type === "scalar") return toInput(shape.kind, value);
  if (shape.type === "object") return Object.fromEntries(shape.fields.map((f) => [f.key, toInput(f.kind, value?.[f.key])]));
  if (shape.type === "map") return Object.fromEntries(shape.entries.map((e) => [e.key, toInput(shape.kind, value?.[e.key])]));
  return ((value as any[]) ?? []).map((row) => Object.fromEntries(shape.columns.map((c) => [c.key, toInput(c.kind, row[c.key])])));
}

function fromDraft(shape: Shape, draft: any): unknown {
  if (shape.type === "scalar") return fromInput(shape.kind, draft);
  if (shape.type === "object") return Object.fromEntries(shape.fields.map((f) => [f.key, fromInput(f.kind, draft[f.key])]));
  if (shape.type === "map") return Object.fromEntries(shape.entries.map((e) => [e.key, fromInput(shape.kind, draft[e.key])]));
  return (draft as any[]).map((row) => {
    const out: any = {};
    for (const c of shape.columns) {
      const v = fromInput(c.kind, row[c.key]);
      if (v !== null || c.key === "upto") out[c.key] = v;
    }
    return out;
  });
}

function Editor({ def, current, onDone }: { def: RuleDef; current: unknown; onDone: () => void }) {
  const [draft, setDraft] = useState<any>(() => toDraft(def.shape, current));
  const [from, setFrom] = useState(todayIso());
  const [to, setTo] = useState("");
  const [note, setNote] = useState("");
  const [error, setError] = useState<unknown>(null);
  const shape = def.shape;

  const input = (kind: any, value: string, onChange: (v: string) => void, unit?: string) => (
    <span className="check">
      <input className={kind === "date" ? undefined : "num"} type={kind === "date" ? "date" : "text"} inputMode="decimal"
        value={value} onChange={(e) => onChange(e.target.value)} style={{ width: kind === "date" ? undefined : 130 }} />
      {inputUnit(kind, unit)}
    </span>
  );

  async function save() {
    setError(null);
    try {
      await api("rule-settings", {
        body: { key: def.key, value: fromDraft(shape, draft), effective_from: from, effective_to: to || null, note: note || null },
      });
      onDone();
    } catch (err) {
      setError(err);
    }
  }

  return (
    <div className="alert alert-info">
      <div className="form">
        {shape.type === "scalar" ? <Field label="新しい値">{input(shape.kind, draft, setDraft, shape.unit)}</Field> : null}
        {shape.type === "object"
          ? shape.fields.map((f) => <Field key={f.key} label={f.label}>{input(f.kind, draft[f.key], (v) => setDraft({ ...draft, [f.key]: v }), f.unit)}</Field>)
          : null}
        {shape.type === "map"
          ? shape.entries.map((e) => <Field key={e.key} label={e.label}>{input(shape.kind, draft[e.key], (v) => setDraft({ ...draft, [e.key]: v }))}</Field>)
          : null}
      </div>
      {shape.type === "rows" ? (
        <table style={{ width: "auto", margin: "6px 0" }}>
          <thead><tr>{shape.columns.map((c) => <th key={c.key}>{c.label}</th>)}<th /></tr></thead>
          <tbody>
            {(draft as any[]).map((row, i) => (
              <tr key={i}>
                {shape.columns.map((c) => (
                  <td key={c.key}>{input(c.kind, row[c.key], (v) => setDraft(draft.map((r: any, j: number) => (j === i ? { ...r, [c.key]: v } : r))))}</td>
                ))}
                <td><button type="button" onClick={() => setDraft(draft.filter((_: any, j: number) => j !== i))}>削除</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : null}
      {shape.type === "rows" ? (
        <p className="small muted" style={{ margin: 0 }}>
          上から小さい順に並べてください。最後の段の上限は空欄（上限なし）にします。
          <button type="button" style={{ marginLeft: 8 }} onClick={() => setDraft([...draft, Object.fromEntries(shape.columns.map((c) => [c.key, ""]))])}>＋段を追加</button>
        </p>
      ) : null}
      <div className="form" style={{ marginTop: 8 }}>
        <Field label="適用開始日"><input type="date" value={from} onChange={(e) => setFrom(e.target.value)} /></Field>
        <Field label="適用終了日（空欄なら期限なし）"><input type="date" value={to} onChange={(e) => setTo(e.target.value)} /></Field>
        <Field label="メモ"><input value={note} onChange={(e) => setNote(e.target.value)} placeholder="例: 令和9年度改正" /></Field>
        <div className="actions">
          <button className="primary" onClick={save}>保存</button>
          <button type="button" onClick={onDone}>キャンセル</button>
        </div>
      </div>
      <p className="small muted" style={{ margin: "6px 0 0" }}>同じ適用開始日の値がある場合は上書きします。適用開始日を変えると、以前の値は履歴として残り、その日以降は新しい値が使われます。</p>
      <ErrorBox error={error} />
    </div>
  );
}

const STATUS_LABEL = { current: "適用中", future: "予定", past: "終了" } as const;

export default function SettingsPage() {
  const list = useApi<{ items: any[] }>("rule-settings");
  const [editing, setEditing] = useState<string | null>(null);
  const [showPast, setShowPast] = useState(false);
  const today = todayIso();

  const rows: Row[] = (list.data?.items ?? []).map((r) => ({ ...r, value: parse(r.value) }));
  const byKey = new Map<string, Row[]>();
  for (const r of rows) byKey.set(r.key, [...(byKey.get(r.key) ?? []), r]);

  return (
    <>
      <PageTitle title="税率・基準額">計算に使う税率や金額の基準です。法改正があったときに、新しい値を適用開始日つきで追加します。</PageTitle>
      <Notice>
        初期値は2026年9月時点の制度に合わせています。通常は変更不要ですが、<strong>法人事業税</strong>と<strong>法人住民税（法人税割）</strong>の税率は自治体によって異なるため、本店所在地の税率になっているか確認してください。
      </Notice>
      <div className="actions" style={{ marginBottom: 10 }}>
        <label className="check"><input type="checkbox" checked={showPast} onChange={(e) => setShowPast(e.target.checked)} /> 適用が終わった値も表示</label>
      </div>
      <ErrorBox error={list.error} />
      {GROUP_ORDER.map((group) => (
        <Card key={group} title={group}>
          <div className="table-wrap">
            <table>
              <thead>
                <tr><th style={{ width: "24%" }}>項目</th><th style={{ width: "13%" }}>適用期間</th><th>値</th><th style={{ width: 70 }}>状態</th><th style={{ width: 90 }} /></tr>
              </thead>
              <tbody>
                {RULES.filter((d) => d.group === group).map((def) => {
                  const all = (byKey.get(def.key) ?? []).sort((a, b) => a.effective_from.localeCompare(b.effective_from));
                  const visible = all.filter((r) => showPast || status(r, all, today) !== "past");
                  const current = all.find((r) => status(r, all, today) === "current") ?? all[all.length - 1];
                  const shown = visible.length ? visible : current ? [current] : [];
                  return (
                    <Fragment key={def.key}>
                      {shown.map((r, i) => {
                        const st = status(r, all, today);
                        return (
                          <tr key={r.effective_from}>
                            {i === 0 ? (
                              <td rowSpan={shown.length + (editing === def.key ? 1 : 0)}>
                                <strong>{def.label}</strong>
                                {def.description ? <div className="small muted">{def.description}</div> : null}
                              </td>
                            ) : null}
                            <td className="small">{display("date", r.effective_from)}〜{r.effective_to ? display("date", r.effective_to) : ""}</td>
                            <td><ValueView shape={def.shape} value={r.value} /></td>
                            <td><span className={`badge${st === "current" ? " ok" : ""}`}>{STATUS_LABEL[st]}</span></td>
                            {i === 0 ? (
                              <td rowSpan={shown.length}>
                                <button onClick={() => setEditing(editing === def.key ? null : def.key)}>変更する</button>
                              </td>
                            ) : null}
                          </tr>
                        );
                      })}
                      {editing === def.key ? (
                        <tr>
                          <td colSpan={4}>
                            <Editor def={def} current={current?.value} onDone={() => { setEditing(null); list.reload(); }} />
                          </td>
                        </tr>
                      ) : null}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        </Card>
      ))}
    </>
  );
}
