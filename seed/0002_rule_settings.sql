-- 設定値（BR-000、設計書 8.2）
-- 値は JSON 文字列。判定日（取引日・取得日・課税期間の末日など）で有効な行を使う。
-- 「要確認」と書いたものは、2026年9月時点の制度を前提にした初期値。法改正時は画面「設定値」から行を追加する。
INSERT OR IGNORE INTO rule_settings (key, value, effective_from, effective_to, note) VALUES
-- BR-022 インボイスのない仕入の経過措置（判定日: 取引日）
('invoice_transitional_rate', '80', '2023-10-01', '2026-09-30', 'BR-022'),
('invoice_transitional_rate', '70', '2026-10-01', '2028-09-30', 'BR-022'),
('invoice_transitional_rate', '50', '2028-10-01', '2030-09-30', 'BR-022'),
('invoice_transitional_rate', '30', '2030-10-01', '2031-09-30', 'BR-022'),
('invoice_transitional_rate', '0',  '2031-10-01', NULL,          'BR-022'),

-- BR-051 固定資産の償却方法（判定日: 取得日）
('small_asset_immediate_limit', '100000', '1998-04-01', NULL, 'BR-051 10万円未満は即時費用化'),
('small_asset_lump_sum_limit',  '200000', '1998-04-01', NULL, 'BR-051 20万円未満は一括償却資産'),
('small_asset_sme_limit', '300000', '2006-04-01', '2026-03-31', 'BR-051 取得日で判定'),
('small_asset_sme_limit', '400000', '2026-04-01', '2029-03-31', 'BR-051 取得日で判定'),
('small_asset_sme_annual_cap', '3000000', '2006-04-01', NULL, 'BR-051'),

-- BR-021 2割特例（課税期間がこの日を含むものまで）
('two_tenths_special_last_period_contains', '"2026-09-30"', '2023-10-01', NULL, 'BR-021'),
('two_tenths_special_deduction_pct', '80', '2023-10-01', NULL, 'BR-021 売上税額の80%を控除'),
-- 簡易課税のみなし仕入率（判定日: 課税期間の末日）
('simplified_deemed_purchase_pct', '{"1":90,"2":80,"3":70,"4":60,"5":50,"6":40}', '2015-04-01', NULL, 'FR-61'),

-- BR-071 交際費
('entertainment_food_per_person_limit', '10000', '2024-04-01', NULL, 'BR-071'),
('entertainment_sme_fixed_limit', '8000000', '2013-04-01', NULL, 'BR-071'),

-- BR-041 個人への報酬の源泉徴収（判定日: 支払日）
('withholding_individual_fee', '{"threshold":1000000,"rate_low":"0.1021","rate_high":"0.2042"}', '2013-01-01', NULL, 'BR-041'),

-- BR-081 借上げ社宅の賃料相当額
('housing_small_area_limit_sqm', '{"wooden":"132","non_wooden":"99"}', '1990-01-01', NULL, 'BR-081'),
('housing_small_formula', '{"building_rate":"0.002","per_sqm_yen":"12","sqm_divisor":"3.3","land_rate":"0.0022"}', '1990-01-01', NULL, 'BR-081'),
('housing_large_formula', '{"building_rate_wooden":"0.10","building_rate_non_wooden":"0.12","land_rate":"0.06","rent_ratio":"0.5"}', '1990-01-01', NULL, 'BR-081'),

-- BR-031 定期同額給与（期首から何か月以内の改定なら可）
('officer_comp_revision_months', '3', '2006-04-01', NULL, 'BR-031'),

-- BR-010 中小法人
('sme_capital_limit', '100000000', '1990-01-01', NULL, 'BR-010'),

-- BR-091 法人税等の概算（判定日: 事業年度の開始日）。地方税率は自治体ごとに異なるため必ず確認して更新すること
('corporate_tax_rate', '{"reduced":"0.15","reduced_threshold":8000000,"standard":"0.232"}', '2019-04-01', '2027-03-31', 'BR-091 中小法人の軽減税率（要確認）'),
('corporate_tax_rate', '{"reduced":"0.19","reduced_threshold":8000000,"standard":"0.232"}', '2027-04-01', NULL, 'BR-091 軽減税率の特例終了後（要確認）'),
('local_corporate_tax_rate', '"0.103"', '2019-10-01', NULL, 'BR-091 地方法人税'),
('defense_special_corporate_tax', '{"rate":"0.04","basic_deduction":5000000}', '2026-04-01', NULL, 'BR-091 防衛特別法人税'),
('enterprise_tax_rates', '[{"upto":4000000,"rate":"0.035"},{"upto":8000000,"rate":"0.053"},{"upto":null,"rate":"0.07"}]', '2019-10-01', NULL, 'BR-091 法人事業税（標準税率、要確認）'),
('special_enterprise_tax_rate', '"0.37"', '2019-10-01', NULL, 'BR-091 特別法人事業税'),
('resident_tax_corporate_rate', '"0.07"', '2019-10-01', NULL, 'BR-091 法人税割（道府県1.0%＋市町村6.0%の標準税率、要確認）'),
('interim_filing_threshold', '200000', '1990-01-01', NULL, 'BR-092'),

-- 年末調整（FR-34、判定日: 対象年の12月31日）要確認
('employment_income_deduction', '[{"upto":1900000,"fixed":650000},{"upto":3600000,"rate":"0.3","add":80000},{"upto":6600000,"rate":"0.2","add":440000},{"upto":8500000,"rate":"0.1","add":1100000},{"upto":null,"fixed":1950000}]', '2025-01-01', NULL, 'FR-34 給与所得控除（要確認）'),
('basic_deduction', '[{"upto":1320000,"amount":950000},{"upto":3360000,"amount":880000},{"upto":4890000,"amount":680000},{"upto":6550000,"amount":630000},{"upto":23500000,"amount":580000},{"upto":24000000,"amount":480000},{"upto":24500000,"amount":320000},{"upto":25000000,"amount":160000},{"upto":null,"amount":0}]', '2025-01-01', NULL, 'FR-34 基礎控除（要確認）'),
('income_tax_brackets', '[{"upto":1950000,"rate":"0.05","deduct":0},{"upto":3300000,"rate":"0.10","deduct":97500},{"upto":6950000,"rate":"0.20","deduct":427500},{"upto":9000000,"rate":"0.23","deduct":636000},{"upto":18000000,"rate":"0.33","deduct":1536000},{"upto":40000000,"rate":"0.40","deduct":2796000},{"upto":null,"rate":"0.45","deduct":4796000}]', '2015-01-01', NULL, 'FR-34 所得税の速算表'),
('reconstruction_tax_rate', '"0.021"', '2013-01-01', '2037-12-31', 'FR-34 復興特別所得税'),
('dependent_deductions', '{"general":380000,"specific":630000,"elderly":480000,"elderly_cohabiting":580000,"spouse":380000,"spouse_income_limit":580000,"dependent_income_limit":580000,"taxpayer_income_limit_for_spouse":9000000}', '2025-01-01', NULL, 'FR-34 扶養・配偶者控除（配偶者特別控除は未対応、要確認）'),
('earthquake_insurance_deduction_cap', '50000', '2007-01-01', NULL, 'FR-34'),

-- NFR-01 保存期間
('retention_years', '{"normal":7,"loss":10}', '2018-04-01', NULL, 'NFR-01');
