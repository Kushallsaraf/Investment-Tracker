import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";

const holding = {
  instrument_id: "instrument-1", position_id: "position-1", canonical_symbol: "ACME.TO",
  security_name: "Acme Inc.", asset_type: "STOCK", exchange: "TSX", trading_currency: "CAD",
  account_alias: "TFSA-01", account_type: "TFSA", quantity: "2", average_cost: "40",
  price: "50", price_currency: "CAD", market_value_trading: "100", market_value_cad: "100",
  unrealized_gain_loss_trading: "20", unrealized_gain_loss_cad: "20", portfolio_weight: "1",
  price_timestamp: "2026-09-10T20:00:00Z", price_fetched_at: "2026-09-11T12:00:00Z",
  price_source: "Synthetic fixture", price_source_url: null, quote_status: "end_of_day",
  delay_minutes: null, price_stale: 0, data_status: "end_of_day", manual_sector: "Industrials",
  sector_source: "Local classification", sector_source_url: null, sector_as_of: "2026-09-11",
};

const portfolio = {
  valuation_snapshot_id: "valuation-1", holding_snapshot_id: "holding-1",
  created_at: "2026-09-11T12:00:00Z", imported_at: "2026-09-11T11:00:00Z",
  source_as_of: "2026-09-11T10:00:00Z", total_cad: "100", priced_positions: 1,
  total_positions: 1, position_coverage_pct: "1", warnings: [], fx: null, holdings: [holding],
};

const sectors = {
  valuation_snapshot_id: "valuation-1", calculated_at: "2026-09-11T12:00:00Z",
  total_cad: "100", covered_value_cad: "100", coverage_pct: "1", etf_value_cad: "0",
  etf_covered_value_cad: "0", etf_coverage_pct: "1",
  categories: [{ sector: "Industrials", market_value_cad: "100", portfolio_weight: "1" }],
  evidence: [], warnings: [], sector_options: ["Industrials", "Information Technology"],
};

const analytics = {
  generated_at: "2026-09-11T12:00:00Z",
  concentration: {
    status: "available", largest_holding_weight: "1", top_five_weight: "1",
    individual_stock_weight: "1", etf_weight: "0", cash_weight: "0", missing_data_pct: "0",
    source: "Immutable local snapshot", as_of: "2026-09-11T12:00:00Z", coverage_pct: "1",
  },
  economic_exposure: {
    status: "partial", label: "PARTIAL COVERAGE", categories: [], coverage_pct: "0",
    etf_lookthrough_available: false,
    reason: "Economic exposure requires verified evidence; trading currency is not substituted.",
  },
  trading_currency: [{ currency: "CAD", weight: "1" }],
  performance: {
    status: "missing", label: "INSUFFICIENT TRANSACTION HISTORY",
    reason: "Adjusted total-return observations and external cash-flow history are unavailable. Current holdings are not backfilled.",
    benchmark: "S&P/TSX Composite Total Return Index", portfolio_return: null,
    benchmark_return: null, difference: null, periods: [
      { period: "1 month", portfolio: null, benchmark: null },
      { period: "YTD", portfolio: null, benchmark: null },
      { period: "1 year", portfolio: null, benchmark: null },
      { period: "Since first reliable observation", portfolio: null, benchmark: null },
    ], currency: "CAD", source: null, as_of: null, coverage_pct: "0",
  },
  risk: {
    status: "missing", label: "INSUFFICIENT DATA", reason: "Aligned adjusted history is unavailable.",
    benchmark: "S&P/TSX Composite Total Return Index", annualized_volatility: null,
    maximum_drawdown: null, beta: null, correlation: null, measurement_period: null,
    observation_frequency: null, source: null, as_of: null, coverage_pct: "0",
    disclaimer: "Historical risk · not a forecast",
  },
  currency_exposure: {
    status: "missing", label: "NOT AVAILABLE",
    reason: "Listing currency is not economic currency exposure.", categories: [],
    trading_currency: [{ currency: "CAD", weight: "1" }], coverage_pct: "0",
  },
  etf_lookthrough: {
    status: "missing", overlap: [], weighted_mer: null, sector_allocation: [],
    country_allocation: [], evidence: [], coverage_pct: "0",
    warning: "No reliable issuer constituent evidence is stored.",
  },
};

