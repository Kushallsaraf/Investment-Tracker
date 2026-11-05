export type DataOrigin = "manual" | "demo";

export type PortfolioStatus = {
  data_origin: DataOrigin | null;
  snapshot_count: number;
  latest_snapshot_at: string | null;
};

export type PriceCapabilities = {
  provider: string;
  automatic_refresh_supported: boolean;
  automatic_refresh_seconds: number | null;
};

export type SectorName =
  | "Communication Services"
  | "Consumer Discretionary"
  | "Consumer Staples"
  | "Energy"
  | "Financials"
  | "Health Care"
  | "Industrials"
  | "Information Technology"
  | "Materials"
  | "Real Estate"
  | "Utilities"
  | "Other";

export type DecisionName =
  | "WATCH"
  | "HOLD"
  | "CONSIDER_ADD"
  | "CONSIDER_REDUCE"
  | "EXIT_CANDIDATE";

export type Holding = {
  instrument_id: string;
  position_id: string;
  canonical_symbol: string;
  security_name: string;
  asset_type: "STOCK" | "ETF" | "CASH";
  exchange: string;
  account_name: string;
  quantity: string;
  average_cost: string | null;
  price: string | null;
  market_value: string | null;
  unrealized_gain_loss: string | null;
  portfolio_weight: string | null;
  price_timestamp: string | null;
  price_fetched_at: string | null;
  price_source: string | null;
  price_source_url: string | null;
  quote_status: string | null;
  delay_minutes: number | null;
  price_stale: number | null;
  data_status: string;
  manual_sector: SectorName | null;
  sector_source: string | null;
  sector_source_url: string | null;
  sector_as_of: string | null;
};

export type Portfolio = {
  valuation_snapshot_id: string;
  holding_snapshot_id: string;
  created_at: string;
  snapshot_created_at: string;
  data_origin: DataOrigin;
  total_value: string;
  priced_positions: number;
  total_positions: number;
  position_coverage_pct: string;
  warnings: string[];
  holdings: Holding[];
};

export type HistoryPoint = {
  id: string;
  created_at: string;
  total_value: string;
  position_coverage_pct: string;
};

export type SectorCategory = {
  sector: string;
  market_value: string;
  portfolio_weight: string;
};

export type SectorEvidence = {
  symbol: string;
  issuer: string | null;
  as_of: string | null;
  verified_on: string | null;
  source_url: string | null;
  method: string;
  stale: boolean | null;
  coverage_pct: string;
};

export type SectorAnalysis = {
  valuation_snapshot_id: string;
  calculated_at: string;
  total_value: string;
  covered_value: string;
  coverage_pct: string;
  etf_value: string;
  etf_covered_value: string;
  etf_coverage_pct: string;
  categories: SectorCategory[];
  evidence: SectorEvidence[];
  warnings: string[];
  sector_options: SectorName[];
};

export type AvailabilityMetric = {
  status: string;
  label?: string;
  reason?: string;
  source?: string | null;
  as_of?: string | null;
  coverage_pct?: string;
  [key: string]: unknown;
};

export type Analytics = {
  generated_at: string;
  concentration: AvailabilityMetric;
  performance: AvailabilityMetric & {
    benchmark: string;
    portfolio_return: string | null;
    benchmark_return: string | null;
    difference: string | null;
    periods: Array<{ period: string; portfolio: string | null; benchmark: string | null }>;
    currency: string;
  };
  risk: AvailabilityMetric & {
    benchmark: string;
    annualized_volatility: string | null;
    maximum_drawdown: string | null;
    beta: string | null;
    correlation: string | null;
    measurement_period: string | null;
    observation_frequency: string | null;
    disclaimer: string;
  };
  etf_lookthrough: {
    status: string;
    overlap: Array<{
      pair: string;
      overlap_by_weight: string;
      largest_duplicated_holdings: string[];
      coverage_pct: string;
      issuer_evidence_date: string;
      verification_date: string;
    }>;
    weighted_mer: string | null;
    sector_allocation: SectorCategory[];
    country_allocation: Array<{ country: string; weight: string }>;
    evidence: SectorEvidence[];
    coverage_pct: string;
    warning: string;
  };
};

