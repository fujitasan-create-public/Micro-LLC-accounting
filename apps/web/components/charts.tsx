"use client";

import { useState } from "react";
import { yen } from "@/lib/client";

/** 検証済みの配色（青・橙・緑・黄）。円グラフの隣り合う色が見分けられる順に並べている */
export const SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"];

type Slice = { name: string; amount: number; color: string };

/** ドーナツ型の円グラフ。凡例（金額・割合つき）を必ず並べて表示する */
export function Donut({ slices, centerLabel, centerValue }: { slices: Slice[]; centerLabel: string; centerValue: string }) {
  const [hover, setHover] = useState<number | null>(null);
  const positive = slices.filter((s) => s.amount > 0);
  const total = positive.reduce((a, s) => a + s.amount, 0);
  const R = 90;
  const r = 56;
  const cx = 100;
  const cy = 100;
  let angle = -Math.PI / 2;

  const arcs = positive.map((s) => {
    const sweep = total > 0 ? (s.amount / total) * Math.PI * 2 : 0;
    const a0 = angle;
    const a1 = angle + sweep;
    angle = a1;
    const large = sweep > Math.PI ? 1 : 0;
    const p = (rad: number, rr: number) => `${cx + rr * Math.cos(rad)} ${cy + rr * Math.sin(rad)}`;
    // 1つだけで一周する場合は、円弧が描けないので2つに分ける
    const d =
      sweep >= Math.PI * 2 - 1e-6
        ? `M ${p(a0, R)} A ${R} ${R} 0 1 1 ${p(a0 + Math.PI, R)} A ${R} ${R} 0 1 1 ${p(a0, R)} M ${p(a0, r)} A ${r} ${r} 0 1 0 ${p(a0 + Math.PI, r)} A ${r} ${r} 0 1 0 ${p(a0, r)} Z`
        : `M ${p(a0, R)} A ${R} ${R} 0 ${large} 1 ${p(a1, R)} L ${p(a1, r)} A ${r} ${r} 0 ${large} 0 ${p(a0, r)} Z`;
    return { ...s, d };
  });

  return (
    <div className="donut">
      <svg viewBox="0 0 200 200" role="img" aria-label={`${centerLabel} ${centerValue}`} style={{ width: 220, height: 220, flexShrink: 0 }}>
        {total === 0 ? <circle cx={cx} cy={cy} r={(R + r) / 2} fill="none" stroke="#e3e7eb" strokeWidth={R - r} /> : null}
        {arcs.map((a, i) => (
          <path key={a.name} d={a.d} fill={a.color} stroke="#fff" strokeWidth={2} fillRule="evenodd"
            opacity={hover === null || hover === i ? 1 : 0.45}
            onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}>
            <title>{`${a.name} ${yen(a.amount)}円（${Math.round((a.amount / total) * 100)}%）`}</title>
          </path>
        ))}
        <text x={cx} y={cy - 6} textAnchor="middle" fontSize="11" fill="#5f6b76">{hover !== null ? arcs[hover].name.replace(/（.*/, "") : centerLabel}</text>
        <text x={cx} y={cy + 14} textAnchor="middle" fontSize="15" fontWeight="bold" fill="#222">
          {hover !== null ? `${yen(arcs[hover].amount)}円` : centerValue}
        </text>
      </svg>
      <table className="legend">
        <tbody>
          {slices.map((s) => (
            <tr key={s.name}>
              <td><span className="swatch" style={{ background: s.amount > 0 ? s.color : "transparent", borderColor: s.color }} /></td>
              <td>{s.name}</td>
              <td className="num">{yen(s.amount)}円</td>
              <td className="num muted">{total > 0 && s.amount > 0 ? `${Math.round((s.amount / total) * 100)}%` : ""}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

type Month = { month: string; inflow: number; outflow: number; balance: number };

/** 月末残高の棒グラフ（1系列）。棒に重ねると、その月の入金・出金・残高を表示する */
export function BalanceBars({ months }: { months: Month[] }) {
  const [hover, setHover] = useState<number | null>(null);
  const W = 760;
  const H = 220;
  const pad = { l: 64, r: 12, t: 12, b: 26 };
  const values = months.map((m) => m.balance);
  const max = Math.max(0, ...values);
  const min = Math.min(0, ...values);
  // 目盛りのきりのよい上限（例: 583,490 → 600,000）
  const niceCeil = (v: number) => {
    if (v <= 0) return 0;
    const p = 10 ** Math.floor(Math.log10(v));
    return Math.ceil(v / p) * p;
  };
  const top = niceCeil(max) || 100000;
  const bottom = -niceCeil(-min);
  const y = (v: number) => pad.t + ((top - v) / (top - bottom)) * (H - pad.t - pad.b);
  const band = (W - pad.l - pad.r) / Math.max(months.length, 1);
  const bw = Math.min(40, band * 0.6);
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((f) => bottom + (top - bottom) * f);

  return (
    <div style={{ position: "relative" }}>
      <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", height: "auto", maxHeight: 260 }} role="img" aria-label="月末の残高の推移">
        {ticks.map((t) => (
          <g key={t}>
            <line x1={pad.l} x2={W - pad.r} y1={y(t)} y2={y(t)} stroke={t === 0 ? "#8f9aa5" : "#e3e7eb"} strokeWidth={1} />
            <text x={pad.l - 6} y={y(t) + 4} textAnchor="end" fontSize="10" fill="#5f6b76">{`${Math.round(t / 10000).toLocaleString("ja-JP")}万`}</text>
          </g>
        ))}
        {months.map((m, i) => {
          const x = pad.l + band * i + (band - bw) / 2;
          const y0 = y(0);
          const y1 = y(m.balance);
          const h = Math.abs(y1 - y0);
          const up = m.balance >= 0;
          const rr = Math.min(4, h);
          // データ側の端だけ角を丸め、基準線側は角ばらせる
          const d = up
            ? `M ${x} ${y0} V ${y1 + rr} Q ${x} ${y1} ${x + rr} ${y1} H ${x + bw - rr} Q ${x + bw} ${y1} ${x + bw} ${y1 + rr} V ${y0} Z`
            : `M ${x} ${y0} V ${y1 - rr} Q ${x} ${y1} ${x + rr} ${y1} H ${x + bw - rr} Q ${x + bw} ${y1} ${x + bw} ${y1 - rr} V ${y0} Z`;
          return (
            <g key={m.month} onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}>
              <rect x={pad.l + band * i} y={pad.t} width={band} height={H - pad.t - pad.b} fill="transparent" />
              {h > 0 ? <path d={d} fill={up ? SERIES[0] : "#b3261e"} opacity={hover === null || hover === i ? 1 : 0.5} /> : null}
              <text x={pad.l + band * i + band / 2} y={H - 8} textAnchor="middle" fontSize="11" fill="#5f6b76">{Number(m.month.slice(5))}月</text>
            </g>
          );
        })}
      </svg>
      {hover !== null ? (
        <div className="chart-tip" style={{ left: `${((pad.l + band * hover + band / 2) / W) * 100}%` }}>
          <strong>{months[hover].month.replace("-", "年")}月</strong>
          <div>入金 {yen(months[hover].inflow)}円</div>
          <div>出金 {yen(months[hover].outflow)}円</div>
          <div>月末残高 {yen(months[hover].balance)}円</div>
        </div>
      ) : null}
    </div>
  );
}
