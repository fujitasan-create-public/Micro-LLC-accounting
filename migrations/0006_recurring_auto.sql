-- Migration number: 0006  定型仕訳の自動計上（家賃・口座振替など、毎月自動で引き落とされるもの）
-- start_month から end_month まで、計上日が来た月の仕訳を自動で作る（recurring_runs で二重計上を防ぐ）
ALTER TABLE recurring_templates ADD COLUMN start_month TEXT;   -- 'YYYY-MM'。NULL は作成した月から
ALTER TABLE recurring_templates ADD COLUMN end_month TEXT;     -- 'YYYY-MM'。NULL は期限なし
ALTER TABLE recurring_templates ADD COLUMN auto_post INTEGER NOT NULL DEFAULT 1;
