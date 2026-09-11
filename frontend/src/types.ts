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
  error_count: number;
  warning_count: number;
  can_apply: boolean;
};

export type PriceCapabilities = {
  provider: string;
  automatic_refresh_supported: boolean;
  automatic_refresh_seconds: number | null;
};

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
    source: string;
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
