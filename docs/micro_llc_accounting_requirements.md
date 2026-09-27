# 要件定義書：マイクロ法人向け最小構成会計ソフト

- 文書バージョン: 1.0
- 作成日: 2026-09-27
- 準拠する制度: 2026年9月時点の日本の税制・会計ルール（令和8年度税制改正を反映）

---

## 0. この文書の読み方（実装担当LLM向け）

- 要件には一意のIDを付けている。`FR-`は機能要件、`DM-`はデータモデル、`BR-`は業務ルール（税務・会計上の判定ロジック）、`NFR-`は非機能要件、`OUT-`は出力帳票を表す。
- 優先度は `MUST`（必須）、`SHOULD`（推奨）、`MAY`（任意）の3段階で示す。
- 税率・控除率・金額しきい値は法改正で変わるため、コードに直書きせず、**適用期間つきの設定テーブル**として保持すること（BR-000）。
- フィールド定義の型は `string`, `int`（円単位の整数）, `decimal`, `date`（YYYY-MM-DD）, `bool`, `enum`, `ref(エンティティ名)`, `file` を使う。
- 金額はすべて円単位の整数で扱い、端数処理の規則は各ルールで明示する。

---

## 1. 前提と対象範囲

### 1.1 利用者と事業の前提

| 項目 | 内容 |
|---|---|
| 法人形態 | 合同会社（持分会社） |
| 役員・従業員 | 代表社員1名のみ。従業員はいない |
| 主な取引 | 経費の支払、借上げ社宅の家賃支払と役員からの徴収、契約企業からの業務報酬の振込入金 |
| 取引頻度 | 月に数件〜数十件程度 |
| 資本金 | 1億円以下（中小法人） |
| 申告 | 青色申告を前提とする |
| 利用者数 | 1名。承認フローは不要 |

### 1.2 スコープ外（実装しない）

- OUT-SCOPE-01: 勤怠管理、給与明細の配信、人事評価などの人事機能
- OUT-SCOPE-02: 部門別会計、プロジェクト別原価計算
- OUT-SCOPE-03: 複数ユーザーの権限管理と承認ワークフロー
- OUT-SCOPE-04: 予算管理、資金繰り予測
- OUT-SCOPE-05: 在庫管理、手形管理
- OUT-SCOPE-06: 法人税申告書の別表・地方税申告書の様式の作成と電子申告。本システムは申告に必要な集計値の出力までとし、申告書の作成はe-Taxや申告ソフトで行う

---

## 2. データモデル

### DM-01 会社設定（Company）　`MUST`

単一レコード。

| フィールド | 型 | 必須 | 説明 |
|---|---|---|---|
| trade_name | string | ○ | 商号 |
| corporate_number | string(13) | ○ | 法人番号 |
| head_office_address | string | ○ | 本店所在地 |
| representative_name | string | ○ | 代表社員名 |
| incorporation_date | date | ○ | 設立日 |
| capital_amount | int | ○ | 資本金の額。中小法人判定、住民税均等割の区分に使う |
| fiscal_year_start_month | int(1-12) | ○ | 期首月 |
| blue_return_approved | bool | ○ | 青色申告の承認の有無 |
| blue_return_effective_from | date | | 承認が有効になる事業年度の開始日 |
| tax_office | string | ○ | 所轄の税務署 |
| prefecture | string | ○ | 都道府県（法人事業税・都道府県民税） |
| municipality | string | ○ | 市区町村（市町村民税、償却資産申告） |
| accounting_tax_method | enum(tax_included, tax_excluded) | ○ | 経理方式（税込か税抜か） |

### DM-02 消費税設定（ConsumptionTaxSetting）　`MUST`

事業年度ごとに1レコード。

