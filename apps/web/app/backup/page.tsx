"use client";

import { useState } from "react";
import { Card, ErrorBox, PageTitle } from "@/components/ui";
import { buildUrl } from "@/lib/client";

export default function BackupPage() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [done, setDone] = useState("");

  async function download(includeFiles: boolean) {
    setBusy(true);
    setError(null);
    setDone("");
    try {
      const res = await fetch(buildUrl("exports", { include_files: includeFiles }), { method: "POST" });
      if (!res.ok) throw new Error(`ダウンロードに失敗しました（${res.status}）`);
      const blob = await res.blob();
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `accounting-export-${new Date().toISOString().slice(0, 10)}.zip`;
      a.click();
      URL.revokeObjectURL(a.href);
      setDone(`ダウンロードしました（${(blob.size / 1024 / 1024).toFixed(1)}MB）`);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageTitle title="バックアップ">すべてのデータを1つの ZIP ファイルにまとめてダウンロードします。</PageTitle>
      <Card title="全データのダウンロード">
        <p>
          仕訳・請求書・給与などの登録内容（表計算ソフトで開ける CSV を含む）と、証憑・書類管理のファイルをまとめてダウンロードします。
          ダウンロードしたファイルは、パソコンや外部のストレージなど、このソフトとは別の場所に保存してください。
        </p>
        <div className="actions">
          <button className="primary" onClick={() => download(true)} disabled={busy}>{busy ? "作成中…" : "ファイルも含めてダウンロード"}</button>
          <button onClick={() => download(false)} disabled={busy}>登録内容だけダウンロード（軽い）</button>
        </div>
        {done ? <p>{done}</p> : null}
        <ErrorBox error={error} />
      </Card>
      <Card title="バックアップについて">
        <ul style={{ margin: 0, paddingLeft: 20 }}>
          <li>クラウドに置いて使う場合は、毎日自動でバックアップが取られます（90日分）。決算で締めた年度のデータは別に長期保存されます。</li>
          <li>このダウンロードは、それとは別に手元にも控えを残すためのものです。決算の後や、大きな変更の前に取っておくと安心です。</li>
          <li>ZIP の中の <code>csv</code> フォルダには表ごとの CSV、<code>evidence</code> と <code>documents</code> フォルダにはファイルが入っています。</li>
        </ul>
      </Card>
    </>
  );
}
