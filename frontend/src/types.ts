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