export type ActivityType =
  | "BUY"
  | "SELL"
  | "DIVIDEND"
  | "DEPOSIT"
  | "WITHDRAWAL"
  | "FEE"
  | "INTEREST"
  | "WITHHOLDING_TAX"
  | "OTHER";

export type Activity = {
  id: string;
  activity_type: ActivityType;
  symbol: string | null;
  trade_date: string;
  quantity: string | null;
  price: string | null;
  fee: string | null;
  cash_amount: string | null;
  note: string;
  data_origin: DataOrigin;
  created_at: string;
};

export type ActivityInput = {
  activity_type: ActivityType;
  trade_date: string;
  symbol?: string | null;
  quantity?: string | null;
  price?: string | null;
  fee?: string | null;
  cash_amount?: string | null;
  note?: string;
};

export type ActivityPayload = {
  activities: Activity[];
  coverage: { start: string | null; end: string | null; count: number };
  warnings: string[];
  source: string;
};

export type IncomePayload = {
  period_start: string;
  period_end: string;
  source: string;
  received: string;
  withholding_tax: string;
  income_by_holding: Array<{ symbol: string; amount: string }>;
  forward_annual_estimate: null;
  portfolio_yield: null;
  upcoming_distributions: [];
  coverage: ActivityPayload["coverage"];
  warnings: string[];
};

export type PositionInput = {
  symbol: string;
  quantity: string;
  average_cost: string | null;
  account_name: string;
};

export type InvestmentProfile = {
  instrument_id: string;
  symbol: string;
  portfolio_role: "CORE" | "DIVERSIFIER" | "INCOME" | "SPECULATIVE" | null;
  thesis_strength: number | null;
  why_owned: string;
  supporting_evidence: string;
  principal_risks: string;
  invalidation_conditions: string;
  maximum_weight: string | null;
  source_links: string[];
  last_reviewed_date: string | null;
  next_review_date: string | null;
  updated_at: string;
};

export type CurrentDecision = {
  instrument_id: string;
  symbol: string;
  decision: DecisionName;
  reason: string;
  decision_date: string;
  review_due_date: string | null;
  updated_at: string;
};

export type ReviewTrigger = {
  id: string;
  instrument_id: string;
  symbol: string;
  trigger_type: string;
  lower_value: string | null;
  upper_value: string | null;
  trigger_date: string | null;
  note: string;
  reason: string;
  expires_at: string | null;
  state: "ACTIVE" | "TRIGGERED" | "EXPIRED" | "DISMISSED";
  created_at: string;
  triggered_at: string | null;
  observed_value: string | null;
  quote_source: string | null;
  quote_timestamp: string | null;
  frozen_holding_snapshot_id: string | null;
  frozen_valuation_snapshot_id: string | null;
};

export type DecisionHistory = {
  id: string;
  instrument_id: string;
  symbol: string;
  decision_date: string;
  previous_decision: DecisionName | null;
  new_decision: DecisionName;
  reason: string;
  claude_disposition: "ACCEPTED" | "REJECTED" | "CONSIDERING" | null;
  review_due_date: string | null;
  created_at: string;
};

export type AIReview = {
  id: string;
  instrument_id: string;
  symbol: string;
  review_date: string;
  evidence_as_of: string | null;
  suggestion: string;
  explanation: string;
  bull_case: string;
  bear_case: string;
  principal_risks: string;
  missing_information: string;
  change_conditions: string;
  source_links: string[];
  claude_model: string | null;
  disposition: "ACCEPTED" | "REJECTED" | "CONSIDERING";
  original_markdown: string;
  created_at: string;
};

export type JournalEntry = {
  holding: Holding;
  profile: InvestmentProfile | null;
  decision: CurrentDecision | null;
  latest_ai_review: AIReview | null;
  active_trigger: ReviewTrigger | null;
};

export type JournalPayload = {
  entries: JournalEntry[];
  decision_history: DecisionHistory[];
  triggers: ReviewTrigger[];
  alerts: Array<{
    id: string;
    trigger_id: string;
    created_at: string;
    message: string;
    symbol: string;
    trigger_type: string;
    state: string;
    exit_plan_id?: string | null;
    exit_plan_reasoning?: string | null;
  }>;
  generated_at: string;
};

