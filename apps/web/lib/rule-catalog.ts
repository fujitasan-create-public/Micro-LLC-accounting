/**
 * 税率・基準額（rule_settings）を画面で扱うための定義。
 * 値の内部形式（JSON）を利用者に見せず、日本語の名前・単位つきで表示・入力できるようにする。
 */

export type Kind =
  | "yen" // 円（数値）
  | "pct" // 整数の％（数値。例: 80）
  | "rate" // 小数の率（文字列。例: "0.103" → 10.3%）
  | "numstr" // 数値を文字列で保存（例: 床面積 "132"）
  | "num" // 数値
  | "months"
  | "years"
  | "date"; // "YYYY-MM-DD" 文字列

export type FieldSpec = { key: string; label: string; kind: Kind; nullable?: boolean; unit?: string };

export type Shape =
  | { type: "scalar"; kind: Kind; unit?: string }
  | { type: "object"; fields: FieldSpec[] }
  | { type: "rows"; columns: FieldSpec[]; rowLabel?: string } // 段階的な表（〜以下 など）
  | { type: "map"; entries: { key: string; label: string }[]; kind: Kind };

export type RuleDef = { key: string; group: string; label: string; description: string; shape: Shape };

const upto = (label = "上限（以下）"): FieldSpec => ({ key: "upto", label, kind: "yen", nullable: true });

