-- Migration number: 0001  初期スキーマ（DM-01〜DM-17、設計書 5章）
-- 金額はすべて円単位の INTEGER。日付は 'YYYY-MM-DD'、日時は ISO 8601（+09:00）。

-- 設定値（BR-000）
CREATE TABLE rule_settings (
  key            TEXT NOT NULL,
  value          TEXT NOT NULL,          -- JSON文字列
  effective_from TEXT NOT NULL,
  effective_to   TEXT,
  note           TEXT,
  PRIMARY KEY (key, effective_from)
);

-- 源泉徴収税額表 月額表・甲欄（FR-32、NFR-07）
CREATE TABLE withholding_tables (
  table_year     INTEGER NOT NULL,       -- 適用年
  min_amount     INTEGER NOT NULL,       -- 社会保険料等控除後の給与等の金額（以上）
  max_amount     INTEGER,                -- 未満。NULL は上限なし
  dependents     INTEGER NOT NULL,       -- 扶養親族等の数（0〜7）
  tax_amount     INTEGER NOT NULL,
  PRIMARY KEY (table_year, min_amount, dependents)
);

-- 会社設定（DM-01）単一レコード
CREATE TABLE company (
  id                          INTEGER PRIMARY KEY CHECK (id = 1),
  trade_name                  TEXT NOT NULL,
  corporate_number            TEXT NOT NULL,
  head_office_address         TEXT NOT NULL,
  representative_name         TEXT NOT NULL,
  incorporation_date          TEXT NOT NULL,
  capital_amount              INTEGER NOT NULL,
  fiscal_year_start_month     INTEGER NOT NULL CHECK (fiscal_year_start_month BETWEEN 1 AND 12),
  blue_return_approved        INTEGER NOT NULL DEFAULT 0,
  blue_return_effective_from  TEXT,
  tax_office                  TEXT NOT NULL,
  prefecture                  TEXT NOT NULL,
  municipality                TEXT NOT NULL,
  accounting_tax_method       TEXT NOT NULL CHECK (accounting_tax_method IN ('tax_included','tax_excluded')),
  updated_at                  TEXT NOT NULL
);

-- 会計期間（DM-03）
CREATE TABLE fiscal_periods (
  id         TEXT PRIMARY KEY,
  start_date TEXT NOT NULL,
  end_date   TEXT NOT NULL,
  status     TEXT NOT NULL CHECK (status IN ('open','closing','closed'))
);

-- 消費税設定（DM-02）事業年度ごとに1レコード
CREATE TABLE consumption_tax_settings (
  fiscal_period_id              TEXT PRIMARY KEY REFERENCES fiscal_periods(id),
  taxable_status                TEXT NOT NULL CHECK (taxable_status IN ('exempt','taxable')),
  invoice_registration_number   TEXT,
  calculation_method            TEXT NOT NULL CHECK (calculation_method IN ('standard','simplified','two_tenths_special')),
  simplified_business_category  TEXT CHECK (simplified_business_category IN ('1','2','3','4','5','6')),
  interim_filing_required       INTEGER NOT NULL DEFAULT 0
);

-- 税区分（DM-05）
CREATE TABLE tax_codes (
  code            TEXT PRIMARY KEY,
  name            TEXT NOT NULL,
  kind            TEXT NOT NULL CHECK (kind IN ('taxable_sales','exempt_sales','non_taxable','taxable_purchase')),
  rate            TEXT,                  -- "0.10" / "0.08"
  invoice_status  TEXT CHECK (invoice_status IN ('qualified','non_qualified_transitional','not_applicable')),
  sort_order      INTEGER NOT NULL DEFAULT 0
);

-- 勘定科目（DM-04）
CREATE TABLE accounts (
  code                   TEXT PRIMARY KEY,
  name                   TEXT NOT NULL,
  category               TEXT NOT NULL CHECK (category IN ('asset','liability','equity','revenue','expense')),
  statement_section      TEXT NOT NULL,
  default_tax_code       TEXT NOT NULL REFERENCES tax_codes(code),
  requires_counterparty  INTEGER NOT NULL DEFAULT 0,
  is_active              INTEGER NOT NULL DEFAULT 1
);

-- 取引先（DM-06）
CREATE TABLE counterparties (
  id                           TEXT PRIMARY KEY,
  name                         TEXT NOT NULL,
  entity_type                  TEXT NOT NULL CHECK (entity_type IN ('corporation','individual')),
  invoice_registration_number  TEXT,
  address                      TEXT,
  bank_account                 TEXT,
  is_client                    INTEGER NOT NULL DEFAULT 0,
  created_at                   TEXT NOT NULL,
  updated_at                   TEXT NOT NULL
);

