export type SnapTradeStatus = {
  adapter_enabled: boolean;
  connection_status: string;
  connection_permission: string | null;
  brokerage_name: string;
  last_checked_at: string | null;
  last_attempted_sync_at: string | null;
  last_successful_sync_at: string | null;
  holdings_as_of: string | null;
  next_sync_allowed_at: string | null;
  sync_allowed: boolean;
  stale: boolean;
  warnings: string[];
};

export type SnapTradeSyncIssue = {
  severity: "error" | "warning";
  code: string;
  message: string;
  symbol: string | null;
};

export type SnapTradeIncomingPosition = {
  row_number: number;
  canonical_symbol: string;
  security_name: string;
  asset_type: "STOCK" | "ETF" | "CASH";
  exchange: string;
  trading_currency: "CAD" | "USD";
  quantity: string;
  average_cost: string | null;
  account_alias: string;
  account_type: string;
};

export type SnapTradeChange = {
  symbol: string;
  account_type: string;
  before: string | null;
  after: string | null;
};

export type ActivityPreviewSummary = {
  additions: number;
  changed_records: number;
  date_range: { start: string | null; end: string | null };
  type_counts: Record<string, number>;
  missing_symbols: string[];
  unsupported_activity_types: string[];
  coverage_start: string | null;
  coverage_end: string | null;
  incomplete_initial_sync: boolean;
  warning: string | null;
  accounts: Array<{
    account_alias: string;
    coverage_start: string | null;
    coverage_end: string | null;
    complete_initial_sync: boolean;
    source_as_of: string | null;
    warning: string | null;
  }>;
};

export type SnapTradeSyncPreview = {
  preview_id: string;
  created_at: string;
  expires_at: string;
  holdings_as_of: string | null;
  last_successful_sync_at: string | null;
  positions: SnapTradeIncomingPosition[];
  changes: {
    additions: SnapTradeChange[];
    removals: SnapTradeChange[];
    quantity_changes: SnapTradeChange[];
    cost_basis_changes: SnapTradeChange[];
    cash_changes: SnapTradeChange[];
  };
  issues: SnapTradeSyncIssue[];
  activity_preview: BrokerageActivity[];
  activity_summary: ActivityPreviewSummary;
  error_count: number;
  warning_count: number;
  can_apply: boolean;
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
  trading_currency: "CAD" | "USD";
  account_alias: string;
  account_type: string;
  quantity: string;
  average_cost: string | null;
  price: string | null;
  price_currency: string | null;
  market_value_trading: string | null;
  market_value_cad: string | null;
  unrealized_gain_loss_trading: string | null;
  unrealized_gain_loss_cad: string | null;
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
  imported_at: string;
  source_as_of: string | null;
  total_cad: string;
  priced_positions: number;
  total_positions: number;
  position_coverage_pct: string;
  warnings: string[];
  fx: {
    rate: string;
    observed_at: string;
    fetched_at?: string;
    source: string;
    source_url?: string;
    stale: number;
  } | null;
  holdings: Holding[];
};

export type HistoryPoint = {
  id: string;
  created_at: string;
  total_cad: string;
  position_coverage_pct: string;
};

export type SectorCategory = {
  sector: string;
  market_value_cad: string;
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
  total_cad: string;
  covered_value_cad: string;
  coverage_pct: string;
  etf_value_cad: string;
  etf_covered_value_cad: string;
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
  economic_exposure: AvailabilityMetric & {
    categories: Array<{ name: string; weight: string; market_value_cad: string }>;
    etf_lookthrough_available?: boolean;
    warning?: string;
  };
  trading_currency: Array<{ currency: string; weight: string }>;
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
  currency_exposure: AvailabilityMetric & {
    categories: Array<{ currency: string; weight: string }>;
    trading_currency: Array<{ currency: string; weight: string }>;
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

export type BrokerageActivity = {
  id?: string;
  normalized_type: string;
  symbol: string | null;
  trade_date: string | null;
  settlement_date: string | null;
  quantity: string | null;
  price: string | null;
  currency: string | null;
  fee: string | null;
  cash_amount: string | null;
  source?: string;
  source_as_of: string | null;
};

export type ActivityPayload = {
  activities: BrokerageActivity[];
  coverage: {
    start: string | null;
    end: string | null;
    complete: boolean;
    source_as_of: string | null;
    last_synced_at: string | null;
  };
  warnings: string[];
  freshness: string;
  source: string;
};

export type IncomePayload = {
  period_start: string;
  period_end: string;
  source: string;
  source_as_of: string | null;
  received_by_currency: Record<string, string>;
  withholding_tax_by_currency: Record<string, string>;
  income_by_holding: Array<{ symbol: string; amounts: Record<string, string> }>;
  forward_annual_estimate: null;
  portfolio_yield: null;
  upcoming_distributions: [];
  coverage: ActivityPayload["coverage"];
  warnings: string[];
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
  include_account_type: boolean;
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
