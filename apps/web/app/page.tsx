"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { BalanceBars, Donut, SERIES } from "@/components/charts";
import { Card, DataTable, ErrorBox, Notice, PageTitle } from "@/components/ui";
import { api, useApi, yen } from "@/lib/client";

export default function Home() {
  const status = useApi<any>("setup/status");
  const ready = status.data?.completed;
  const [autoPosted, setAutoPosted] = useState<any[] | null>(null);
  const [loadKey, setLoadKey] = useState(0);

  // 家賃の引落しなど、計上日が来た定型仕訳を先に自動計上してから集計を表示する
  useEffect(() => {
    if (!ready) return;
    api("recurring-templates/auto-run", { body: {} })
      .then((r) => setAutoPosted(r.created))
      .catch(() => setAutoPosted([]))
      .finally(() => setLoadKey((k) => k + 1));
  }, [ready]);

  const dash = useApi<any>(ready && loadKey > 0 ? "dashboard" : null, { k: loadKey });
  const deadlines = useApi<{ items: any[] }>("deadlines");
  const invoices = useApi<{ items: any[] }>(ready ? "sales-invoices" : null);

  if (status.error) {
    return (
      <>
        <PageTitle title="ホーム" />
        <ErrorBox error={status.error} />
        <Notice>API が起動しているか確認してください（ローカルでは <code>apps/api</code> で uvicorn を起動します）。</Notice>
      </>
    );
  }

  const d = dash.data;
  const unpaid = (invoices.data?.items ?? []).filter((i) => i.status !== "paid");
  const unpaidTotal = unpaid.reduce((a, b) => a + b.remaining_amount, 0);
  const soon = (deadlines.data?.items ?? []).filter((x) => x.within_14_days);
  const slices = d
    ? d.breakdown.items.map((it: any, i: number) => ({ name: it.name, amount: Math.max(it.amount, 0), color: SERIES[i] }))
    : [];
  const shortfall = d ? d.breakdown.items.find((it: any) => it.key === "remaining").amount : 0;

  return (
    <>
      <PageTitle title="ホーム">{d ? `会計期間 ${d.period.start_date}〜${d.period.end_date}（${d.as_of} 時点）` : null}</PageTitle>

      {status.data && !ready ? (
        <Notice>
          初期設定が完了していません。<Link href="/setup">初期設定</Link>で会社情報・会計期間・消費税の設定を入力してください。
          使い方は<Link href="/help">ヘルプ</Link>にまとめています。
        </Notice>
      ) : null}
      {autoPosted && autoPosted.length > 0 ? (
        <Notice>
          家賃などの定期的な引落しを自動で記帳しました（
          {Object.entries(autoPosted.reduce((acc: Record<string, number>, a) => ({ ...acc, [a.name]: (acc[a.name] ?? 0) + 1 }), {}))
            .map(([name, n]) => `${name} ${n}か月分`)
            .join("、")}
          ）。
        </Notice>
      ) : null}
      <ErrorBox error={dash.error} />

      {d ? (
        <>
          <div className="stats" style={{ marginBottom: 12 }}>
            <div className="stat">
              <div className="label">使えるお金（支払予定・税金の見込みを除いた額）</div>
              <div className="value hero" style={{ color: d.available < 0 ? "var(--danger)" : undefined }}>{yen(d.available)}円</div>
            </div>
            <div className="stat"><div className="label">口座・現金の残高</div><div className="value">{yen(d.cash_total)}円</div></div>
            <div className="stat"><div className="label">支払予定（カード・預り金など）</div><div className="value">{yen(d.payables_total)}円</div></div>
            <div className="stat"><div className="label">税金の見込み</div><div className="value">{yen(d.reserves_total)}円</div></div>
            <div className="stat"><div className="label">未入金の売上（請求中）</div><div className="value">{yen(unpaidTotal)}円</div></div>
          </div>

          <div className="grid">
            <Card title="会社のお金">
              <table className="funds">
                <tbody>
                  {d.cash.map((c: any) => (
                    <tr key={c.code}>
                      <td>{c.name}{c.accounts.length ? <span className="muted small">（{c.accounts.join("、")}）</span> : null}</td>
                      <td className="num">{yen(c.balance)}円</td>
                    </tr>
                  ))}
                  <tr className="sub"><td>口座・現金の合計</td><td className="num">{yen(d.cash_total)}円</td></tr>
                  {d.payables.map((p: any) => (
                    <tr key={p.code}><td>− {p.name}</td><td className="num">−{yen(p.amount)}円</td></tr>
                  ))}
                  {d.reserves.map((r: any) => (
                    <tr key={r.name}><td>− {r.name}</td><td className="num">−{yen(r.amount)}円</td></tr>
                  ))}
                  <tr className="total"><td>使えるお金</td><td className="num">{yen(d.available)}円</td></tr>
                </tbody>
              </table>
              {d.officer_loan ? (
                <p className="small muted">このほか、社長が立て替えた分（役員借入金）が {yen(d.officer_loan)}円 あります。会社から社長に返すお金です。</p>
              ) : null}
              <p className="small muted">口座の残高は、登録した仕訳から計算しています。通帳・ネットバンキングの残高と合わない場合は、記帳漏れがないか確認してください。</p>
            </Card>

            <Card title="今期の売上の使い道">
              {d.breakdown.revenue > 0 ? (
                <Donut slices={slices} centerLabel="今期の売上" centerValue={`${yen(d.breakdown.revenue)}円`} />
              ) : (
                <p className="muted">今期の売上はまだありません。</p>
              )}
              {shortfall < 0 ? (
                <div className="alert alert-warn">経費・役員報酬・税金の合計が売上を {yen(-shortfall)}円 上回っています。</div>
              ) : null}
              <p className="small muted">税金には、決算でまだ計上していない消費税・法人税などの見込み額を含みます。売上は税込経理なら消費税込みの額です。</p>
            </Card>
          </div>

          <Card title="月ごとの入出金と残高（口座・現金）">
            <BalanceBars months={d.months} />
            <div className="table-wrap" style={{ marginTop: 8 }}>
              <table>
                <thead>
                  <tr><th>月</th>{d.months.map((m: any) => <th key={m.month} className="num">{Number(m.month.slice(5))}月</th>)}</tr>
                </thead>
                <tbody>
                  <tr><td>入金</td>{d.months.map((m: any) => <td key={m.month} className="num">{yen(m.inflow)}</td>)}</tr>
                  <tr><td>出金</td>{d.months.map((m: any) => <td key={m.month} className="num">{yen(m.outflow)}</td>)}</tr>
                  <tr><td><strong>月末残高</strong></td>{d.months.map((m: any) => <td key={m.month} className="num"><strong>{yen(m.balance)}</strong></td>)}</tr>
                </tbody>
              </table>
            </div>
          </Card>

          <div className="grid">
            <Card title="これからの自動引落し" actions={<Link href="/recurring">定型仕訳の設定</Link>}>
              <DataTable
                columns={[["date", "予定日"], ["name", "内容"], ["outflow", "出金"], ["inflow", "入金"]]}
                rows={d.upcoming}
                empty="自動で記帳する引落しはありません。家賃などは「借上げ社宅」や「定型仕訳」から設定できます。"
              />
            </Card>
            <Card title="14日以内の期限">
              <DataTable columns={[["date", "期限"], ["title", "内容"]]} rows={soon} empty="14日以内に期限を迎えるものはありません。" />
            </Card>
          </div>
        </>
      ) : null}

      <div className="grid">
        <Card title="未入金の請求書" actions={<Link href="/invoices">請求書へ</Link>}>
          <DataTable
            columns={[["invoice_number", "番号"], ["client_name", "請求先"], ["due_date", "支払期日"], ["remaining_amount", "残高"]]}
            rows={unpaid}
            empty="未入金の請求書はありません。"
          />
        </Card>
        <Card title="今後の期限（60日）">
          <DataTable columns={[["date", "期限"], ["title", "内容"], ["detail", "補足"]]} rows={deadlines.data?.items ?? []} empty="60日以内の期限はありません。" />
        </Card>
      </div>
    </>
  );
}