| フィールド | 型 | 必須 | 説明 |
|---|---|---|---|
| fiscal_period_id | ref(FiscalPeriod) | ○ | 対象の事業年度 |
| taxable_status | enum(exempt, taxable) | ○ | 免税事業者か課税事業者か |
| invoice_registration_number | string | | インボイス登録番号（T＋13桁） |
| calculation_method | enum(standard, simplified, two_tenths_special) | ○ | 本則課税、簡易課税、2割特例。BR-021を参照 |
| simplified_business_category | enum(1,2,3,4,5,6) | | 簡易課税の事業区分。役務提供（コンサル・IT等）は通常5 |
| interim_filing_required | bool | | 消費税の中間申告が必要か |

### DM-03 会計期間（FiscalPeriod）　`MUST`

| フィールド | 型 | 必須 | 説明 |
|---|---|---|---|
| id | string | ○ | |
| start_date | date | ○ | 期首日 |
| end_date | date | ○ | 期末日 |
| status | enum(open, closing, closed) | ○ | 締め処理後は仕訳の変更を禁止する（NFR-03） |

### DM-04 勘定科目（Account）　`MUST`

| フィールド | 型 | 必須 | 説明 |
|---|---|---|---|
| code | string | ○ | 科目コード |
| name | string | ○ | 科目名 |
| category | enum(asset, liability, equity, revenue, expense) | ○ | 区分 |
| statement_section | string | ○ | 決算書上の表示区分（流動資産、販売費及び一般管理費、営業外収益など） |
| default_tax_code | ref(TaxCode) | ○ | 税区分の初期値 |
| requires_counterparty | bool | ○ | 取引先の入力を必須にするか（内訳書の作成に必要な科目で true） |
| is_active | bool | ○ | |

**初期データ**（ユーザーが追加・非表示にできること）

- 資産: 現金、普通預金、売掛金、前払費用、仮払金、工具器具備品、ソフトウェア、一括償却資産
- 負債: 未払金、未払費用、預り金（源泉所得税）、預り金（住民税）、預り金（社会保険料）、未払法人税等、未払消費税等、役員借入金
- 純資産: 資本金、繰越利益剰余金
- 収益: 売上高、受取利息、雑収入
- 費用: 役員報酬、法定福利費、地代家賃、旅費交通費、通信費、消耗品費、支払手数料、租税公課、会議費、交際費、新聞図書費、支払報酬、減価償却費、雑費
- 税金: 法人税・住民税及び事業税

### DM-05 税区分（TaxCode）　`MUST`

| フィールド | 型 | 必須 | 説明 |
|---|---|---|---|
| code | string | ○ | |
| name | string | ○ | |
| kind | enum(taxable_sales, exempt_sales, non_taxable, taxable_purchase) | ○ | 課税売上、非課税、不課税、課税仕入 |
| rate | decimal | | 0.10 または 0.08 |
| invoice_status | enum(qualified, non_qualified_transitional, not_applicable) | | 仕入のとき、適格請求書があるか、経過措置の対象か |

- 経過措置の控除率はこのテーブルに持たせず、取引日から BR-022 で判定する。

### DM-06 取引先（Counterparty）　`MUST`

| フィールド | 型 | 必須 | 説明 |
|---|---|---|---|
| id | string | ○ | |
| name | string | ○ | 名称 |
| entity_type | enum(corporation, individual) | ○ | 個人への報酬支払時に源泉徴収の警告を出すため（BR-041） |
| invoice_registration_number | string | | インボイス登録番号。未入力なら仕入は経過措置の対象とみなす |
| address | string | | 地代家賃の内訳書に貸主の住所が必要 |
| bank_account | string | | 振込先 |
| is_client | bool | | 報酬の支払元（売上の相手先）か |

### DM-07 口座・支払手段（PaymentAccount）　`MUST`

| フィールド | 型 | 必須 | 説明 |
|---|---|---|---|
| id | string | ○ | |
| type | enum(bank, credit_card, cash, officer_advance) | ○ | officer_advance は役員による立替（役員借入金に紐付く） |
| bank_name | string | | 金融機関名（預貯金の内訳書に必要） |
| branch_name | string | | 支店名 |
| account_kind | string | | 普通・当座など |
| account_number | string | | 口座番号 |
| linked_account_code | ref(Account) | ○ | 対応する勘定科目 |
| csv_import_format | string | | 明細CSVの取込形式 |

