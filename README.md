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

`.github/workflows/deploy.yml` を参照。GitHub Secrets に `CLOUDFLARE_API_TOKEN` と `CLOUDFLARE_ACCOUNT_ID` を登録してください。
各 `wrangler.jsonc` の `<D1_ID>` `<KV_ID>` は、リソース作成後に実際の ID に置き換えます。

## 注意

- 税額計算（法人税等の概算・年末調整など）は**概算**です。申告書の作成は e-Tax や申告ソフトで行ってください。
- 税率・控除率・しきい値は `rule_settings` テーブルで管理しています。法改正時は画面「設定値」から追加・更新してください。
- マイナンバーは保存しません。