export const RULES: RuleDef[] = [
  // ---- 消費税 ----
  { key: "invoice_transitional_rate", group: "消費税", label: "インボイスがない仕入の控除割合（経過措置）",
    description: "登録番号のない相手への支払で、消費税を差し引ける割合。取引日で判定します。", shape: { type: "scalar", kind: "pct" } },
  { key: "two_tenths_special_last_period_contains", group: "消費税", label: "2割特例を使える最後の課税期間",
    description: "この日を含む課税期間まで2割特例を選べます。", shape: { type: "scalar", kind: "date" } },
  { key: "two_tenths_special_deduction_pct", group: "消費税", label: "2割特例で差し引く割合",
    description: "売上の消費税のうち、この割合を差し引いた残りを納めます。", shape: { type: "scalar", kind: "pct" } },
  { key: "simplified_deemed_purchase_pct", group: "消費税", label: "簡易課税のみなし仕入率",
    description: "事業区分ごとの割合。コンサル・ITなどの役務提供は通常第5種です。",
    shape: { type: "map", kind: "pct", entries: ["1", "2", "3", "4", "5", "6"].map((k) => ({ key: k, label: `第${k}種` })) } },

  // ---- 法人税・地方税 ----
  { key: "sme_capital_limit", group: "法人税・地方税", label: "中小法人とみなす資本金の上限",
    description: "資本金がこの額以下なら、軽減税率などの中小法人向けの扱いになります。", shape: { type: "scalar", kind: "yen" } },
  { key: "corporate_tax_rate", group: "法人税・地方税", label: "法人税の税率",
    description: "中小法人は、所得のうち上限額までの部分に軽減税率がかかります。事業年度の開始日で判定します。",
    shape: { type: "object", fields: [
      { key: "reduced", label: "軽減税率", kind: "rate" },
      { key: "reduced_threshold", label: "軽減税率がかかる所得の上限", kind: "yen" },
      { key: "standard", label: "本則税率", kind: "rate" },
    ] } },
  { key: "defense_special_corporate_tax", group: "法人税・地方税", label: "防衛特別法人税",
    description: "法人税額から基礎控除を引いた額にかかります。",
    shape: { type: "object", fields: [
      { key: "rate", label: "税率", kind: "rate" },
      { key: "basic_deduction", label: "基礎控除（法人税額から）", kind: "yen" },
    ] } },
  { key: "local_corporate_tax_rate", group: "法人税・地方税", label: "地方法人税の税率",
    description: "法人税額に対する割合です。", shape: { type: "scalar", kind: "rate" } },
  { key: "enterprise_tax_rates", group: "法人税・地方税", label: "法人事業税の税率（所得割）",
    description: "所得の段階ごとの税率。都道府県によって異なる場合があるので、本店所在地の税率を確認してください。",
    shape: { type: "rows", columns: [upto("所得の上限（以下）"), { key: "rate", label: "税率", kind: "rate" }] } },
  { key: "special_enterprise_tax_rate", group: "法人税・地方税", label: "特別法人事業税の税率",
    description: "法人事業税額（標準税率で計算した額）に対する割合です。", shape: { type: "scalar", kind: "rate" } },
  { key: "resident_tax_corporate_rate", group: "法人税・地方税", label: "法人住民税（法人税割）の税率",
    description: "都道府県分と市区町村分の合計。自治体によって異なるので確認してください。均等割の額は「決算・締め」の繰越情報で設定します。",
    shape: { type: "scalar", kind: "rate" } },
  { key: "interim_filing_threshold", group: "法人税・地方税", label: "中間申告が必要になる前期の法人税額",
    description: "前期の法人税額がこの額を超えると、中間申告が必要です。", shape: { type: "scalar", kind: "yen" } },

  // ---- 固定資産 ----
  { key: "small_asset_immediate_limit", group: "固定資産", label: "買った年に全額経費にできる金額（未満）",
    description: "取得価額がこの額未満なら、買った年に全額を経費にできます。", shape: { type: "scalar", kind: "yen" } },
  { key: "small_asset_lump_sum_limit", group: "固定資産", label: "3年で均等に経費にできる金額（未満）",
    description: "取得価額がこの額未満なら、一括償却資産として3年で均等に経費にできます。", shape: { type: "scalar", kind: "yen" } },
  { key: "small_asset_sme_limit", group: "固定資産", label: "中小企業の少額資産の特例の金額（未満）",
    description: "青色申告の中小法人は、この額未満の資産を買った年に全額経費にできます。取得日で判定します。", shape: { type: "scalar", kind: "yen" } },
  { key: "small_asset_sme_annual_cap", group: "固定資産", label: "中小企業の少額資産の特例の年間上限",
    description: "1事業年度に特例を使える合計額。事業年度が1年未満なら月数で按分します。", shape: { type: "scalar", kind: "yen" } },

  // ---- 交際費 ----
  { key: "entertainment_food_per_person_limit", group: "交際費", label: "交際費から除ける飲食費（1人あたり）",
    description: "1人あたりこの額以下の飲食費は、記録を残せば交際費から除けます。", shape: { type: "scalar", kind: "yen" } },
  { key: "entertainment_sme_fixed_limit", group: "交際費", label: "中小法人が経費にできる交際費の年間上限",
    description: "", shape: { type: "scalar", kind: "yen" } },

  // ---- 源泉所得税・年末調整 ----
  { key: "withholding_individual_fee", group: "源泉所得税・年末調整", label: "個人への報酬の源泉徴収税率",
    description: "税理士・デザイナーなど個人に報酬を払うときの税率です。",
    shape: { type: "object", fields: [
      { key: "threshold", label: "低い税率がかかる支払額の上限", kind: "yen" },
      { key: "rate_low", label: "上限までの税率", kind: "rate" },
      { key: "rate_high", label: "上限を超える部分の税率", kind: "rate" },
    ] } },
  { key: "employment_income_deduction", group: "源泉所得税・年末調整", label: "給与所得控除",
    description: "給与の収入金額に応じて差し引く額。「定額」が空欄の段は「収入×割合＋加算額」で計算します。",
    shape: { type: "rows", columns: [upto("収入の上限（以下）"), { key: "fixed", label: "定額", kind: "yen", nullable: true },
      { key: "rate", label: "割合", kind: "rate", nullable: true }, { key: "add", label: "加算額", kind: "yen", nullable: true }] } },
  { key: "basic_deduction", group: "源泉所得税・年末調整", label: "基礎控除",
    description: "合計所得金額に応じた控除額です。",
    shape: { type: "rows", columns: [upto("所得の上限（以下）"), { key: "amount", label: "控除額", kind: "yen" }] } },
  { key: "income_tax_brackets", group: "源泉所得税・年末調整", label: "所得税の税率（速算表）",
    description: "課税所得に税率をかけ、控除額を引いて所得税を計算します。",
    shape: { type: "rows", columns: [upto("課税所得の上限（以下）"), { key: "rate", label: "税率", kind: "rate" }, { key: "deduct", label: "控除額", kind: "yen" }] } },
  { key: "reconstruction_tax_rate", group: "源泉所得税・年末調整", label: "復興特別所得税の税率",
    description: "所得税額に対する割合です。", shape: { type: "scalar", kind: "rate" } },
  { key: "dependent_deductions", group: "源泉所得税・年末調整", label: "配偶者控除・扶養控除",
    description: "",
    shape: { type: "object", fields: [
      { key: "general", label: "一般の扶養親族", kind: "yen" },
      { key: "specific", label: "特定扶養親族（19〜22歳）", kind: "yen" },
      { key: "elderly", label: "老人扶養親族", kind: "yen" },
      { key: "elderly_cohabiting", label: "同居老親等", kind: "yen" },
      { key: "spouse", label: "配偶者控除", kind: "yen" },
      { key: "spouse_income_limit", label: "配偶者の所得要件（以下）", kind: "yen" },
      { key: "dependent_income_limit", label: "扶養親族の所得要件（以下）", kind: "yen" },
      { key: "taxpayer_income_limit_for_spouse", label: "配偶者控除を受けられる本人の所得（以下）", kind: "yen" },
    ] } },
  { key: "earthquake_insurance_deduction_cap", group: "源泉所得税・年末調整", label: "地震保険料控除の上限",
    description: "", shape: { type: "scalar", kind: "yen" } },

  // ---- 役員報酬・社宅 ----
  { key: "officer_comp_revision_months", group: "役員報酬・社宅", label: "役員報酬を改定できる期間（期首から）",
    description: "この期間を過ぎた改定は、定期同額給与に当たらない可能性があるとして注意を出します。", shape: { type: "scalar", kind: "months" } },
  { key: "housing_small_area_limit_sqm", group: "役員報酬・社宅", label: "小規模住宅とみなす床面積（以下）",
    description: "借上げ社宅の賃料相当額の計算方法が変わる基準です。",
    shape: { type: "object", fields: [
      { key: "wooden", label: "木造", kind: "numstr", unit: "㎡" },
      { key: "non_wooden", label: "木造以外", kind: "numstr", unit: "㎡" },
    ] } },
  { key: "housing_small_formula", group: "役員報酬・社宅", label: "賃料相当額の計算（小規模住宅）",
    description: "建物の課税標準額×割合 ＋ 1㎡あたりの額×床面積÷3.3 ＋ 土地の課税標準額×割合",
    shape: { type: "object", fields: [
      { key: "building_rate", label: "建物の課税標準額に対する割合", kind: "rate" },
      { key: "per_sqm_yen", label: "床面積に対する額", kind: "numstr", unit: "円" },
      { key: "sqm_divisor", label: "床面積を割る数", kind: "numstr" },
      { key: "land_rate", label: "土地の課税標準額に対する割合", kind: "rate" },
    ] } },
  { key: "housing_large_formula", group: "役員報酬・社宅", label: "賃料相当額の計算（小規模住宅以外）",
    description: "（建物の課税標準額×割合 ＋ 土地の課税標準額×割合）÷12 と、家賃×割合 の多いほう",
    shape: { type: "object", fields: [
      { key: "building_rate_wooden", label: "建物の割合（木造）", kind: "rate" },
      { key: "building_rate_non_wooden", label: "建物の割合（木造以外）", kind: "rate" },
      { key: "land_rate", label: "土地の割合", kind: "rate" },
      { key: "rent_ratio", label: "家賃に対する割合", kind: "rate" },
    ] } },

  // ---- 保存 ----
  { key: "retention_years", group: "帳簿の保存", label: "帳簿・証憑の保存期間",
    description: "",
    shape: { type: "object", fields: [
      { key: "normal", label: "通常", kind: "years" },
      { key: "loss", label: "赤字（欠損金）の年度", kind: "years" },
    ] } },
];