### DM-08 仕訳（JournalEntry / JournalLine）　`MUST`

**JournalEntry（仕訳ヘッダ）**

| フィールド | 型 | 必須 | 説明 |
|---|---|---|---|
| id | string | ○ | |
| transaction_date | date | ○ | 取引日。経過措置の控除率の判定にも使う |
| description | string | ○ | 摘要 |
| counterparty_id | ref(Counterparty) | 条件付き | 科目の requires_counterparty が true なら必須 |
| payment_account_id | ref(PaymentAccount) | | 支払元・入金先 |
| attachments | ref(Attachment)[] | | 証憑 |
| entertainment_detail | object | | 交際費の場合に入力。{ participants: string, headcount: int, is_food_and_drink: bool } |
| source | enum(manual, csv_import, recurring, closing_adjustment) | ○ | 入力元 |
| created_at / updated_at | datetime | ○ | 訂正・削除の履歴（NFR-02） |

**JournalLine（仕訳明細）**

| フィールド | 型 | 必須 | 説明 |
|---|---|---|---|
| side | enum(debit, credit) | ○ | 借方か貸方か |
| account_code | ref(Account) | ○ | |
| amount | int | ○ | 金額 |
| tax_code | ref(TaxCode) | ○ | 科目の初期値から変更できる |
| tax_amount | int | ○ | 消費税額（自動計算し、手修正可） |

- 制約: 1仕訳の借方合計と貸方合計は必ず一致すること。

### DM-09 証憑（Attachment）　`MUST`

| フィールド | 型 | 必須 | 説明 |
|---|---|---|---|
| id | string | ○ | |
| file | file | ○ | PDF・画像・受信データそのもの |
| received_date | date | ○ | 受領日 |
| transaction_date | date | ○ | 取引年月日（検索項目） |
| amount | int | ○ | 取引金額（検索項目） |
| counterparty_name | string | ○ | 取引先（検索項目） |
| receipt_channel | enum(electronic, paper_scanned, paper) | ○ | 電子取引か紙か |
| hash | string | ○ | 改ざん検知用のハッシュ値 |

### DM-10 売上請求（SalesInvoice）　`SHOULD`

| フィールド | 型 | 必須 | 説明 |
|---|---|---|---|
| id / invoice_number | string | ○ | 請求書番号 |
| client_id | ref(Counterparty) | ○ | 請求先 |
| issue_date | date | ○ | 発行日 |
| service_period | string | ○ | 取引年月日または役務提供期間 |
| lines | {description, amount, tax_rate}[] | ○ | 明細 |
| due_date | date | ○ | 支払期日 |
| status | enum(issued, partially_paid, paid) | ○ | 入金状況 |
| received_amount | int | | 入金額 |
| bank_fee_deducted | int | | 先方負担にならず差し引かれた振込手数料 |

### DM-11 役員（Officer）と役員報酬（OfficerCompensation）　`MUST`

**Officer**

| フィールド | 型 | 必須 | 説明 |
|---|---|---|---|
| name | string | ○ | 氏名 |
| address | string | ○ | 住所 |
| my_number_stored_externally | bool | | マイナンバーは本システムに保存しない（NFR-05） |
| dependents | object[] | | 扶養親族（源泉徴収税額表の甲欄の扶養人数の計算に使う） |

**OfficerCompensation（改定ごとに1レコード）**

| フィールド | 型 | 必須 | 説明 |
|---|---|---|---|
| effective_from | date | ○ | 適用開始月 |
| monthly_amount | int | ○ | 月額報酬 |
| payment_day | int | ○ | 支給日 |
| resolution_date | date | ○ | 社員総会での決定日（議事録の日付） |
| revision_reason | enum(regular, performance_deterioration, other) | ○ | 改定理由。BR-031 の判定に使う |

### DM-12 給与支給実績（PayrollRecord）　`MUST`

月ごとに1レコード。

