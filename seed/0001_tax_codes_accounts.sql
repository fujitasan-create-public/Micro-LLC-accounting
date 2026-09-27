-- 税区分（DM-05）
-- 経過措置の控除率はここに持たず、取引日から BR-022 で判定する。
INSERT OR IGNORE INTO tax_codes (code, name, kind, rate, invoice_status, sort_order) VALUES
('S10',  '課税売上 10%',                 'taxable_sales',    '0.10', 'not_applicable',             10),
('S08',  '課税売上 8%（軽減）',          'taxable_sales',    '0.08', 'not_applicable',             20),
('SEX',  '非課税売上',                   'exempt_sales',     NULL,   'not_applicable',             30),
('NT',   '対象外（不課税）',             'non_taxable',      NULL,   'not_applicable',             40),
('PEX',  '非課税仕入',                   'non_taxable',      NULL,   'not_applicable',             50),
('P10',  '課税仕入 10%（適格）',         'taxable_purchase', '0.10', 'qualified',                  60),
('P08',  '課税仕入 8%（軽減・適格）',    'taxable_purchase', '0.08', 'qualified',                  70),
('P10N', '課税仕入 10%（経過措置）',     'taxable_purchase', '0.10', 'non_qualified_transitional', 80),
('P08N', '課税仕入 8%（軽減・経過措置）','taxable_purchase', '0.08', 'non_qualified_transitional', 90);

-- 勘定科目（DM-04）
-- 要件の初期データに加え、税抜経理用の「仮払消費税等」「仮受消費税等」と、内訳書（雑益・雑損失）用の「雑損失」を追加している。
INSERT OR IGNORE INTO accounts (code, name, category, statement_section, default_tax_code, requires_counterparty, is_active) VALUES
-- 資産
('100', '現金',               'asset',     '流動資産',             'NT',  0, 1),
('110', '普通預金',           'asset',     '流動資産',             'NT',  0, 1),
('130', '売掛金',             'asset',     '流動資産',             'NT',  1, 1),
('140', '前払費用',           'asset',     '流動資産',             'NT',  0, 1),
('150', '仮払金',             'asset',     '流動資産',             'NT',  1, 1),
('160', '仮払消費税等',       'asset',     '流動資産',             'NT',  0, 1),
('170', '工具器具備品',       'asset',     '有形固定資産',         'P10', 0, 1),
('180', 'ソフトウェア',       'asset',     '無形固定資産',         'P10', 0, 1),
('190', '一括償却資産',       'asset',     '投資その他の資産',     'P10', 0, 1),
-- 負債
('200', '未払金',             'liability', '流動負債',             'NT',  1, 1),
('210', '未払費用',           'liability', '流動負債',             'NT',  0, 1),
('220', '預り金（源泉所得税）','liability','流動負債',             'NT',  0, 1),
('221', '預り金（住民税）',   'liability', '流動負債',             'NT',  0, 1),
('222', '預り金（社会保険料）','liability','流動負債',             'NT',  0, 1),
('230', '未払法人税等',       'liability', '流動負債',             'NT',  0, 1),
('240', '未払消費税等',       'liability', '流動負債',             'NT',  0, 1),
('245', '仮受消費税等',       'liability', '流動負債',             'NT',  0, 1),
('250', '役員借入金',         'liability', '固定負債',             'NT',  0, 1),
-- 純資産
('300', '資本金',             'equity',    '資本金',               'NT',  0, 1),
('310', '繰越利益剰余金',     'equity',    '利益剰余金',           'NT',  0, 1),
-- 収益
('400', '売上高',             'revenue',   '売上高',               'S10', 1, 1),
('410', '受取利息',           'revenue',   '営業外収益',           'SEX', 0, 1),
('420', '雑収入',             'revenue',   '営業外収益',           'S10', 0, 1),
-- 費用
('500', '役員報酬',           'expense',   '販売費及び一般管理費', 'NT',  0, 1),
('510', '法定福利費',         'expense',   '販売費及び一般管理費', 'NT',  0, 1),
('520', '地代家賃',           'expense',   '販売費及び一般管理費', 'P10', 1, 1),
('530', '旅費交通費',         'expense',   '販売費及び一般管理費', 'P10', 0, 1),
('540', '通信費',             'expense',   '販売費及び一般管理費', 'P10', 0, 1),
('550', '消耗品費',           'expense',   '販売費及び一般管理費', 'P10', 0, 1),
('560', '支払手数料',         'expense',   '販売費及び一般管理費', 'P10', 0, 1),
('570', '租税公課',           'expense',   '販売費及び一般管理費', 'NT',  0, 1),
('580', '会議費',             'expense',   '販売費及び一般管理費', 'P10', 0, 1),
('590', '交際費',             'expense',   '販売費及び一般管理費', 'P10', 0, 1),
('600', '新聞図書費',         'expense',   '販売費及び一般管理費', 'P10', 0, 1),
('610', '支払報酬',           'expense',   '販売費及び一般管理費', 'P10', 1, 1),
('620', '減価償却費',         'expense',   '販売費及び一般管理費', 'NT',  0, 1),
('630', '雑費',               'expense',   '販売費及び一般管理費', 'P10', 0, 1),
('690', '雑損失',             'expense',   '営業外費用',           'NT',  0, 1),
-- 税金
('700', '法人税、住民税及び事業税', 'expense', '法人税等',         'NT',  0, 1);

INSERT OR IGNORE INTO withholding_settings (id, special_payment_deadline, updated_at)
VALUES (1, 0, '2026-09-27T00:00:00+09:00');