export const GROUP_ORDER = ["消費税", "法人税・地方税", "固定資産", "交際費", "源泉所得税・年末調整", "役員報酬・社宅", "帳簿の保存"];

/** 小数の文字列の小数点を n 桁動かす（浮動小数点の誤差を避けるため文字列で処理） */
export function shiftDecimal(value: string, n: number): string {
  const neg = value.startsWith("-");
  let s = neg ? value.slice(1) : value;
  if (!/^\d*\.?\d*$/.test(s) || s === "" || s === ".") return value;
  let [int, frac = ""] = s.split(".");
  if (n > 0) {
    frac = frac.padEnd(n, "0");
    int = int + frac.slice(0, n);
    frac = frac.slice(n);
  } else {
    const k = -n;
    int = int.padStart(k + 1, "0");
    frac = int.slice(int.length - k) + frac;
    int = int.slice(0, int.length - k);
  }
  int = int.replace(/^0+(?=\d)/, "");
  frac = frac.replace(/0+$/, "");
  s = frac ? `${int}.${frac}` : int;
  return neg ? `-${s}` : s;
}

/** 保存形式 → 画面表示用の文字列（単位つき） */
export function display(kind: Kind, v: unknown, unit?: string): string {
  if (v === null || v === undefined || v === "") return "―";
  switch (kind) {
    case "yen":
      return `${Number(v).toLocaleString("ja-JP")}円`;
    case "pct":
      return `${v}%`;
    case "rate":
      return `${shiftDecimal(String(v), 2)}%`;
    case "months":
      return `${v}か月`;
    case "years":
      return `${v}年`;
    case "date": {
      const [y, m, d] = String(v).split("-");
      return `${y}年${Number(m)}月${Number(d)}日`;
    }
    default:
      return `${v}${unit ?? ""}`;
  }
}

/** 保存形式 → 入力欄の文字列（単位なし） */
export function toInput(kind: Kind, v: unknown): string {
  if (v === null || v === undefined) return "";
  return kind === "rate" ? shiftDecimal(String(v), 2) : String(v);
}

/** 入力欄の文字列 → 保存形式。空欄は null */
export function fromInput(kind: Kind, s: string): unknown {
  const t = s.trim().replace(/,/g, "");
  if (t === "") return null;
  switch (kind) {
    case "rate":
      return shiftDecimal(t, -2);
    case "numstr":
    case "date":
      return t;
    default:
      return Number(t);
  }
}

export function inputUnit(kind: Kind, unit?: string): string {
  return { yen: "円", pct: "%", rate: "%", months: "か月", years: "年", numstr: unit ?? "", num: unit ?? "", date: "" }[kind];
}