| フィールド | 型 | 必須 | 説明 |
|---|---|---|---|
| pay_date | date | ○ | 支給日 |
| gross_amount | int | ○ | 総支給額 |
| health_insurance_employee | int | ○ | 健康保険料（本人負担） |
| pension_employee | int | ○ | 厚生年金保険料（本人負担） |
| health_insurance_employer | int | ○ | 健康保険料（会社負担） |
| pension_employer | int | ○ | 厚生年金保険料（会社負担） |
| standard_monthly_remuneration | int | ○ | 標準報酬月額 |
| withholding_income_tax | int | ○ | 源泉所得税 |
| resident_tax | int | ○ | 住民税（特別徴収額） |
| company_housing_deduction | int | | 社宅家賃の天引き額 |
| net_amount | int | ○ | 差引支給額（自動計算） |

### DM-13 源泉所得税の設定（WithholdingSetting）　`MUST`

| フィールド | 型 | 必須 | 説明 |
|---|---|---|---|
| special_payment_deadline | bool | ○ | 納期の特例の承認を受けているか |
| payments | {period, amount, paid_date}[] | ○ | 納付履歴 |

### DM-14 年末調整情報（YearEndAdjustment）　`MUST`

暦年ごとに1レコード。

| フィールド | 型 | 必須 | 説明 |
|---|---|---|---|
| year | int | ○ | 対象年 |
| life_insurance_deduction_inputs | object | | 生命保険料控除の元データ |
| earthquake_insurance_premium | int | | 地震保険料 |
| small_business_mutual_aid_premium | int | | 小規模企業共済等掛金（iDeCo含む） |
| social_insurance_paid_personally | int | | 本人が個人で支払った社会保険料（国民年金等） |
| spouse_income | int | | 配偶者の所得 |
| housing_loan_deduction | int | | 住宅ローン控除額 |

### DM-15 借上げ社宅（CompanyHousing）　`MUST`

| フィールド | 型 | 必須 | 説明 |
|---|---|---|---|
| landlord_id | ref(Counterparty) | ○ | 貸主（地代家賃の内訳書に必要） |
| address | string | ○ | 物件の所在地 |
| contract_start / contract_end | date | ○ | 契約期間 |
| monthly_rent | int | ○ | 月額家賃 |
| monthly_common_fee | int | | 共益費・管理費 |
| floor_area_sqm | decimal | ○ | 床面積（㎡） |
| structure | enum(wooden, non_wooden) | ○ | 構造 |
| building_tax_base | int | ○ | 建物の固定資産税の課税標準額 |
| land_tax_base | int | ○ | 土地（敷地）の固定資産税の課税標準額 |
| is_luxury | bool | ○ | いわゆる豪華社宅に当たるか（床面積240㎡超など） |
| market_rent | int | | 豪華社宅の場合の時価 |
| collection_amount | int | ○ | 役員から受け取る月額 |
| collection_method | enum(payroll_deduction, transfer) | ○ | 給与から天引きか振込か |

### DM-16 固定資産（FixedAsset）　`MUST`

| フィールド | 型 | 必須 | 説明 |
|---|---|---|---|
| name | string | ○ | 資産名 |
| asset_category | string | ○ | 種類（器具備品、ソフトウェアなど） |
| acquisition_date | date | ○ | 取得日 |
| service_start_date | date | ○ | 事業に使い始めた日。償却の起点はこちら |
| acquisition_cost | int | ○ | 取得価額（経理方式に応じて税込または税抜） |
| useful_life_years | int | ○ | 法定耐用年数 |
| depreciation_method | enum(straight_line, declining_balance, immediate_small, lump_sum_3y, small_sme_special) | ○ | 償却方法。BR-051 で候補を提示する |
| disposal_date | date | | 除却・売却日 |
| subject_to_depreciable_asset_return | bool | ○ | 償却資産申告の対象か（ソフトウェアなど無形資産は対象外） |

### DM-17 決算・申告用の繰越情報（ClosingCarryover）　`MUST`

事業年度ごとに1レコード。

