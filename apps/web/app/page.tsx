"use client";

import Link from "next/link";
import { Card, DataTable, ErrorBox, Notice, PageTitle } from "@/components/ui";
import { useApi, yen } from "@/lib/client";

export default function Home() {
  const status = useApi<any>("setup/status");
  const deadlines = useApi<{ items: any[] }>("deadlines");
  const ready = status.data?.completed;
  const pl = useApi<any>(ready ? "reports/income-statement" : null);
  const invoices = useApi<{ items: any[] }>(ready ? "sales-invoices" : null);

  if (status.error) {
    return (
      <>
        <PageTitle title="ホーム" />
        <ErrorBox error={status.error} />
        <Notice>
          API が起動しているか確認してください（ローカルでは <code>apps/api</code> で uvicorn を起動します）。
        </Notice>
      </>
    );
  }

  const unpaid = (invoices.data?.items ?? []).filter((i) => i.status !== "paid");
  const soon = (deadlines.data?.items ?? []).filter((d) => d.within_14_days);
  const s = pl.data?.summary;

  return (
    <>
      <PageTitle title="ホーム">{pl.data ? `会計期間 ${pl.data.period_label}` : null}</PageTitle>

      {status.data && !ready ? (
        <Notice>
          初期設定が完了していません。<Link href="/setup">初期設定</Link>
          で会社情報・会計期間・消費税の設定を入力してください。
        </Notice>
      ) : null}

      {s ? (
        <div className="stats" style={{ marginBottom: 16 }}>
          <div className="stat">
            <div className="label">売上高</div>
            <div className="value">{yen(s.sales)}</div>
          </div>
          <div className="stat">
            <div className="label">販売費及び一般管理費</div>
            <div className="value">{yen(s.sga)}</div>
          </div>
          <div className="stat">
            <div className="label">税引前当期純利益</div>
            <div className="value">{yen(s.income_before_taxes)}</div>
          </div>
          <div className="stat">
            <div className="label">未入金の請求</div>
            <div className="value">{yen(unpaid.reduce((a, b) => a + b.remaining_amount, 0))}</div>
          </div>
        </div>
      ) : null}

      <div className="grid">
        <Card title="14日以内の期限">
          {soon.length === 0 ? (
            <p className="muted">14日以内に期限を迎えるものはありません。</p>
          ) : (
            <DataTable columns={[["date", "期限"], ["title", "内容"]]} rows={soon} />
          )}
        </Card>
        <Card title="未入金の請求書" actions={<Link href="/invoices">請求書へ</Link>}>
          <DataTable
            columns={[["invoice_number", "番号"], ["client_name", "請求先"], ["due_date", "支払期日"], ["remaining_amount", "残高"]]}
            rows={unpaid}
            empty="未入金の請求書はありません。"
          />
        </Card>
      </div>

      <Card title="今後の期限（60日）">
        <ErrorBox error={deadlines.error} />
        <DataTable columns={[["date", "期限"], ["title", "内容"], ["detail", "補足"]]} rows={deadlines.data?.items ?? []} />
      </Card>
    </>
  );
}