-- 口座・支払手段（DM-07）
CREATE TABLE payment_accounts (
  id                   TEXT PRIMARY KEY,
  name                 TEXT NOT NULL,     -- 表示名（設計上の追加項目）
  type                 TEXT NOT NULL CHECK (type IN ('bank','credit_card','cash','officer_advance')),
  bank_name            TEXT,
  branch_name          TEXT,
  account_kind         TEXT,
  account_number       TEXT,
  linked_account_code  TEXT NOT NULL REFERENCES accounts(code),
  csv_import_format    TEXT,
  created_at           TEXT NOT NULL,
  updated_at           TEXT NOT NULL
);

-- 仕訳ヘッダ（DM-08）
CREATE TABLE journal_entries (
  id                  TEXT PRIMARY KEY,
  fiscal_period_id    TEXT NOT NULL REFERENCES fiscal_periods(id),
  transaction_date    TEXT NOT NULL,
  description         TEXT NOT NULL,
  counterparty_id     TEXT REFERENCES counterparties(id),
  payment_account_id  TEXT REFERENCES payment_accounts(id),
  entertainment_json  TEXT,
  source              TEXT NOT NULL CHECK (source IN ('manual','csv_import','recurring','closing_adjustment','opening_balance','carryover')),
  reverses_entry_id   TEXT REFERENCES journal_entries(id),
  voided_at           TEXT,
  created_at          TEXT NOT NULL,
  updated_at          TEXT NOT NULL
);
CREATE INDEX idx_je_date ON journal_entries(transaction_date);
CREATE INDEX idx_je_counterparty ON journal_entries(counterparty_id);
CREATE INDEX idx_je_period ON journal_entries(fiscal_period_id);

-- 仕訳明細（DM-08）
CREATE TABLE journal_lines (
  id                   TEXT PRIMARY KEY,
  entry_id             TEXT NOT NULL REFERENCES journal_entries(id),
  line_no              INTEGER NOT NULL,
  side                 TEXT NOT NULL CHECK (side IN ('debit','credit')),
  account_code         TEXT NOT NULL REFERENCES accounts(code),
  amount               INTEGER NOT NULL CHECK (amount >= 0),
  tax_code             TEXT NOT NULL REFERENCES tax_codes(code),
  tax_amount           INTEGER NOT NULL DEFAULT 0,
  deductible_rate_pct  INTEGER,
  UNIQUE (entry_id, line_no)
);
CREATE INDEX idx_jl_account ON journal_lines(account_code);
CREATE INDEX idx_jl_entry ON journal_lines(entry_id);

-- 証憑（DM-09）
CREATE TABLE attachments (
  id                 TEXT PRIMARY KEY,
  r2_key             TEXT NOT NULL UNIQUE,
  original_filename  TEXT NOT NULL,
  sha256             TEXT NOT NULL,
  content_type       TEXT NOT NULL,
  size_bytes         INTEGER NOT NULL,
  received_date      TEXT NOT NULL,
  transaction_date   TEXT NOT NULL,
  amount             INTEGER NOT NULL,
  counterparty_name  TEXT NOT NULL,
  receipt_channel    TEXT NOT NULL CHECK (receipt_channel IN ('electronic','paper_scanned','paper')),
  voided_at          TEXT,
  created_at         TEXT NOT NULL,
  updated_at         TEXT NOT NULL
);
CREATE INDEX idx_att_search ON attachments(transaction_date, amount, counterparty_name);

CREATE TABLE journal_attachments (
  entry_id      TEXT NOT NULL REFERENCES journal_entries(id),
  attachment_id TEXT NOT NULL REFERENCES attachments(id),
  PRIMARY KEY (entry_id, attachment_id)
);

-- 明細CSV取込の科目推定ルール（FR-13）
CREATE TABLE import_rules (
  id                TEXT PRIMARY KEY,
  keyword           TEXT NOT NULL,         -- 摘要に含まれる文字列
  account_code      TEXT NOT NULL REFERENCES accounts(code),
  tax_code          TEXT REFERENCES tax_codes(code),
  counterparty_id   TEXT REFERENCES counterparties(id),
  priority          INTEGER NOT NULL DEFAULT 100,
  created_at        TEXT NOT NULL
);