| フィールド | 型 | 必須 | 説明 |
|---|---|---|---|
| loss_carryforwards | {origin_period, remaining_amount}[] | ○ | 繰越欠損金の発生年度ごとの残高 |
| prior_corporate_tax | int | ○ | 前期の法人税額（中間申告の要否判定に使う） |
| interim_payments | {tax_type, amount, paid_date}[] | | 中間納付の実績 |
| resident_tax_per_capita | int | ○ | 法人住民税の均等割額 |
| business_overview | object | | 法人事業概況説明書の項目（事業内容、経理の方法、使用システムなど） |

---

## 3. 機能要件

### 3.1 初期設定

- FR-01 `MUST` 会社設定（DM-01）、消費税設定（DM-02）、会計期間（DM-03）を初回起動時に入力させる。
- FR-02 `MUST` 勘定科目・税区分の初期データを投入し、ユーザーが追加・非表示・名称変更をできるようにする。
- FR-03 `MUST` 設立初年度の開始残高（資本金の払込など）を入力できる。

### 3.2 日々の取引

- FR-10 `MUST` 仕訳を手入力できる。科目を選ぶと税区分の初期値が自動で入り、変更できる。
- FR-11 `MUST` 借方と貸方が一致しない仕訳は保存できない。
- FR-12 `MUST` 取引先がインボイス登録番号を持たない場合、課税仕入の税区分を自動で経過措置の対象にする（BR-022）。
- FR-13 `SHOULD` 銀行・カードの明細CSVを取り込み、仕訳の候補を作る。摘要や取引先から科目を推定するルールをユーザーが登録できる。
- FR-14 `SHOULD` 毎月の定型仕訳（役員報酬、社宅家賃、社会保険料など）を繰り返し登録できる。
- FR-15 `MUST` 役員が個人で立て替えた支払を、役員借入金を相手科目として記録できる。
- FR-16 `MUST` 証憑ファイルを仕訳に添付し、取引年月日・金額・取引先を入力させる（BR-061）。
- FR-17 `MUST` 交際費の仕訳では参加者・人数・飲食かどうかを入力でき、1人あたり金額を自動計算する（BR-071）。

### 3.3 売上と入金

- FR-20 `SHOULD` 請求書（DM-10）を作成し、発行時に「売掛金／売上高」の仕訳を自動で作る。
- FR-21 `SHOULD` 請求書はインボイスの記載事項（BR-023）を満たすPDFとして出力する。
- FR-22 `MUST` 入金時に売掛金を消し込む。入金額が請求額より少ない場合、差額を振込手数料（支払手数料）として処理できる。

### 3.4 役員報酬・源泉・社会保険

- FR-30 `MUST` 役員報酬の改定履歴（DM-11）を記録し、定期同額給与の要件を満たさない改定に警告を出す（BR-031）。
- FR-31 `MUST` 毎月の給与支給実績（DM-12）から、役員報酬・法定福利費・預り金の仕訳を自動で作る。
- FR-32 `SHOULD` 源泉所得税を源泉徴収税額表（月額表・甲欄）から自動計算する。税額表は年度ごとに差し替えられる設定データとして持つ。
- FR-33 `MUST` 源泉所得税の納付期限を表示する（BR-042）。
- FR-34 `SHOULD` 年末調整の計算を行い、源泉徴収票の記載内容を出力する（OUT-20）。

### 3.5 社宅

- FR-40 `MUST` 借上げ社宅の情報（DM-15）から賃料相当額を自動計算する（BR-081）。
- FR-41 `MUST` 役員から受け取る額が賃料相当額を下回る場合に警告し、差額が役員報酬として課税されることを表示する。
- FR-42 `MUST` 家賃の支払と役員からの徴収を仕訳として作る。住宅の家賃の税区分は非課税とする。

### 3.6 固定資産

- FR-50 `MUST` 固定資産台帳（DM-16）を管理し、期末に減価償却費の仕訳を自動で作る。
- FR-51 `MUST` 取得価額と取得日から、選べる償却方法の候補を提示する（BR-051）。
- FR-52 `MUST` 少額減価償却資産の特例の年間合計額を集計し、上限を超える場合は警告する。

