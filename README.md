# Micro-LLC-accounting

マイクロ法人（代表社員1名の合同会社）向けの最小構成会計ソフトです。

- 要件定義書: [docs/micro_llc_accounting_requirements.md](docs/micro_llc_accounting_requirements.md) v1.0
- 設計書: [docs/micro_llc_accounting_design.md](docs/micro_llc_accounting_design.md) v1.0（Cloudflare Workers 構成）

## 構成

```
apps/
  web/    Next.js（App Router, TypeScript）+ OpenNext（Cloudflare Workers）
  api/    FastAPI（Python Workers）。業務ロジックは src/domain/ に純粋な Python で実装
  jobs/   Python Workers（Cron Trigger）。日次バックアップ
migrations/  D1 マイグレーション
seed/        勘定科目・税区分・設定値（rule_settings）の初期データ
scripts/     Cloudflare の初期作成、エクスポートからの復元
```

## ローカルでの起動

前提: Node.js 20 以上、Python 3.11 以上、[uv](https://docs.astral.sh/uv/) 0.12.3 以上

### 1. API（ポート 8787）

```bash
cd apps/api
uv sync
uv run uvicorn local_server:app --app-dir src --port 8787 --reload
```

- ローカルでは Cloudflare D1 の代わりに SQLite（`apps/api/.local/ledger.sqlite3`）、R2 の代わりにローカルフォルダ（`apps/api/.local/evidence/`）を使います。
- 初回起動時に `migrations/*.sql` と `seed/*.sql` を自動で適用します。

### 2. Web（ポート 3000）

```bash
cd apps/web
npm install
npm run dev
```

ブラウザで http://localhost:3000 を開きます。初回は「初期設定」画面で会社情報・会計期間・消費税設定を入力してください。

- Web から API への呼び出しは `lib/api-client.ts` に集約しています。Workers 上では Service Binding（`env.API`）、ローカルでは環境変数 `API_BASE_URL`（既定値 `http://127.0.0.1:8787`）に中継します。ブラウザから API を直接呼ぶことはありません。

## Cloudflare と同じ環境での確認（アカウント不要）

Workers のランタイム（workerd）と、ローカルの D1・R2 で動かします。本番に出す前の確認に使います。
Windows では `PYTHONUTF8=1` が必要です（設定ファイルの日本語を読むため）。

```bash
# API（Python Workers、ポート 8788）
cd apps/api
uv sync --group workers
npx --prefix ../web wrangler d1 migrations apply ledger --local
for f in ../../seed/*.sql; do npx --prefix ../web wrangler d1 execute ledger --local --file "$f"; done
PYTHONUTF8=1 uv run pywrangler dev --port 8788 --test-scheduled

# Web（OpenNext でビルドした Worker、ポート 8790）。API とは Service Binding でつながる
cd apps/web
cp .dev.vars.example .dev.vars   # localhost に限り Cloudflare Access の確認を省略する
npx opennextjs-cloudflare build
npx wrangler dev --port 8790
```

http://localhost:8790 を開きます。定期実行（自動記帳）は次で呼び出せます。

```bash
curl -X POST "http://127.0.0.1:8788/cdn-cgi/local/explorer/api/local/scheduled?worker=accounting-api" -H "content-type: application/json" -d '{"cron":"30 15 * * *"}'
```

## Cloudflare へのデプロイ（CI/CD）

`main` に Push すると、GitHub Actions（`.github/workflows/deploy.yml`）が次を自動で行います。

1. 確認: API の読み込み、マイグレーションの適用確認、Web の型チェックとビルド（Pull Request でも実行）
2. デプロイ: D1 マイグレーション → 初期データ（重複しない）→ api・jobs・web の Workers

Cloudflare の設定が済むまでは、確認だけを行い、デプロイは省略します。最初に1回だけ次を行ってください。

1. `npx --prefix apps/web wrangler login` で Cloudflare にログインし、`bash scripts/cloudflare-setup.sh` を実行する（D1・R2・KV を作成）
2. GitHub の Settings → Secrets and variables → Actions に登録する
   - Secrets: `CLOUDFLARE_API_TOKEN`（Workers・D1・R2・KV の編集権限）、`CLOUDFLARE_ACCOUNT_ID`
   - Variables: `D1_DATABASE_ID`、`KV_NAMESPACE_ID`、`CF_ACCESS_TEAM_DOMAIN`、`CF_ACCESS_AUD`
3. Cloudflare Zero Trust で Access アプリケーションを作り、自分のメールアドレスだけを許可する
4. R2 のバケットロック（7年保存）を管理画面で設定する

`CF_ACCESS_TEAM_DOMAIN` / `CF_ACCESS_AUD` が無い状態では、本番の画面からはデータを読めません（安全側に倒しています）。

## 月額費用の目安

| 項目 | 費用 |
|---|---|
| Workers Paid プラン | 月5ドル（Workers・D1・KV の利用枠を含む。1人で使う量は枠内に収まる見込み） |
| R2（証憑・書類・バックアップ） | 月10GBまで無料。超えた分は 1GB あたり月0.015ドル程度 |
| Cloudflare Access | 50ユーザーまで無料 |
| GitHub Actions | 公開リポジトリは無料 |
| 独自ドメイン（任意） | 使う場合のみ年額（.com で年10ドル前後） |

料金は変わることがあるため、契約前に Cloudflare の料金ページで確認してください。

## データの復元

画面「バックアップ」でダウンロードした ZIP から、復元用の SQL を作れます。

```bash
python scripts/restore_export.py accounting-export-YYYY-MM-DD.zip > restore.sql
```

## 実装上の仮決め（設計書・要件定義書からの補足）

| 項目 | 仮決めした内容 |
|---|---|
| ローカルの API | Python Workers（pywrangler）に加え、CPython + uvicorn + SQLite で動く経路を用意した（`src/local_server.py`）。業務ロジックとルーターは共通 |
| Workers のエントリポイント | 設計書の `asgi.entrypoint(app)` ではなく、現行の `WorkerEntrypoint` + `asgi.fetch` の形で記述（wrangler dev で確認済み） |
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
| 自動記帳 | 定型仕訳の自動記帳は api の Cron（毎日0時30分）とホーム画面を開いたときに実行 |
| ローカル確認時の Access | `.dev.vars` の `ACCESS_LOCAL_BYPASS=true` かつ localhost へのアクセスのときだけ、Access の確認を省略 |
| OpenNext のキャッシュ | 設計書の `NEXT_CACHE` ではなく、OpenNext の KV キャッシュが要求する `NEXT_INC_CACHE_KV` を使用 |
| Access の JWT 検証 | Next.js のミドルウェアではなく、API 中継の Route Handler（`/api/proxy`）で検証 |

## 注意

- 税額計算（法人税等の概算・年末調整など）は**概算**です。申告書の作成は e-Tax や申告ソフトで行ってください。
- 税率・控除率・しきい値は `rule_settings` テーブルで管理しています。法改正時は画面「税率・基準額」から追加・更新してください。
- マイナンバーは保存しません。