export type ClaudePrompt = {
  id: string;
  name: string;
  prompt_text: string;
  is_default: number;
  created_at: string;
  updated_at: string;
};

export type ReviewPrivacy = {
  weights_only: boolean;
  include_quantities: boolean;
  include_dollar_values: boolean;
  include_account_name: boolean;
};

export type ReviewPack = {
  export_id: string | null;
  instrument_id: string;
  symbol: string;
  prompt_id: string;
  trigger_id: string | null;
  privacy: ReviewPrivacy;
  markdown: string;
  holdings_as_of: string | null;
  evidence_as_of: string | null;
  generated_at: string;
};

export type ChartRange = "1M" | "3M" | "6M" | "1Y" | "5Y" | "MAX";

export type PriceBar = {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  adj_close: number;
  volume: number | null;
};

export type QuoteChange = {
  last: number | null;
  change: number | null;
  change_pct: number | null;
  as_of: string | null;
};

export type IndicatorName =
  | "ema20"
  | "ema50"
  | "sma200"
  | "bb_upper"
  | "bb_middle"
  | "bb_lower"
  | "rsi14"
  | "macd"
  | "macd_signal"
  | "macd_histogram";

export type ChartPayload = {
  symbol: string;
  name: string;
  asset_type: "STOCK" | "ETF";
  exchange: string;
  range: ChartRange;
  bars: PriceBar[];
  indicators: Record<IndicatorName, Array<number | null>>;
  quote: QuoteChange;
  source: string;
  fetched_at: string | null;
  stale: boolean;
};

export type Technicals = {
  symbol: string;
  as_of: string;
  close: number;
  trend: {
    label: "Uptrend" | "Downtrend" | "Mixed" | null;
    sma20: number | null;
    sma50: number | null;
    sma200: number | null;
    above_sma20: boolean | null;
    above_sma50: boolean | null;
    above_sma200: boolean | null;
    distance_sma50_pct: number | null;
  };
  rsi14: number | null;
  rsi_zone: "overbought" | "oversold" | "neutral" | null;
  macd: { value: number | null; signal: number | null; state: "bullish" | "bearish" | null };
  range_52w: { high: number; low: number; position: number | null };
  relative_strength_3m: {
    benchmark: string;
    symbol_return: number;
    benchmark_return: number | null;
    difference: number | null;
  } | null;
  atr14: number | null;
  atr_pct: number | null;
  atr_stop: number | null;
  volume_ratio: number | null;
  source: string;
  stale: boolean;
};

export type StripItem = QuoteChange & { label: string; symbol: string; description: string };

export type WatchlistItem = QuoteChange & {
  symbol: string;
  security_name: string;
  asset_type: "STOCK" | "ETF";
  exchange: string;
  position: number;
  added_at: string;
  stale: boolean;
};

export type DatedMetric = { value: number | null; as_of: string | null; note: string | null };

export type ValuationBand = {
  metric: string;
  status: "available" | "not_available";
  current: number | null;
  min?: number;
  median?: number;
  max?: number;
  percentile?: number;
  observations?: number;
  start?: string | null;
  end?: string | null;
  note?: string;
};

type NotApplicable = { symbol: string; applicable: false; reason: string; source: string };

export type Fundamentals = NotApplicable | {
  symbol: string;
  name: string;
  applicable: true;
  cik: number;
  sec_name: string;
  sic: string | null;
  sic_description: string | null;
  latest_filing: { form: string; filed: string; period: string | null; url: string } | null;
  price: DatedMetric;
  period: { ttm_end: string | null; latest_quarter_end: string | null };
  valuation: Record<"market_cap" | "enterprise_value" | "pe_ttm" | "ps_ttm" | "ev_ebitda" | "pb" | "fcf_yield", DatedMetric>;
  growth: Record<"revenue_ttm_yoy" | "revenue_quarter_yoy" | "net_income_ttm_yoy", DatedMetric>;
  profitability: Record<"gross_margin" | "operating_margin" | "net_margin" | "fcf_margin", DatedMetric>;
  ttm: Record<"revenue" | "net_income" | "free_cash_flow" | "ebitda", DatedMetric>;
  balance_sheet: Record<"cash" | "debt" | "net_cash" | "debt_to_equity" | "shares_outstanding", DatedMetric>;
  valuation_history: { pe: ValuationBand; ps: ValuationBand };
  annual: Array<{ fiscal_year_end: string; revenue: number; net_income: number | null; free_cash_flow: number | null }>;
  notes: string[];
  source: string;
  fetched_at: string;
  stale: boolean;
};