### 3.7 決算

- FR-60 `MUST` 決算整理仕訳（未払費用、前払費用、未払法人税等、未払消費税等）を入力する画面を用意する。
- FR-61 `MUST` 消費税の納付額を、設定された計算方式（DM-02）で計算する。
- FR-62 `SHOULD` 法人税・地方税の概算額を計算する。概算であることを画面に明示する。
- FR-63 `MUST` 期末の締め処理を行い、締めた期間の仕訳を変更できないようにする。翌期への残高の繰越を自動で行う。
- FR-64 `MUST` 決算書と申告用の集計資料（第4章）を出力する。

### 3.8 検索とデータ保全

- FR-70 `MUST` 仕訳と証憑を、取引年月日（範囲）・金額（範囲）・取引先で検索できる。2つ以上の条件を組み合わせて検索できる。
- FR-71 `MUST` 全データ（仕訳、マスタ、証憑）をCSVとファイル一式でエクスポートできる。

---

## 4. 出力帳票

| ID | 帳票 | 優先度 | 用途 |
|---|---|---|---|
| OUT-01 | 仕訳帳 | MUST | 青色申告の必須帳簿 |
| OUT-02 | 総勘定元帳 | MUST | 青色申告の必須帳簿 |
| OUT-03 | 現金出納帳・預金出納帳 | MUST | 補助簿 |
| OUT-04 | 売掛帳 | SHOULD | 補助簿 |
| OUT-05 | 固定資産台帳 | MUST | 補助簿、償却資産申告の元データ |
| OUT-06 | 試算表（月次・年次） | MUST | 残高確認 |
| OUT-10 | 貸借対照表 | MUST | 決算書 |
| OUT-11 | 損益計算書 | MUST | 決算書 |
| OUT-12 | 社員資本等変動計算書 | MUST | 決算書（合同会社の株主資本等変動計算書に相当） |
| OUT-13 | 個別注記表 | MUST | 決算書 |
| OUT-14 | 勘定科目内訳明細書の元データ | MUST | 預貯金、売掛金、仮払金、未払金、役員借入金、役員報酬手当等及び人件費、地代家賃、雑益・雑損失 |
| OUT-15 | 法人事業概況説明書の元データ | SHOULD | 月別売上など |
| OUT-16 | 消費税の集計表 | MUST | 税率別・税区分別・経過措置控除率別の集計 |
| OUT-17 | 償却資産申告の一覧 | SHOULD | 市区町村への申告（毎年1月31日期限） |
| OUT-20 | 源泉徴収票 | SHOULD | 役員への交付、税務署への提出 |
| OUT-21 | 給与支払報告書の元データ | SHOULD | 市区町村への提出（毎年1月31日期限） |
| OUT-22 | 源泉所得税の納付書の記載事項 | SHOULD | 納付時の転記用 |

---

## 5. 業務ルール

### BR-000 設定値の持ち方

- 税率、控除率、金額しきい値、適用期限は、`{key, value, effective_from, effective_to}` の形の設定テーブルに持つ。
- 判定に使う日付（取引日、取得日、課税期間の末日など）を各ルールで明示し、その日付で有効な値を使う。

### BR-010 中小法人の判定

- 資本金1億円以下で、大法人に完全支配されていない法人を中小法人とする。
- 中小法人は、法人税の軽減税率、少額減価償却資産の特例（BR-051）、交際費の定額控除限度額の特例を使える。

### BR-020 消費税の課税判定の補助

- 資本金1,000万円未満で設立した法人は、原則として設立から2期は免税事業者となる。ただし次の場合は課税事業者になる。
  - インボイス登録をした場合
  - 特定期間（前期の上半期）の課税売上高と給与支払額がともに1,000万円を超えた場合
- システムは判定の補助表示にとどめ、最終的な区分はユーザーが DM-02 で設定する。

### BR-021 2割特例の適用可否