const journal = {
  entries: [{ holding, profile: null, decision: null, latest_ai_review: null, active_trigger: null }],
  decision_history: [], triggers: [], alerts: [], generated_at: "2026-09-11T12:00:00Z",
};

const status = {
  adapter_enabled: true, connection_status: "connected_read_only", connection_permission: "read",
  brokerage_name: "Wealthsimple", last_checked_at: "2026-09-11T12:00:00Z",
  last_attempted_sync_at: "2026-09-11T12:00:00Z", last_successful_sync_at: "2026-09-11T12:00:00Z",
  holdings_as_of: "2026-09-11T10:00:00Z", next_sync_allowed_at: "2099-09-11T12:10:00Z",
  sync_allowed: false, stale: false, warnings: [],
};

function response(body: unknown, code = 200) {
  return new Response(JSON.stringify(body), { status: code, headers: { "Content-Type": "application/json" } });
}

function createFetch(overrides: Record<string, unknown> = {}) {
  return vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const method = init?.method ?? "GET";
    const key = `${method} ${url}`;
    if (key in overrides) return response(overrides[key]);
    if (url === "/api/portfolio/history") return response({ history: [] });
    if (url === "/api/portfolio/sectors") return response({ status: "ok", analysis: sectors });
    if (url === "/api/portfolio") return response({ status: "ok", portfolio });
    if (url === "/api/analytics") return response({ analytics });
    if (url.startsWith("/api/activity")) return response({
      activities: [], coverage: { start: null, end: null, complete: false, source_as_of: null, last_synced_at: null },
      warnings: ["Completed activity history is incomplete."], freshness: "daily_cached",
      source: "SnapTrade completed activities",
    });
    if (url === "/api/income") return response({ income: {
      period_start: "2025-09-11", period_end: "2026-09-11", source: "SnapTrade completed activities",
      source_as_of: null, received_by_currency: {}, withholding_tax_by_currency: {}, income_by_holding: [],
      forward_annual_estimate: null, portfolio_yield: null, upcoming_distributions: [],
      coverage: { start: null, end: null, complete: false, source_as_of: null, last_synced_at: null },
      warnings: ["Incomplete activity history."],
    } });
    if (url === "/api/journal") return response({ journal });
    if (url === "/api/research/prompts") return response({ prompts: [{
      id: "prompt-1", name: "Canadian evidence review", prompt_text: "Use sources and as-of dates.",
      is_default: 1, created_at: "2026-09-11T12:00:00Z", updated_at: "2026-09-11T12:00:00Z",
    }] });
    if (url === "/api/research/reviews") return response({ reviews: [] });
    if (url === "/api/snaptrade/status") return response(status);
    if (url === "/api/snaptrade/sync/pending") return response({ preview: null });
    if (url === "/api/prices/capabilities") return response({
      provider: "Yahoo daily/manual", automatic_refresh_supported: false, automatic_refresh_seconds: null,
    });
    if (url === "/api/research/packs/preview") return response({ pack: {
      export_id: null, instrument_id: "instrument-1", symbol: "ACME.TO", prompt_id: "prompt-1",
      trigger_id: null,
      privacy: { weights_only: true, include_quantities: false, include_dollar_values: false, include_account_type: false },
      markdown: "# ACME.TO evidence review\n\nQuantity: excluded\nMissing data: adjusted total return unavailable.",
      holdings_as_of: "2026-09-11T10:00:00Z", evidence_as_of: null,
      generated_at: "2026-09-11T12:00:00Z",
    } });
    if (method !== "GET") return response({ status: "ok" });
    throw new Error(`Unexpected request: ${key}`);
  });
}