-- 定型仕訳（FR-14）
CREATE TABLE recurring_templates (
  id                  TEXT PRIMARY KEY,
  name                TEXT NOT NULL,
  day_of_month        INTEGER NOT NULL CHECK (day_of_month BETWEEN 1 AND 31),
  description         TEXT NOT NULL,
  counterparty_id     TEXT REFERENCES counterparties(id),
  payment_account_id  TEXT REFERENCES payment_accounts(id),
  lines_json          TEXT NOT NULL,       -- [{side, account_code, amount, tax_code}]
  is_active           INTEGER NOT NULL DEFAULT 1,
  created_at          TEXT NOT NULL,
  updated_at          TEXT NOT NULL
);

-- 売上請求（DM-10）
CREATE TABLE sales_invoices (
  id                 TEXT PRIMARY KEY,
  invoice_number     TEXT NOT NULL UNIQUE,
  client_id          TEXT NOT NULL REFERENCES counterparties(id),
  issue_date         TEXT NOT NULL,
  service_period     TEXT NOT NULL,
  lines_json         TEXT NOT NULL,        -- [{description, amount, tax_rate, is_reduced}]
  due_date           TEXT NOT NULL,
  status             TEXT NOT NULL CHECK (status IN ('issued','partially_paid','paid')),
  total_amount       INTEGER NOT NULL,     -- 税込請求額
  received_amount    INTEGER NOT NULL DEFAULT 0,
  bank_fee_deducted  INTEGER NOT NULL DEFAULT 0,
  journal_entry_id   TEXT REFERENCES journal_entries(id),
  voided_at          TEXT,
  created_at         TEXT NOT NULL,
  updated_at         TEXT NOT NULL
);

CREATE TABLE sales_invoice_receipts (
  id                 TEXT PRIMARY KEY,
  invoice_id         TEXT NOT NULL REFERENCES sales_invoices(id),
  received_date      TEXT NOT NULL,
  received_amount    INTEGER NOT NULL,
  bank_fee           INTEGER NOT NULL DEFAULT 0,
  payment_account_id TEXT NOT NULL REFERENCES payment_accounts(id),
  journal_entry_id   TEXT REFERENCES journal_entries(id),
  created_at         TEXT NOT NULL
);

-- 役員（DM-11）マイナンバーの列は作らない（NFR-05）
CREATE TABLE officers (
  id                           TEXT PRIMARY KEY,
  name                         TEXT NOT NULL,
  address                      TEXT NOT NULL,
  my_number_stored_externally  INTEGER NOT NULL DEFAULT 1,
  dependents_json              TEXT NOT NULL DEFAULT '[]',
  created_at                   TEXT NOT NULL,
  updated_at                   TEXT NOT NULL
);

CREATE TABLE officer_compensations (
  id               TEXT PRIMARY KEY,
  officer_id       TEXT NOT NULL REFERENCES officers(id),
  effective_from   TEXT NOT NULL,
  monthly_amount   INTEGER NOT NULL,
  payment_day      INTEGER NOT NULL CHECK (payment_day BETWEEN 1 AND 31),
  resolution_date  TEXT NOT NULL,
  revision_reason  TEXT NOT NULL CHECK (revision_reason IN ('regular','performance_deterioration','other')),
  created_at       TEXT NOT NULL
);

-- 給与支給実績（DM-12）
CREATE TABLE payroll_records (
  id                              TEXT PRIMARY KEY,
  officer_id                      TEXT NOT NULL REFERENCES officers(id),
  pay_date                        TEXT NOT NULL,
  gross_amount                    INTEGER NOT NULL,
  health_insurance_employee       INTEGER NOT NULL,
  pension_employee                INTEGER NOT NULL,
  health_insurance_employer       INTEGER NOT NULL,
  pension_employer                INTEGER NOT NULL,
  standard_monthly_remuneration   INTEGER NOT NULL,
  withholding_income_tax          INTEGER NOT NULL,
  resident_tax                    INTEGER NOT NULL,
  company_housing_deduction       INTEGER NOT NULL DEFAULT 0,
  net_amount                      INTEGER NOT NULL,
  payment_account_id              TEXT REFERENCES payment_accounts(id),
  journal_entry_id                TEXT REFERENCES journal_entries(id),
  voided_at                       TEXT,
  created_at                      TEXT NOT NULL,
  updated_at                      TEXT NOT NULL
);
CREATE INDEX idx_payroll_date ON payroll_records(pay_date);

-- 源泉所得税の設定（DM-13）
CREATE TABLE withholding_settings (
  id                        INTEGER PRIMARY KEY CHECK (id = 1),
  special_payment_deadline  INTEGER NOT NULL DEFAULT 0,
  updated_at                TEXT NOT NULL
);