- 法人の2割特例は、**2026年9月30日を含む課税期間**までしか使えない。
- 課税期間の開始日が2026年10月1日以後の場合、calculation_method に `two_tenths_special` を選べないようにする。
- 個人事業者向けの3割特例は法人には存在しないため、選択肢に含めない。

### BR-022 インボイスのない仕入の経過措置

- 取引先にインボイス登録番号がない課税仕入は、仕入税額に次の控除率を掛けた額だけ控除できる。判定日は**取引日（引渡し・役務提供の日）**とする。

| 取引日 | 控除率 |
|---|---|
| 2023-10-01 〜 2026-09-30 | 80% |
| 2026-10-01 〜 2028-09-30 | 70% |
| 2028-10-01 〜 2030-09-30 | 50% |
| 2030-10-01 〜 2031-09-30 | 30% |
| 2031-10-01 以降 | 0%（控除不可） |

### BR-023 インボイスの記載事項

発行する請求書には次の事項を必ず含める。

1. 発行者の名称と登録番号
2. 取引年月日
3. 取引内容（軽減税率対象品目はその旨）
4. 税率ごとに区分した対価の合計額と適用税率
5. 税率ごとに区分した消費税額（端数処理は1請求書につき税率ごとに1回）
6. 受け取る側の名称

### BR-031 定期同額給与のチェック

- 役員報酬は、支給時期が1か月以下の一定の期間ごとで、各支給時期の支給額が同額である場合に損金算入できる。
- 次の場合に警告を出す。
  - 同一事業年度内で monthly_amount が変わり、かつ effective_from が期首から3か月を超えた日で、revision_reason が `regular` の場合
  - 実際の支給額（DM-12 の gross_amount）が、その月に有効な monthly_amount と異なる場合

### BR-041 個人への報酬支払時の源泉徴収

- 支払報酬の科目で、取引先の entity_type が `individual`（税理士・デザイナーなど）の場合、源泉徴収が必要な可能性を警告する。
- 税率は、支払額100万円以下の部分が10.21%、100万円を超える部分が20.42%。
- 法人から受け取る報酬には、原則として源泉徴収はされない。

### BR-042 源泉所得税の納付期限

- 納期の特例あり：1月〜6月支払分は7月10日、7月〜12月支払分は翌年1月20日が期限。給与の支払人数が常時10人未満であることが要件。
- 納期の特例なし：支払月の翌月10日が期限。
- 期限が土日祝日にあたる場合は翌営業日とする。

### BR-051 固定資産の償却方法の候補

取得価額（経理方式に応じて税込または税抜）と取得日から、選べる方法を提示する。

| 取得価額 | 選べる方法 |
|---|---|
| 10万円未満 | 取得年度に全額費用化（immediate_small） |
| 20万円未満 | 上記に加え、一括償却資産として3年均等償却（lump_sum_3y） |
| 30万円未満（2026-03-31以前の取得）／40万円未満（2026-04-01以後の取得） | 上記に加え、中小企業者等の少額減価償却資産の特例（small_sme_special） |
| 上記以上 | 通常の減価償却（straight_line または declining_balance） |

- small_sme_special の条件
  - 青色申告の中小企業者等であること（常時使用する従業員数400人以下）
  - 1事業年度の合計取得価額が300万円まで。事業年度が1年未満の場合は月数で按分する
  - 適用期限は2029年3月31日までに取得したもの
- 減価償却の開始日は service_start_date とし、月割りで計算する。

### BR-061 電子取引データの保存

- 電子で受け取った請求書・領収書などは、電子データのまま保存する（紙に印刷しての保存は不可）。
- 保存時に取引年月日・金額・取引先を入力させ、FR-70 で検索できるようにする。
- 改ざん防止措置として、訂正・削除の履歴を残す（NFR-02）。
- 参考：基準期間の売上高が5,000万円以下で、税務調査でデータのダウンロードの求めに応じる場合は検索要件が不要になるが、本システムは検索機能を常に提供する。

### BR-071 交際費の判定補助

