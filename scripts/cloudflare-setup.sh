#!/usr/bin/env bash
# Cloudflare のリソースを最初に1回だけ作る。
#   事前に `npx --prefix apps/web wrangler login` で Cloudflare にログインしておく。
#   実行後に表示される ID を、GitHub の Variables（D1_DATABASE_ID, KV_NAMESPACE_ID）に登録する。
set -euo pipefail
cd "$(dirname "$0")/.."
W="npx --prefix apps/web wrangler"

echo "== D1（会計データ） =="
$W d1 create ledger || echo "（既に作成済みの場合はこのエラーは無視してよい）"

echo "== R2（証憑・書類 / バックアップ） =="
$W r2 bucket create accounting-evidence || true
$W r2 bucket create accounting-backup || true

echo "== R2 バックアップの自動削除（日次バックアップは90日で削除） =="
$W r2 bucket lifecycle add accounting-backup daily-90d backup/daily/ --expire-days 90 || true

echo "== KV（画面のキャッシュ） =="
$W kv namespace create NEXT_INC_CACHE_KV || true

cat <<'EOF'

次の作業:
  1. 上に表示された D1 の database_id と KV の id を、GitHub の
     Settings → Secrets and variables → Actions → Variables に登録する
       D1_DATABASE_ID, KV_NAMESPACE_ID
  2. Cloudflare Zero Trust で Access アプリケーションを作り（許可するのは自分のメールアドレスのみ）、
     チームドメイン（xxx.cloudflareaccess.com）と Application Audience (AUD) を Variables に登録する
       CF_ACCESS_TEAM_DOMAIN, CF_ACCESS_AUD
  3. API トークン（Workers・D1・R2・KV の編集権限）とアカウント ID を Secrets に登録する
       CLOUDFLARE_API_TOKEN, CLOUDFLARE_ACCOUNT_ID
  4. 帳簿の7年保存のため、R2 の accounting-evidence と accounting-backup の backup/closed/ に
     バケットロック（保持期間）を管理画面で設定する
  5. main に Push すると自動でデプロイされる（Actions の画面から手動実行も可）
EOF