CREATE TABLE withholding_payments (
  id         TEXT PRIMARY KEY,
  period     TEXT NOT NULL,            -- 例: '2026-01' または '2026-H1'
  amount     INTEGER NOT NULL,
  paid_date  TEXT NOT NULL,
  created_at TEXT NOT NULL
);

-- 年末調整情報（DM-14）
CREATE TABLE year_end_adjustments (
  officer_id                          TEXT NOT NULL REFERENCES officers(id),
  year                                INTEGER NOT NULL,
  life_insurance_deduction_inputs     TEXT NOT NULL DEFAULT '{}',
  earthquake_insurance_premium        INTEGER NOT NULL DEFAULT 0,
  small_business_mutual_aid_premium   INTEGER NOT NULL DEFAULT 0,
  social_insurance_paid_personally    INTEGER NOT NULL DEFAULT 0,
  spouse_income                       INTEGER,
  housing_loan_deduction              INTEGER NOT NULL DEFAULT 0,
  updated_at                          TEXT NOT NULL,
  PRIMARY KEY (officer_id, year)
);

-- 借上げ社宅（DM-15）
CREATE TABLE company_housings (
  id                   TEXT PRIMARY KEY,
  landlord_id          TEXT NOT NULL REFERENCES counterparties(id),
  address              TEXT NOT NULL,
  contract_start       TEXT NOT NULL,
  contract_end         TEXT NOT NULL,
  monthly_rent         INTEGER NOT NULL,
  monthly_common_fee   INTEGER NOT NULL DEFAULT 0,
  floor_area_sqm       TEXT NOT NULL,
  structure            TEXT NOT NULL CHECK (structure IN ('wooden','non_wooden')),
  building_tax_base    INTEGER NOT NULL,
  land_tax_base        INTEGER NOT NULL,
  is_luxury            INTEGER NOT NULL DEFAULT 0,
  market_rent          INTEGER,
  collection_amount    INTEGER NOT NULL,
  collection_method    TEXT NOT NULL CHECK (collection_method IN ('payroll_deduction','transfer')),
  created_at           TEXT NOT NULL,
  updated_at           TEXT NOT NULL
);

-- 固定資産（DM-16）
CREATE TABLE fixed_assets (
  id                                   TEXT PRIMARY KEY,
  name                                 TEXT NOT NULL,
  asset_category                       TEXT NOT NULL,
  account_code                         TEXT NOT NULL REFERENCES accounts(code),
  acquisition_date                     TEXT NOT NULL,
  service_start_date                   TEXT NOT NULL,
  acquisition_cost                     INTEGER NOT NULL,
  useful_life_years                    INTEGER NOT NULL,
  depreciation_method                  TEXT NOT NULL CHECK (depreciation_method IN ('straight_line','declining_balance','immediate_small','lump_sum_3y','small_sme_special')),
  disposal_date                        TEXT,
  subject_to_depreciable_asset_return  INTEGER NOT NULL DEFAULT 1,
  created_at                           TEXT NOT NULL,
  updated_at                           TEXT NOT NULL
);

-- 減価償却の実施記録（期ごと）
CREATE TABLE depreciation_runs (
  fiscal_period_id  TEXT NOT NULL REFERENCES fiscal_periods(id),
  asset_id          TEXT NOT NULL REFERENCES fixed_assets(id),
  amount            INTEGER NOT NULL,
  journal_entry_id  TEXT NOT NULL REFERENCES journal_entries(id),
  created_at        TEXT NOT NULL,
  PRIMARY KEY (fiscal_period_id, asset_id)
);

-- 決算・申告用の繰越情報（DM-17）
CREATE TABLE closing_carryovers (
  fiscal_period_id         TEXT PRIMARY KEY REFERENCES fiscal_periods(id),
  loss_carryforwards_json  TEXT NOT NULL DEFAULT '[]',
  prior_corporate_tax      INTEGER NOT NULL DEFAULT 0,
  interim_payments_json    TEXT NOT NULL DEFAULT '[]',
  resident_tax_per_capita  INTEGER NOT NULL DEFAULT 70000,
  business_overview_json   TEXT NOT NULL DEFAULT '{}',
  updated_at               TEXT NOT NULL
);

-- 変更履歴（NFR-02）
CREATE TABLE audit_log (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  table_name  TEXT NOT NULL,
  row_id      TEXT NOT NULL,
  action      TEXT NOT NULL CHECK (action IN ('insert','update','void')),
  before_json TEXT,
  after_json  TEXT,
  changed_at  TEXT NOT NULL
);
CREATE INDEX idx_audit_row ON audit_log(table_name, row_id);
