-- Migration number: 0002  整合性トリガーと変更履歴（設計書 5.3、NFR-01〜03）
-- 【要検証】D1 でトリガーが動作しない場合に備え、同じ制約を repositories/ 層でも実施している。

------------------------------------------------------------------
-- 締め済み期間への変更の拒否（NFR-03）
------------------------------------------------------------------
CREATE TRIGGER trg_je_closed_period_insert
BEFORE INSERT ON journal_entries
WHEN (SELECT status FROM fiscal_periods WHERE id = NEW.fiscal_period_id) = 'closed'
BEGIN
  SELECT RAISE(ABORT, 'fiscal period is closed');
END;

CREATE TRIGGER trg_je_closed_period_update
BEFORE UPDATE ON journal_entries
WHEN (SELECT status FROM fiscal_periods WHERE id = OLD.fiscal_period_id) = 'closed'
BEGIN
  SELECT RAISE(ABORT, 'fiscal period is closed');
END;

CREATE TRIGGER trg_jl_closed_period_insert
BEFORE INSERT ON journal_lines
WHEN (SELECT fp.status FROM journal_entries je JOIN fiscal_periods fp ON fp.id = je.fiscal_period_id
      WHERE je.id = NEW.entry_id) = 'closed'
BEGIN
  SELECT RAISE(ABORT, 'fiscal period is closed');
END;

CREATE TRIGGER trg_jl_closed_period_update
BEFORE UPDATE ON journal_lines
WHEN (SELECT fp.status FROM journal_entries je JOIN fiscal_periods fp ON fp.id = je.fiscal_period_id
      WHERE je.id = OLD.entry_id) = 'closed'
BEGIN
  SELECT RAISE(ABORT, 'fiscal period is closed');
END;

------------------------------------------------------------------
-- 物理削除の禁止（NFR-01）
------------------------------------------------------------------
CREATE TRIGGER trg_je_no_delete BEFORE DELETE ON journal_entries
BEGIN
  SELECT RAISE(ABORT, 'physical delete is not allowed; use voided_at');
END;

CREATE TRIGGER trg_jl_no_delete BEFORE DELETE ON journal_lines
BEGIN
  SELECT RAISE(ABORT, 'physical delete is not allowed; use voided_at');
END;

CREATE TRIGGER trg_att_no_delete BEFORE DELETE ON attachments
BEGIN
  SELECT RAISE(ABORT, 'physical delete is not allowed; use voided_at');
END;

CREATE TRIGGER trg_ja_no_delete BEFORE DELETE ON journal_attachments
BEGIN
  SELECT RAISE(ABORT, 'physical delete is not allowed');
END;

-- 証憑のハッシュ値・保存先は変更不可（改ざん防止、BR-061）
CREATE TRIGGER trg_att_immutable_file BEFORE UPDATE OF r2_key, sha256, size_bytes ON attachments
BEGIN
  SELECT RAISE(ABORT, 'attachment file is immutable');
END;

------------------------------------------------------------------
-- 変更履歴（NFR-02）
------------------------------------------------------------------
CREATE TRIGGER trg_audit_je_insert AFTER INSERT ON journal_entries
BEGIN
  INSERT INTO audit_log (table_name, row_id, action, before_json, after_json, changed_at)
  VALUES ('journal_entries', NEW.id, 'insert', NULL,
    json_object('fiscal_period_id', NEW.fiscal_period_id, 'transaction_date', NEW.transaction_date,
      'description', NEW.description, 'counterparty_id', NEW.counterparty_id,
      'payment_account_id', NEW.payment_account_id, 'entertainment_json', NEW.entertainment_json,
      'source', NEW.source, 'reverses_entry_id', NEW.reverses_entry_id, 'voided_at', NEW.voided_at),
    NEW.updated_at);
END;