export type InsiderTransaction = {
  filed: string;
  date: string | null;
  owner: string;
  role: string;
  code: string | null;
  description: string;
  shares: number | null;
  price: number | null;
  value: number | null;
  acquired_disposed: string | null;
  planned_10b5_1: boolean;
  shares_after: number | null;
  url: string;
};

export type InsiderActivity = NotApplicable | {
  symbol: string;
  applicable: true;
  days: number;
  since: string;
  filings: number;
  summary: {
    purchase_value: number;
    sale_value: number;
    net_value: number;
    buyers: number;
    sellers: number;
    planned_sale_value: number;
    other_transactions: number;
  };
  transactions: InsiderTransaction[];
  latest_filing: string | null;
  source: string;
  fetched_at: string;
  stale: boolean;
  warnings: string[];
};

export type PeerRow = {
  symbol: string;
  name?: string;
  available: boolean;
  reason?: string | null;
  market_cap?: number | null;
  pe_ttm?: number | null;
  ps_ttm?: number | null;
  ev_ebitda?: number | null;
  revenue_growth?: number | null;
  operating_margin?: number | null;
  return_3m?: number | null;
  ttm_end?: string | null;
};

export type PeerComparison = NotApplicable | {
  symbol: string;
  applicable: true;
  peers: string[];
  list_source: "SIC" | "USER";
  sic: string | null;
  sic_description: string | null;
  rows: PeerRow[];
  source: string;
};

export type Note = {
  id: string;
  symbol: string;
  body: string;
  pinned_date: string | null;
  author: "USER" | "CLAUDE";
  created_at: string;
  updated_at: string;
};

export type ExitPlanStatus = "PROPOSED" | "ACCEPTED" | "REJECTED" | "SUPERSEDED";

export type ExitPlan = {
  id: string;
  symbol: string;
  target_price: string | null;
  stop_price: string | null;
  review_date: string | null;
  reasoning: string;
  proposed_by: "CLAUDE" | "USER";
  status: ExitPlanStatus;
  reference_price: string | null;
  reference_date: string | null;
  note_id: string | null;
  created_at: string;
  decided_at: string | null;
};

export type ExitPlanInput = {
  target_price: string | null;
  stop_price: string | null;
  review_date: string | null;
  reasoning: string;
};

export type SymbolJournal = {
  symbol: string;
  instrument_id: string | null;
  decision: CurrentDecision | null;
  triggers: ReviewTrigger[];
  notes: Note[];
  exit_plans: ExitPlan[];
};

export type McpCheck = { ok: boolean; detail: string };

export type McpSetup = {
  server_name: string;
  config: { mcpServers: Record<string, { command: string; args: string[]; env: Record<string, string> }> };
  checks: { python: McpCheck; mcp_package: McpCheck; sec_contact: McpCheck };
  data_folder: string;
  config_file: string;
  read_tools: Record<string, string>;
  write_tools: Record<string, string>;
  prompt: string;
};

export type HeadlineSentiment = {
  label: "positive" | "neutral" | "negative";
  net: number;
  positive: number;
  neutral: number;
  negative: number;
  model: string;
};

export type NewsItem = {
  id: string;
  kind: "HEADLINE" | "FILING";
  title: string;
  summary: string | null;
  url: string;
  publisher: string;
  published_at: string;
  sentiment: HeadlineSentiment | null;
};

export type NewsPayload = {
  symbol: string;
  window_days: number;
  headlines: NewsItem[];
  filings: NewsItem[];
  sentiment:
    | { available: false; reason: string; model: null; trend: []; counts: null }
    | {
        available: true;
        reason: string | null;
        model: string;
        net: number;
        counts: { positive: number; neutral: number; negative: number };
        scored: number;
        trend: Array<{ date: string; count: number; net: number | null }>;
      };
  latest_published_at: string | null;
  fetched_at: string | null;
  stale: boolean;
  warnings: string[];
  sources: string[];
};
