# Micro-LLC-accounting

マイクロ法人（代表社員1名の合同会社）向けの最小構成会計ソフトです。

- 要件定義書: [docs/micro_llc_accounting_requirements.md](docs/micro_llc_accounting_requirements.md) v1.0
- 設計書: [docs/micro_llc_accounting_design.md](docs/micro_llc_accounting_design.md) v1.0（Cloudflare Workers 構成）

## 構成

```
apps/
  web/    Next.js（App Router, TypeScript）+ OpenNext（Cloudflare Workers）
  api/    FastAPI（Python Workers）。業務ロジックは src/domain/ に純粋な Python で実装
  jobs/   Python Workers（Cron Trigger）。日次バックアップと期限計算
migrations/  D1 マイグレーション
seed/        勘定科目・税区分・設定値（rule_settings）の初期データ
```

## ローカルでの起動

前提: Node.js 20 以上、Python 3.11 以上、[uv](https://docs.astral.sh/uv/)

### 1. API（ポート 8787）

```bash
cd apps/api
uv sync
uv run uvicorn local_server:app --app-dir src --port 8787 --reload
```

- ローカルでは Cloudflare D1 の代わりに SQLite（`apps/api/.local/ledger.sqlite3`）、R2 の代わりにローカルフォルダ（`apps/api/.local/evidence/`）を使います。
- 初回起動時に `migrations/*.sql` と `seed/*.sql` を自動で適用します。
- Workers 上と同じ環境で確認する場合は `uv run pywrangler dev`（D1・R2 はローカルエミュレーション）を使います。この場合は事前に `npx wrangler d1 migrations apply ledger --local` と seed の投入が必要です。

### 2. Web（ポート 3000）

```bash
cd apps/web
npm install
npm run dev
```

ブラウザで http://localhost:3000 を開きます。初回は「初期設定」画面で会社情報・会計期間・消費税設定を入力してください。

- Web から API への呼び出しは `lib/api-client.ts` に集約しています。Workers 上では Service Binding（`env.API`）、ローカルでは環境変数 `API_BASE_URL`（既定値 `http://127.0.0.1:8787`）に中継します。ブラウザから API を直接呼ぶことはありません。

## デプロイ

`.github/workflows/deploy.yml`（手動実行）を参照。GitHub Secrets に `CLOUDFLARE_API_TOKEN` と `CLOUDFLARE_ACCOUNT_ID` を登録してください。
各 `wrangler.jsonc` の `<D1_ID>` `<KV_ID>` は、リソース作成後に実際の ID に置き換えます。
`apps/web/wrangler.jsonc` の `CF_ACCESS_TEAM_DOMAIN` / `CF_ACCESS_AUD` を設定しないと、本番では API への中継が 403 になります（安全側に倒しています）。

## データの復元（NFR-04）

画面「設定値・エクスポート」でダウンロードした ZIP から、復元用の SQL を作れます。

```bash
python scripts/restore_export.py accounting-export-YYYY-MM-DD.zip > restore.sql
```

## 実装上の仮決め（設計書・要件定義書からの補足）

| 項目 | 仮決めした内容 |
|---|---|
| ローカルの API | Python Workers（pywrangler）に加え、CPython + uvicorn + SQLite で動く経路を用意した（`src/local_server.py`）。業務ロジックとルーターは共通 |
| Workers のエントリポイント | 設計書の `asgi.entrypoint(app)` ではなく、現行の `WorkerEntrypoint` + `asgi.fetch` の形で記述（【要検証】） |
| services/ 層 | 仕訳の登録を請求・給与・社宅・償却・決算から共通で使うため `apps/api/src/services/` を追加 |
| 勘定科目 | 初期データに「仮払消費税等」「仮受消費税等」（税抜経理用）と「雑損失」（内訳書用）を追加 |
| 税区分 | 非課税仕入（`PEX`）を追加（住宅家賃など）。経過措置は `P10N` / `P08N` |
| 税抜経理 | 入力は税込で受け取り、本体と仮払／仮受消費税等に自動で分ける |
| 取消し | 未締めの期間は `voided_at` を設定、締め済みの期間は当期に逆仕訳を作る |
| 会社負担の社会保険料 | 給与の登録時に「法定福利費／未払費用」で計上し、口座振替時に消し込む |
| 未払法人税等 | 中間納付は納付時に「法人税、住民税及び事業税」で処理している前提で、概算額から中間納付額を差し引いて計上 |
| 消費税の計算 | 割戻し計算のみ（積上げ計算は未対応） |
| 源泉徴収税額表 | 税額表そのものは同梱せず、CSV で取り込む方式（未取込なら手入力） |
| 年末調整 | 簡易計算。配偶者特別控除・障害者控除などは未対応 |
| 定率法 | 200%定率法の近似（保証率・改定償却率の表は未使用） |
| 年次アーカイブ | 締め処理は api で行うため、api にも `BACKUP`（R2）をバインド |
| 期限通知 | jobs は日次バックアップのみ。期限一覧は api がその都度計算してトップ画面に表示 |
| OpenNext のキャッシュ | 設計書の `NEXT_CACHE` ではなく、OpenNext の KV キャッシュが要求する `NEXT_INC_CACHE_KV` を使用 |
| Access の JWT 検証 | Next.js のミドルウェアではなく、API 中継の Route Handler（`/api/proxy`）で検証 |

## 注意

- 税額計算（法人税等の概算・年末調整など）は**概算**です。申告書の作成は e-Tax や申告ソフトで行ってください。
- 税率・控除率・しきい値は `rule_settings` テーブルで管理しています。法改正時は画面「設定値」から追加・更新してください。
- マイナンバーは保存しません。