CREATE TRIGGER trg_audit_je_update AFTER UPDATE ON journal_entries
BEGIN
  INSERT INTO audit_log (table_name, row_id, action, before_json, after_json, changed_at)
  VALUES ('journal_entries', NEW.id,
    CASE WHEN OLD.voided_at IS NULL AND NEW.voided_at IS NOT NULL THEN 'void' ELSE 'update' END,
    json_object('transaction_date', OLD.transaction_date, 'description', OLD.description,
      'counterparty_id', OLD.counterparty_id, 'payment_account_id', OLD.payment_account_id,
      'entertainment_json', OLD.entertainment_json, 'voided_at', OLD.voided_at, 'updated_at', OLD.updated_at),
    json_object('transaction_date', NEW.transaction_date, 'description', NEW.description,
      'counterparty_id', NEW.counterparty_id, 'payment_account_id', NEW.payment_account_id,
      'entertainment_json', NEW.entertainment_json, 'voided_at', NEW.voided_at, 'updated_at', NEW.updated_at),
    NEW.updated_at);
END;

CREATE TRIGGER trg_audit_jl_insert AFTER INSERT ON journal_lines
BEGIN
  INSERT INTO audit_log (table_name, row_id, action, before_json, after_json, changed_at)
  VALUES ('journal_lines', NEW.id, 'insert', NULL,
    json_object('entry_id', NEW.entry_id, 'line_no', NEW.line_no, 'side', NEW.side,
      'account_code', NEW.account_code, 'amount', NEW.amount, 'tax_code', NEW.tax_code,
      'tax_amount', NEW.tax_amount, 'deductible_rate_pct', NEW.deductible_rate_pct),
    strftime('%Y-%m-%dT%H:%M:%S+09:00', 'now', '+9 hours'));
END;

CREATE TRIGGER trg_audit_jl_update AFTER UPDATE ON journal_lines
BEGIN
  INSERT INTO audit_log (table_name, row_id, action, before_json, after_json, changed_at)
  VALUES ('journal_lines', NEW.id, 'update',
    json_object('side', OLD.side, 'account_code', OLD.account_code, 'amount', OLD.amount,
      'tax_code', OLD.tax_code, 'tax_amount', OLD.tax_amount),
    json_object('side', NEW.side, 'account_code', NEW.account_code, 'amount', NEW.amount,
      'tax_code', NEW.tax_code, 'tax_amount', NEW.tax_amount),
    strftime('%Y-%m-%dT%H:%M:%S+09:00', 'now', '+9 hours'));
END;

CREATE TRIGGER trg_audit_att_insert AFTER INSERT ON attachments
BEGIN
  INSERT INTO audit_log (table_name, row_id, action, before_json, after_json, changed_at)
  VALUES ('attachments', NEW.id, 'insert', NULL,
    json_object('r2_key', NEW.r2_key, 'sha256', NEW.sha256, 'received_date', NEW.received_date,
      'transaction_date', NEW.transaction_date, 'amount', NEW.amount,
      'counterparty_name', NEW.counterparty_name, 'receipt_channel', NEW.receipt_channel),
    NEW.created_at);
END;

CREATE TRIGGER trg_audit_att_update AFTER UPDATE ON attachments
BEGIN
  INSERT INTO audit_log (table_name, row_id, action, before_json, after_json, changed_at)
  VALUES ('attachments', NEW.id,
    CASE WHEN OLD.voided_at IS NULL AND NEW.voided_at IS NOT NULL THEN 'void' ELSE 'update' END,
    json_object('received_date', OLD.received_date, 'transaction_date', OLD.transaction_date,
      'amount', OLD.amount, 'counterparty_name', OLD.counterparty_name,
      'receipt_channel', OLD.receipt_channel, 'voided_at', OLD.voided_at),
    json_object('received_date', NEW.received_date, 'transaction_date', NEW.transaction_date,
      'amount', NEW.amount, 'counterparty_name', NEW.counterparty_name,
      'receipt_channel', NEW.receipt_channel, 'voided_at', NEW.voided_at),
    NEW.updated_at);
END;

-- マスタ・給与・資産などは更新の前後を丸ごと JSON で記録する
CREATE TRIGGER trg_audit_cp_update AFTER UPDATE ON counterparties
BEGIN
  INSERT INTO audit_log (table_name, row_id, action, before_json, after_json, changed_at)
  VALUES ('counterparties', NEW.id, 'update',
    json_object('name', OLD.name, 'entity_type', OLD.entity_type,
      'invoice_registration_number', OLD.invoice_registration_number, 'address', OLD.address,
      'bank_account', OLD.bank_account, 'is_client', OLD.is_client),
    json_object('name', NEW.name, 'entity_type', NEW.entity_type,
      'invoice_registration_number', NEW.invoice_registration_number, 'address', NEW.address,
      'bank_account', NEW.bank_account, 'is_client', NEW.is_client),
    NEW.updated_at);
