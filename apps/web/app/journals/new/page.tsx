"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";
import { AccountSelect, Card, ErrorBox, Field, Notice, PageTitle, Warnings } from "@/components/ui";
import { api, todayIso, useApi, yen, type Warning } from "@/lib/client";

type Line = { side: "debit" | "credit"; account_code: string; amount: string; tax_code: string; tax_amount: string };

const newLine = (side: "debit" | "credit"): Line => ({ side, account_code: "", amount: "", tax_code: "", tax_amount: "" });
const SOURCE_TITLES: Record<string, string> = {
  manual: "仕訳の入力",
  opening_balance: "開始残高の入力",
  closing_adjustment: "決算整理仕訳の入力",
};

export default function NewJournalPage() {
  return (
    <Suspense fallback={<p className="muted">読み込み中…</p>}>
      <JournalForm />
    </Suspense>
  );
}

function JournalForm() {
  const params = useSearchParams();
  const source = params.get("source") ?? "manual";
  const copyId = params.get("copy");
  const accounts = useApi<{ items: any[] }>("accounts");
  const taxCodes = useApi<{ items: any[] }>("tax-codes");
  const cps = useApi<{ items: any[] }>("counterparties");
  const pas = useApi<{ items: any[] }>("payment-accounts");

  const [date, setDate] = useState(todayIso());
  const [description, setDescription] = useState("");
  const [counterpartyId, setCounterpartyId] = useState("");
  const [paymentAccountId, setPaymentAccountId] = useState("");
  const [lines, setLines] = useState<Line[]>([newLine("debit"), newLine("credit")]);
  const [ent, setEnt] = useState({ participants: "", headcount: "", is_food_and_drink: true, venue: "", is_internal_only: false });
  const [file, setFile] = useState<File | null>(null);
  const [att, setAtt] = useState({ received_date: todayIso(), receipt_channel: "electronic", amount: "", counterparty_name: "" });
  const [error, setError] = useState<unknown>(null);
  const [warnings, setWarnings] = useState<Warning[]>([]);
  const [saved, setSaved] = useState<any>(null);
  const [busy, setBusy] = useState(false);

  const accountMap = useMemo(() => Object.fromEntries((accounts.data?.items ?? []).map((a) => [a.code, a])), [accounts.data]);
  const cp = cps.data?.items.find((c) => c.id === counterpartyId);

  // 複製して訂正（取消＋再入力）
  useEffect(() => {
    if (!copyId) return;
    api(`journals/${copyId}`).then((e) => {
      setDate(e.transaction_date);
      setDescription(e.description);
      setCounterpartyId(e.counterparty_id ?? "");
      setPaymentAccountId(e.payment_account_id ?? "");
      // 税抜経理で本体と仮払／仮受消費税等に分かれている場合は、税込の1行に戻す
      const split = e.lines.some((l: any) => ["160", "245"].includes(l.account_code));
      setLines(e.lines.filter((l: any) => !(split && ["160", "245"].includes(l.account_code))).map((l: any) => ({
        side: l.side, account_code: l.account_code, amount: String(l.amount + (split ? l.tax_amount : 0)), tax_code: l.tax_code, tax_amount: "",
      })));
    }).catch(setError);
  }, [copyId]);

  const setLine = (i: number, patch: Partial<Line>) => setLines(lines.map((l, j) => (j === i ? { ...l, ...patch } : l)));

  function onAccount(i: number, code: string) {
    // FR-10: 科目を選ぶと税区分の初期値が入る（変更可）
    const def = accountMap[code]?.default_tax_code ?? "NT";
    setLine(i, { account_code: code, tax_code: def });
  }

  function onPaymentAccount(id: string) {
    setPaymentAccountId(id);
    const pa = pas.data?.items.find((p) => p.id === id);
    if (!pa) return;
    // 支払元の科目を貸方の空欄に入れる（役員立替なら役員借入金、FR-15）
    const idx = lines.findIndex((l) => l.side === "credit" && !l.account_code);
    if (idx >= 0) setLine(idx, { account_code: pa.linked_account_code, tax_code: "NT" });
  }

  const debit = lines.filter((l) => l.side === "debit").reduce((a, l) => a + (Number(l.amount) || 0), 0);
  const credit = lines.filter((l) => l.side === "credit").reduce((a, l) => a + (Number(l.amount) || 0), 0);
  const hasEntertainment = lines.some((l) => l.account_code === "590" && l.side === "debit");
  const entTotal = lines.filter((l) => l.account_code === "590" && l.side === "debit").reduce((a, l) => a + (Number(l.amount) || 0), 0);
  const perPerson = Number(ent.headcount) > 0 ? Math.floor(entTotal / Number(ent.headcount)) : null;
  const needsCp = lines.some((l) => accountMap[l.account_code]?.requires_counterparty);
  const willBeTransitional = cp && !cp.invoice_registration_number && lines.some((l) => ["P10", "P08"].includes(l.tax_code));

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setWarnings([]);
    setBusy(true);
    try {
      const body = {
        transaction_date: date,
        description,
        counterparty_id: counterpartyId || null,
        payment_account_id: paymentAccountId || null,
        source,
        lines: lines.filter((l) => l.account_code && l.amount !== "").map((l) => ({
          side: l.side, account_code: l.account_code, amount: Number(l.amount), tax_code: l.tax_code || null,
          tax_amount: l.tax_amount === "" ? null : Number(l.tax_amount),
        })),
        entertainment_detail: hasEntertainment ? { ...ent, headcount: Number(ent.headcount) || 0, venue: ent.venue || null } : null,
      };
      const r = await api("journals", { body });
      let ws: Warning[] = r.warnings ?? [];
      if (file) {
        // FR-16 / BR-061: 証憑の検索項目（取引年月日・金額・取引先）を入力して保存
        const fd = new FormData();
        fd.set("file", file);
        fd.set("received_date", att.received_date);
        fd.set("transaction_date", date);
        fd.set("amount", att.amount || String(debit));
        fd.set("counterparty_name", att.counterparty_name || cp?.name || description);
        fd.set("receipt_channel", att.receipt_channel);
        fd.set("entry_id", r.entry.id);
        const a = await api("attachments", { form: fd });
        ws = ws.concat(a.warnings ?? []);
      }
      setWarnings(ws);
      setSaved(r.entry);
      setDescription("");
      setLines([newLine("debit"), newLine("credit")]);
      setFile(null);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  const taxOptions = taxCodes.data?.items ?? [];

  return (
    <>
      <PageTitle title={SOURCE_TITLES[source] ?? "仕訳の入力"}>
        借方と貸方の合計が一致しない仕訳は保存できません。税込経理では金額は税込で入力します。
      </PageTitle>
      {copyId ? <Notice>元の仕訳を複製しました。訂正する場合は、元の仕訳を取り消してからこの内容で登録してください。</Notice> : null}
      <Card>
        <form onSubmit={submit}>
          <div className="form">
            <Field label="取引日"><input type="date" value={date} onChange={(e) => setDate(e.target.value)} required /></Field>
            <Field label="摘要" wide><input value={description} onChange={(e) => setDescription(e.target.value)} required /></Field>
            <Field label={`取引先${needsCp ? "（必須）" : ""}`} hint={cp && !cp.invoice_registration_number ? "インボイス登録番号なし: 課税仕入は経過措置の区分になります" : undefined}>
              <select value={counterpartyId} onChange={(e) => setCounterpartyId(e.target.value)} required={needsCp}>
                <option value="">なし</option>
                {cps.data?.items.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
            </Field>
            <Field label="支払元・入金先">
              <select value={paymentAccountId} onChange={(e) => onPaymentAccount(e.target.value)}>
                <option value="">指定なし</option>
                {pas.data?.items.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
              </select>
            </Field>
          </div>

          <div className="table-wrap" style={{ marginTop: 12 }}>
            <table>
              <thead><tr><th>貸借</th><th>勘定科目</th><th className="num">金額</th><th>税区分</th><th className="num">消費税額</th><th /></tr></thead>
              <tbody>
                {lines.map((l, i) => (
                  <tr key={i}>
                    <td>
                      <select value={l.side} onChange={(e) => setLine(i, { side: e.target.value as Line["side"] })}>
                        <option value="debit">借方</option>
                        <option value="credit">貸方</option>
                      </select>
                    </td>
                    <td><AccountSelect accounts={accounts.data?.items ?? []} value={l.account_code} onChange={(c) => onAccount(i, c)} /></td>
                    <td><input type="number" className="num" min={0} value={l.amount} onChange={(e) => setLine(i, { amount: e.target.value })} /></td>
                    <td>
                      <select value={l.tax_code} onChange={(e) => setLine(i, { tax_code: e.target.value })}>
                        <option value="">科目の初期値</option>
                        {taxOptions.map((t) => <option key={t.code} value={t.code}>{t.name}</option>)}
                      </select>
                    </td>
                    <td><input type="number" className="num" min={0} placeholder="自動" value={l.tax_amount} onChange={(e) => setLine(i, { tax_amount: e.target.value })} /></td>
                    <td>{lines.length > 2 ? <button type="button" onClick={() => setLines(lines.filter((_, j) => j !== i))}>削除</button> : null}</td>
                  </tr>
                ))}
                <tr>
                  <td colSpan={2} className="muted">借方合計 {yen(debit)} ／ 貸方合計 {yen(credit)}</td>
                  <td colSpan={4}>{debit !== credit ? <span style={{ color: "var(--danger)" }}>差額 {yen(debit - credit)}</span> : <span className="badge ok">一致</span>}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <div className="actions" style={{ margin: "8px 0 16px" }}>
            <button type="button" onClick={() => setLines([...lines, newLine("debit")])}>＋借方</button>
            <button type="button" onClick={() => setLines([...lines, newLine("credit")])}>＋貸方</button>
          </div>
          {willBeTransitional ? <Notice>取引先にインボイス登録番号がないため、保存時に課税仕入の税区分を経過措置（取引日に応じた控除率）に変更します。</Notice> : null}

          {hasEntertainment ? (
            <Card title="交際費の内容">
              <div className="form">
                <Field label="参加者（氏名・関係）" wide><input value={ent.participants} onChange={(e) => setEnt({ ...ent, participants: e.target.value })} placeholder="例: A社 山田部長、当社 代表社員" /></Field>
                <Field label="人数"><input type="number" min={1} className="num" value={ent.headcount} onChange={(e) => setEnt({ ...ent, headcount: e.target.value })} /></Field>
                <Field label="店名"><input value={ent.venue} onChange={(e) => setEnt({ ...ent, venue: e.target.value })} /></Field>
                <Field label="飲食"><span className="check"><input type="checkbox" checked={ent.is_food_and_drink} onChange={(e) => setEnt({ ...ent, is_food_and_drink: e.target.checked })} /> 飲食費</span></Field>
                <Field label="社内飲食"><span className="check"><input type="checkbox" checked={ent.is_internal_only} onChange={(e) => setEnt({ ...ent, is_internal_only: e.target.checked })} /> 社内のみ</span></Field>
              </div>
              {perPerson !== null ? <p>1人あたり <strong>{yen(perPerson)}円</strong>{ent.is_food_and_drink && !ent.is_internal_only && perPerson <= 10000 ? "（1万円以下の飲食費として交際費から除外できます）" : ""}</p> : null}
            </Card>
          ) : null}

          <Card title="証憑の添付">
            <div className="form">
              <Field label="ファイル（PDF・画像など、20MBまで）"><input type="file" onChange={(e) => setFile(e.target.files?.[0] ?? null)} /></Field>
              {file ? (
                <>
                  <Field label="受領日"><input type="date" value={att.received_date} onChange={(e) => setAtt({ ...att, received_date: e.target.value })} /></Field>
                  <Field label="取引金額" hint="空欄なら仕訳の金額"><input type="number" className="num" value={att.amount} onChange={(e) => setAtt({ ...att, amount: e.target.value })} /></Field>
                  <Field label="取引先" hint="空欄なら仕訳の取引先"><input value={att.counterparty_name} onChange={(e) => setAtt({ ...att, counterparty_name: e.target.value })} /></Field>
                  <Field label="受領方法" hint="電子で受け取ったものは電子データのまま保存します">
                    <select value={att.receipt_channel} onChange={(e) => setAtt({ ...att, receipt_channel: e.target.value })}>
                      <option value="electronic">電子取引</option>
                      <option value="paper_scanned">紙をスキャン</option>
                      <option value="paper">紙</option>
                    </select>
                  </Field>
                </>
              ) : null}
            </div>
          </Card>

          <div className="actions">
            <button className="primary" disabled={busy || debit !== credit || debit === 0}>保存</button>
            <Link href="/journals">一覧へ</Link>
          </div>
        </form>
        <ErrorBox error={error} />
        <Warnings items={warnings} />
        {saved ? <p className="muted">保存しました: {saved.transaction_date} {saved.description}（{yen(saved.total_amount)}円）</p> : null}
      </Card>
    </>
  );
}