- 飲食費で、1人あたりの金額が10,000円以下（社内飲食を除く）のものは交際費から除外できる。
- 除外するには、飲食の年月日、参加者の氏名・関係、人数、金額、店名を記録する必要がある。
- 中小法人は、交際費のうち年800万円までを損金算入できる（接待飲食費の50%損金算入との選択）。

### BR-081 借上げ社宅の賃料相当額

以下を月額で計算する。

1. 小規模住宅の判定
   - 木造：床面積132㎡以下
   - 非木造：床面積99㎡以下
2. 小規模住宅の賃料相当額

   ```
   賃料相当額 = 建物の課税標準額 × 0.2%
             + 12円 × 床面積(㎡) ÷ 3.3
             + 土地の課税標準額 × 0.22%
   ```

3. 小規模住宅でない場合の賃料相当額

   ```
   賃料相当額 = max(
       (建物の課税標準額 × 12%（非木造）または 10%（木造） + 土地の課税標準額 × 6%) ÷ 12,
       月額家賃 × 50%
   )
   ```

4. 豪華社宅（is_luxury = true）の場合は market_rent を賃料相当額とする。
5. collection_amount < 賃料相当額 の場合、差額を役員への給与として扱うよう警告する（FR-41）。

### BR-091 法人税等の概算（FR-62）

- 法人税：中小法人は所得のうち年800万円以下の部分に軽減税率、超える部分に本則税率を適用する。
- 防衛特別法人税：2026年4月1日以後に開始する事業年度から、法人税額から基礎控除500万円を差し引いた額に4%を課す。
- 地方法人税、法人事業税、特別法人事業税、法人住民税（法人税割・均等割）を加算する。
- 均等割は赤字でも発生する（DM-17 の resident_tax_per_capita を使う）。
- 繰越欠損金は古い年度のものから順に控除する。中小法人は所得の全額まで控除できる。
- 税率は都道府県・市区町村ごとに異なるため、BR-000 の設定テーブルでユーザーが入力・更新できるようにする。

### BR-092 中間申告

- 前期の法人税額が20万円を超える場合、法人税の中間申告が必要であることを表示する。

---

## 6. 非機能要件

- NFR-01 `MUST` 帳簿と証憑は、事業年度の確定申告期限の翌日から7年間保存する。欠損金が生じた年度のものは10年間保存する。保存期間内のデータは削除できないようにする。
- NFR-02 `MUST` 仕訳と証憑の訂正・削除の履歴（変更前の値、変更日時）を残す。
- NFR-03 `MUST` 締めた会計期間（status = closed）の仕訳は変更できない。訂正は当期の修正仕訳で行う。
- NFR-04 `MUST` 定期的なバックアップと、FR-71 のエクスポートで別環境に復元できること。
- NFR-05 `MUST` マイナンバーは本システムに保存しない。
- NFR-06 `SHOULD` 利用者は1名のため、認証は単一ユーザーで足りる。ただし証憑と給与データを含むため、保存データは暗号化する。
- NFR-07 `SHOULD` 税制改正に対応できるよう、税率・控除率・しきい値・税額表を設定データとして差し替えられること（BR-000）。

---

## 7. 年間の期限一覧（通知機能用）　`SHOULD`

| 時期 | 内容 | 関連 |
|---|---|---|
| 毎月10日 | 源泉所得税の納付（納期の特例なしの場合） | BR-042 |
| 7月10日 | 源泉所得税の納付（1〜6月分、納期の特例ありの場合） | BR-042 |
| 1月20日 | 源泉所得税の納付（7〜12月分、納期の特例ありの場合） | BR-042 |
| 12月 | 年末調整 | FR-34 |
| 1月31日 | 法定調書合計表・源泉徴収票の提出、給与支払報告書の提出、償却資産申告 | OUT-17, OUT-20, OUT-21 |
| 期末から2か月以内 | 法人税・地方税・消費税の確定申告と納付 | FR-64 |
| 期首から6か月経過後2か月以内 | 中間申告（必要な場合） | BR-092 |
| 期首から3か月以内 | 役員報酬の改定期限 | BR-031 |