END;

CREATE TRIGGER trg_audit_payroll_insert AFTER INSERT ON payroll_records
BEGIN
  INSERT INTO audit_log (table_name, row_id, action, before_json, after_json, changed_at)
  VALUES ('payroll_records', NEW.id, 'insert', NULL,
    json_object('pay_date', NEW.pay_date, 'gross_amount', NEW.gross_amount,
      'withholding_income_tax', NEW.withholding_income_tax, 'net_amount', NEW.net_amount),
    NEW.created_at);
END;

CREATE TRIGGER trg_audit_payroll_update AFTER UPDATE ON payroll_records
BEGIN
  INSERT INTO audit_log (table_name, row_id, action, before_json, after_json, changed_at)
  VALUES ('payroll_records', NEW.id,
    CASE WHEN OLD.voided_at IS NULL AND NEW.voided_at IS NOT NULL THEN 'void' ELSE 'update' END,
    json_object('pay_date', OLD.pay_date, 'gross_amount', OLD.gross_amount, 'voided_at', OLD.voided_at),
    json_object('pay_date', NEW.pay_date, 'gross_amount', NEW.gross_amount, 'voided_at', NEW.voided_at),
    NEW.updated_at);
END;

CREATE TRIGGER trg_audit_fa_update AFTER UPDATE ON fixed_assets
BEGIN
  INSERT INTO audit_log (table_name, row_id, action, before_json, after_json, changed_at)
  VALUES ('fixed_assets', NEW.id, 'update',
    json_object('name', OLD.name, 'acquisition_cost', OLD.acquisition_cost,
      'depreciation_method', OLD.depreciation_method, 'disposal_date', OLD.disposal_date),
    json_object('name', NEW.name, 'acquisition_cost', NEW.acquisition_cost,
      'depreciation_method', NEW.depreciation_method, 'disposal_date', NEW.disposal_date),
    NEW.updated_at);
END;

CREATE TRIGGER trg_audit_housing_update AFTER UPDATE ON company_housings
BEGIN
  INSERT INTO audit_log (table_name, row_id, action, before_json, after_json, changed_at)
  VALUES ('company_housings', NEW.id, 'update',
    json_object('monthly_rent', OLD.monthly_rent, 'collection_amount', OLD.collection_amount,
      'contract_end', OLD.contract_end),
    json_object('monthly_rent', NEW.monthly_rent, 'collection_amount', NEW.collection_amount,
      'contract_end', NEW.contract_end),
    NEW.updated_at);
END;

CREATE TRIGGER trg_audit_company_update AFTER UPDATE ON company
BEGIN
  INSERT INTO audit_log (table_name, row_id, action, before_json, after_json, changed_at)
  VALUES ('company', '1', 'update',
    json_object('trade_name', OLD.trade_name, 'capital_amount', OLD.capital_amount,
      'accounting_tax_method', OLD.accounting_tax_method, 'fiscal_year_start_month', OLD.fiscal_year_start_month),
    json_object('trade_name', NEW.trade_name, 'capital_amount', NEW.capital_amount,
      'accounting_tax_method', NEW.accounting_tax_method, 'fiscal_year_start_month', NEW.fiscal_year_start_month),
    NEW.updated_at);
END;

CREATE TRIGGER trg_audit_si_update AFTER UPDATE ON sales_invoices
BEGIN
  INSERT INTO audit_log (table_name, row_id, action, before_json, after_json, changed_at)
  VALUES ('sales_invoices', NEW.id,
    CASE WHEN OLD.voided_at IS NULL AND NEW.voided_at IS NOT NULL THEN 'void' ELSE 'update' END,
    json_object('status', OLD.status, 'received_amount', OLD.received_amount,
      'bank_fee_deducted', OLD.bank_fee_deducted, 'voided_at', OLD.voided_at),
    json_object('status', NEW.status, 'received_amount', NEW.received_amount,
      'bank_fee_deducted', NEW.bank_fee_deducted, 'voided_at', NEW.voided_at),
    NEW.updated_at);
END;