describe("Investment Tracker", () => {
  afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
  beforeEach(() => { window.localStorage.clear(); window.history.replaceState({}, "", "/"); });

  it("renders all eight persistent navigation tabs and explicit evidence states", async () => {
    vi.stubGlobal("fetch", createFetch());
    render(<App />);
    expect(await screen.findByRole("heading", { name: "Portfolio dashboard" })).toBeInTheDocument();
    const nav = screen.getByRole("navigation", { name: "Investment Tracker sections" });
    for (const name of ["Dashboard", "Holdings", "Analytics", "Income", "Activity", "Decisions", "Research", "Settings"]) {
      expect(within(nav).getByRole("tab", { name })).toBeInTheDocument();
    }
    expect(screen.getByText("SNAPTRADE · READ ONLY")).toBeInTheDocument();
    expect(screen.getByText("Today’s change").nextElementSibling).toHaveTextContent("NOT AVAILABLE");
    fireEvent.click(within(nav).getByRole("tab", { name: "Income" }));
    expect(screen.getByRole("heading", { name: "Income" })).toBeInTheDocument();
    expect(window.localStorage.getItem("investment-tracker.active-tab.v1")).toBe("Income");
    expect(screen.queryByText(/place order/i)).not.toBeInTheDocument();
  });

  it("provides all analytics views without fabricating unavailable returns or risk", async () => {
    vi.stubGlobal("fetch", createFetch());
    render(<App />);
    fireEvent.click(await screen.findByRole("tab", { name: "Analytics" }));
    const tabs = screen.getByRole("tablist", { name: "Analytics views" });
    for (const name of ["Diversification", "Performance", "Risk", "ETF look-through"]) {
      expect(within(tabs).getByRole("tab", { name })).toBeInTheDocument();
    }
    fireEvent.click(within(tabs).getByRole("tab", { name: "Performance" }));
    expect(screen.getAllByText(/INSUFFICIENT TRANSACTION HISTORY/).length).toBeGreaterThan(0);
    expect(screen.getByText(/current holdings are not backfilled/i)).toBeInTheDocument();
    fireEvent.click(within(tabs).getByRole("tab", { name: "Risk" }));
    expect(screen.getByText("Historical risk · not a forecast")).toBeInTheDocument();
    expect(screen.getByText(/Listing currency is not economic currency exposure/)).toBeInTheDocument();
    fireEvent.click(within(tabs).getByRole("tab", { name: "ETF look-through" }));
    expect(screen.getByText(/verified constituent holdings are not stored/)).toBeInTheDocument();
    expect(screen.getByText("NO BROAD AUTOMATIC SUPPORT CLAIM")).toBeInTheDocument();
  });

  it("keeps the holdings worksheet configurable and confirms keyboard row deletion locally", async () => {
    const fetchMock = createFetch();
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);
    fireEvent.click(await screen.findByRole("tab", { name: "Holdings" }));
    expect(screen.queryByRole("columnheader", { name: "Account" })).not.toBeInTheDocument();
    expect(screen.queryByRole("columnheader", { name: "Currency" })).not.toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Sector for ACME.TO" })).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "My decision for ACME.TO" })).toHaveValue("WATCH");
    fireEvent.click(screen.getByText(/COLUMNS \d+\/\d+/));
    fireEvent.click(screen.getByRole("checkbox", { name: "Account" }));
    expect(screen.getByRole("columnheader", { name: "Account" })).toBeInTheDocument();
    expect(window.localStorage.getItem("portfolio-manager.visible-columns.v1")).toContain("account");
    const rowButton = screen.getByRole("button", { name: "Select row 1: ACME.TO" });
    fireEvent.click(rowButton);
    fireEvent.keyDown(rowButton, { key: "Delete" });
    expect(await screen.findByRole("dialog")).toHaveTextContent("not a Wealthsimple sale");
    expect(screen.getByRole("dialog")).toHaveTextContent("never contacts SnapTrade or a brokerage");
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "DELETE LOCAL ROW" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      "/api/portfolio/positions/position-1", expect.objectContaining({ method: "DELETE" }),
    ));
  });

  it("separates decisions, Claude suggestions, thesis data and review-only triggers", async () => {
    const fetchMock = createFetch();
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);
    fireEvent.click(await screen.findByRole("tab", { name: "Decisions" }));
    expect(screen.getByText("MY DECISION ≠ CLAUDE SUGGESTION")).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "My decision for ACME.TO" })).toHaveValue("WATCH");
    expect(screen.getByText("Manual Claude workflow only")).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Portfolio role" })).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Thesis strength" })).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Trigger condition" })).toBeInTheDocument();
    fireEvent.change(screen.getByRole("textbox", { name: "Decision reason" }), {
      target: { value: "Revisit after the next evidence update" },
    });
    fireEvent.change(screen.getByRole("combobox", { name: "Claude suggestion response" }), {
      target: { value: "CONSIDERING" },
    });
    fireEvent.change(screen.getByLabelText("Decision review due date"), {
      target: { value: "2026-10-15" },
    });
    fireEvent.click(screen.getByRole("button", { name: "RECORD DECISION" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      "/api/journal/instruments/instrument-1/decisions",
      expect.objectContaining({
        method: "POST",
        body: expect.stringContaining('"claude_disposition":"CONSIDERING"'),
      }),
    ));
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/journal/instruments/instrument-1/decisions",
      expect.objectContaining({ body: expect.stringContaining('"review_due_date":"2026-10-15"') }),
    );
    expect(screen.getByText("REVIEW ONLY · NEVER AN ORDER")).toBeInTheDocument();
    expect(screen.getByText(/never contacts? Claude or a brokerage/i)).toBeInTheDocument();
  });

  it("previews a weights-only Claude review pack without sending data to Claude", async () => {
    vi.stubGlobal("fetch", createFetch());
    render(<App />);
    fireEvent.click(await screen.findByRole("tab", { name: "Research" }));
    fireEvent.change(screen.getByRole("combobox", { name: "Research holding" }), {
      target: { value: "instrument-1" },
    });
    fireEvent.click(screen.getByRole("button", { name: "PREVIEW EXACT MARKDOWN" }));
    expect(await screen.findByText(/# ACME.TO evidence review/)).toBeInTheDocument();
    expect(screen.getByLabelText("Claude review pack Markdown preview")).toHaveTextContent("Quantity: excluded");
    expect(screen.getByText(/no Claude API connection/i)).toBeInTheDocument();
    expect(screen.getByText("STORED SEPARATELY FROM MY DECISION")).toBeInTheDocument();
  });

  it("shows read-only connection timestamps and an activity table with no order actions", async () => {
    vi.stubGlobal("fetch", createFetch());
    render(<App />);
    fireEvent.click(await screen.findByRole("tab", { name: "Activity" }));
    expect(screen.getByText("NO ORDER ACTIONS AVAILABLE")).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Activity type" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: "Settings" }));
    expect(screen.getByText("SnapTrade / Wealthsimple")).toBeInTheDocument();
    expect(screen.getAllByText("READ ONLY").length).toBeGreaterThan(0);
    expect(screen.getByText(/Yahoo daily\/manual · separate from holdings/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "VIEW HISTORY" }));
    expect(screen.getByText("NO HISTORICAL VALUATION SNAPSHOTS")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "DELETE LOCAL DATA" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /buy|sell|order/i })).not.toBeInTheDocument();
  });

  it("requires explicit confirmation before applying holdings and activity changes", async () => {
    const preview = {
      preview_id: "preview-1", created_at: "2026-09-11T12:00:00Z",
      expires_at: "2026-09-11T12:30:00Z", holdings_as_of: "2026-09-11T10:00:00Z",
      last_successful_sync_at: "2026-09-11T10:00:00Z", positions: [],
      changes: { additions: [], removals: [], quantity_changes: [], cost_basis_changes: [], cash_changes: [] },
      issues: [], activity_preview: [], activity_summary: {
        additions: 2, changed_records: 1,
        date_range: { start: "2026-01-01T00:00:00Z", end: "2026-09-10T00:00:00Z" },
        type_counts: { BUY: 1, DISTRIBUTION: 2 }, missing_symbols: [],
        unsupported_activity_types: [], coverage_start: "2026-01-01T00:00:00Z",
        coverage_end: "2026-09-10T00:00:00Z", incomplete_initial_sync: false,
        warning: null, accounts: [],
      }, error_count: 0, warning_count: 0, can_apply: true,
    };
    const fetchMock = createFetch({ "GET /api/snaptrade/sync/pending": { preview } });
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);
    expect(await screen.findByText("ACTIVITY ADDITIONS")).toBeInTheDocument();
    expect(screen.getByText("BUY 1 · DISTRIBUTION 2")).toBeInTheDocument();
    const apply = screen.getByRole("button", { name: "APPLY SNAPSHOT" });
    expect(apply).toBeDisabled();
    fireEvent.click(screen.getByRole("checkbox", { name: /I reviewed holdings and completed-activity changes/ }));
    expect(apply).toBeEnabled();
    fireEvent.click(apply);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      "/api/snaptrade/sync/preview-1/apply", expect.objectContaining({ method: "POST" }),
    ));
  });
});
