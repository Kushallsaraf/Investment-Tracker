import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";

const chartMocks = vi.hoisted(() => ({
  setMarkers: vi.fn(),
  clickHandlers: [] as Array<(param: { time?: string }) => void>,
  priceLines: [] as Array<{ price: number; title: string }>,
}));

vi.mock("lightweight-charts", () => {
  const series = () => ({
    setData: vi.fn(),
    createPriceLine: vi.fn((options: { price: number; title: string }) => {
      if (options.title) chartMocks.priceLines.push(options);
      return options;
    }),
    removePriceLine: vi.fn((line: unknown) => {
      const index = chartMocks.priceLines.indexOf(line as { price: number; title: string });
      if (index >= 0) chartMocks.priceLines.splice(index, 1);
    }),
    priceScale: () => ({ applyOptions: vi.fn() }),
  });
  return {
    createChart: vi.fn(() => ({
      addSeries: vi.fn(series),
      panes: () => [{ setHeight: vi.fn() }, { setHeight: vi.fn() }],
      timeScale: () => ({ fitContent: vi.fn() }),
      subscribeCrosshairMove: vi.fn(),
      unsubscribeCrosshairMove: vi.fn(),
      subscribeClick: vi.fn((handler: (param: { time?: string }) => void) => chartMocks.clickHandlers.push(handler)),
      unsubscribeClick: vi.fn(),
      remove: vi.fn(),
    })),
    createSeriesMarkers: vi.fn((_series: unknown, markers: unknown) => {
      chartMocks.setMarkers(markers);
      return { setMarkers: chartMocks.setMarkers };
    }),
    CandlestickSeries: {}, LineSeries: {}, HistogramSeries: {},
    ColorType: { Solid: "solid" }, CrosshairMode: { Normal: 0 }, LineStyle: { Solid: 0, Dotted: 1, Dashed: 2 },
  };
});

const holding = {
  instrument_id: "instrument-1", position_id: "position-1", canonical_symbol: "ACME",
  security_name: "Acme Corporation", asset_type: "STOCK", exchange: "NYSE",
  account_name: "Brokerage", quantity: "2", average_cost: "40",
  price: "50", market_value: "100", unrealized_gain_loss: "20", portfolio_weight: "1",
  price_timestamp: "2026-09-10T20:00:00Z", price_fetched_at: "2026-09-11T12:00:00Z",
  price_source: "Synthetic fixture", price_source_url: null, quote_status: "end_of_day",
  delay_minutes: null, price_stale: 0, data_status: "end_of_day", manual_sector: "Industrials",
  sector_source: "Local classification", sector_source_url: null, sector_as_of: "2026-09-11",
};

const portfolio = {
  valuation_snapshot_id: "valuation-1", holding_snapshot_id: "holding-1",
  created_at: "2026-09-11T12:00:00Z", snapshot_created_at: "2026-09-11T11:00:00Z",
  data_origin: "manual", total_value: "100", priced_positions: 1,
  total_positions: 1, position_coverage_pct: "1", warnings: [], holdings: [holding],
};

const sectors = {
  valuation_snapshot_id: "valuation-1", calculated_at: "2026-09-11T12:00:00Z",
  total_value: "100", covered_value: "100", coverage_pct: "1", etf_value: "0",
  etf_covered_value: "0", etf_coverage_pct: "1",
  categories: [{ sector: "Industrials", market_value: "100", portfolio_weight: "1" }],
  evidence: [], warnings: [], sector_options: ["Industrials", "Information Technology"],
};

const analytics = {
  generated_at: "2026-09-11T12:00:00Z",
  concentration: {
    status: "available", largest_holding_weight: "1", top_five_weight: "1",
    individual_stock_weight: "1", etf_weight: "0", cash_weight: "0", missing_data_pct: "0",
    source: "Immutable local snapshot", as_of: "2026-09-11T12:00:00Z", coverage_pct: "1",
  },
  performance: {
    status: "missing", label: "INSUFFICIENT TRANSACTION HISTORY",
    reason: "Adjusted total-return observations and external cash-flow history are unavailable. Current holdings are not backfilled.",
    benchmark: "S&P 500 Total Return Index", portfolio_return: null,
    benchmark_return: null, difference: null, periods: [
      { period: "1 month", portfolio: null, benchmark: null },
      { period: "YTD", portfolio: null, benchmark: null },
      { period: "1 year", portfolio: null, benchmark: null },
      { period: "Since first reliable observation", portfolio: null, benchmark: null },
    ], currency: "USD", source: null, as_of: null, coverage_pct: "0",
  },
  risk: {
    status: "missing", label: "INSUFFICIENT DATA", reason: "Aligned adjusted history is unavailable.",
    benchmark: "S&P 500 Total Return Index", annualized_volatility: null,
    maximum_drawdown: null, beta: null, correlation: null, measurement_period: null,
    observation_frequency: null, source: null, as_of: null, coverage_pct: "0",
    disclaimer: "Historical risk · not a forecast",
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

const status = { data_origin: "manual", snapshot_count: 1, latest_snapshot_at: "2026-09-11T11:00:00Z" };

const bars = Array.from({ length: 30 }, (_, index) => ({
  date: `2026-09-${String(index + 1).padStart(2, "0")}`,
  open: 100 + index, high: 102 + index, low: 99 + index, close: 101 + index, adj_close: 101 + index, volume: 1_000_000,
}));
const nulls = bars.map(() => null);

function chartPayload(symbol: string, range: string) {
  return {
    symbol, name: `${symbol} Synthetic Inc.`, asset_type: "STOCK", exchange: "NYSE", range, bars,
    indicators: { ema20: nulls, ema50: nulls, sma200: nulls, bb_upper: nulls, bb_middle: nulls, bb_lower: nulls, rsi14: nulls, macd: nulls, macd_signal: nulls, macd_histogram: nulls },
    quote: { last: 130, change: 1, change_pct: 0.0077, as_of: "2026-09-30" },
    source: "Yahoo Finance chart (daily)", fetched_at: "2026-09-30T20:00:00Z", stale: false,
  };
}

const technicals = {
  symbol: "SPY", as_of: "2026-09-30", close: 130,
  trend: { label: "Uptrend", sma20: 128, sma50: 120, sma200: 110, above_sma20: false, above_sma50: true, above_sma200: true, distance_sma50_pct: 0.083 },
  rsi14: 64.2, rsi_zone: "neutral", macd: { value: 1.2, signal: 0.8, state: "bullish" },
  range_52w: { high: 131, low: 90, position: 0.97 },
  relative_strength_3m: { benchmark: "SPY", symbol_return: 0.05, benchmark_return: 0.05, difference: 0 },
  atr14: 2.1, atr_pct: 0.016, atr_stop: 125.8, volume_ratio: 1.62, source: "Yahoo Finance chart (daily)", stale: false,
};

const metric = (value: number | null, note: string | null = null) => ({ value, as_of: "2026-06-30", note: value == null ? note ?? "Not available" : null });
const fundamentals = {
  symbol: "SPY", name: "SPY Synthetic Inc.", applicable: true, cik: 1234, sec_name: "SYNTHETIC CORP", sic: "3674",
  sic_description: "Semiconductors & Related Devices",
  latest_filing: { form: "10-Q", filed: "2026-08-05", period: "2026-06-30", url: "https://www.sec.gov/Archives/edgar/data/1234/x-index.htm" },
  price: metric(130), period: { ttm_end: "2026-06-30", latest_quarter_end: "2026-06-30" },
  valuation: { market_cap: metric(4.5e12), enterprise_value: metric(4.4e12), pe_ttm: metric(52.3), ps_ttm: metric(25.1), ev_ebitda: metric(null, "EBITDA negative or unavailable"), pb: metric(40), fcf_yield: metric(0.019) },
  growth: { revenue_ttm_yoy: metric(0.62), revenue_quarter_yoy: metric(0.55), net_income_ttm_yoy: metric(0.8) },
  profitability: { gross_margin: metric(0.73), operating_margin: metric(0.6), net_margin: metric(0.5), fcf_margin: metric(0.45) },
  ttm: { revenue: metric(1.8e11), net_income: metric(9e10), free_cash_flow: metric(8e10), ebitda: metric(1.1e11) },
  balance_sheet: { cash: metric(5e10), debt: metric(1e10), net_cash: metric(4e10), debt_to_equity: metric(0.1), shares_outstanding: metric(2.4e10) },
  valuation_history: {
    pe: { metric: "P/E", status: "available", current: 52.3, min: 30, median: 55, max: 120, percentile: 0.4, observations: 20, start: "2021-09-30", end: "2026-06-30" },
    ps: { metric: "P/S", status: "not_available", current: 25.1, note: "Needs at least 8 quarters of positive history" },
  },
  annual: [], notes: ["Capital expenditures were not reported under the standard concept."],
  source: "SEC EDGAR", fetched_at: "2026-10-26T20:00:00Z", stale: false,
};
const insiders = {
  symbol: "SPY", applicable: true, days: 90, since: "2026-07-28", filings: 3,
  summary: { purchase_value: 50000, sale_value: 149000, net_value: -99000, buyers: 1, sellers: 2, planned_sale_value: 149000, other_transactions: 0 },
  transactions: [
    { filed: "2026-10-03", date: "2026-10-01", owner: "Jane Doe", role: "CFO", code: "P", description: "Open-market purchase", shares: 1000, price: 50, value: 50000, acquired_disposed: "A", planned_10b5_1: false, shares_after: 5000, url: "https://www.sec.gov/a-index.htm" },
    { filed: "2026-09-20", date: "2026-09-18", owner: "John Roe", role: "CEO", code: "S", description: "Open-market sale", shares: 2000, price: 60, value: 120000, acquired_disposed: "D", planned_10b5_1: true, shares_after: 5000, url: "https://www.sec.gov/b-index.htm" },
  ],
  latest_filing: "2026-10-03", source: "SEC EDGAR Form 4 filings", fetched_at: "2026-10-26T20:00:00Z", stale: false, warnings: [],
};
const peers = {
  symbol: "SPY", applicable: true, peers: ["AMD"], list_source: "SIC", sic: "3674", sic_description: "Semiconductors & Related Devices",
  rows: [
    { symbol: "SPY", name: "SYNTHETIC CORP", available: true, market_cap: 4.5e12, pe_ttm: 52.3, ps_ttm: 25.1, ev_ebitda: 40, revenue_growth: 0.62, operating_margin: 0.6, return_3m: 0.05, ttm_end: "2026-06-30" },
    { symbol: "AMD", name: "ADVANCED MICRO DEVICES", available: false, reason: "Not available (RuntimeError)", return_3m: -0.02 },
  ],
  source: "SEC EDGAR",
};

const note = {
  id: "note-1", symbol: "SPY", body: "Earnings gap filled. Watching $125 as support.", pinned_date: "2026-09-15",
  author: "USER", created_at: "2026-09-16T12:00:00Z", updated_at: "2026-09-16T12:00:00Z",
};
const proposal = {
  id: "plan-1", symbol: "SPY", target_price: "800.00", stop_price: "700.00", review_date: "2027-01-15",
  reasoning: "Prior high near 800; the stop sits under the 200-day average.", proposed_by: "CLAUDE",
  status: "PROPOSED", reference_price: "765.37", reference_date: "2026-09-30", note_id: null,
  created_at: "2026-10-01T12:00:00Z", decided_at: null,
};
const acceptedPlan = {
  ...proposal, id: "plan-0", target_price: "780.00", stop_price: "720.00", review_date: null,
  reasoning: "Earlier plan.", proposed_by: "USER", status: "ACCEPTED", decided_at: "2026-09-20T12:00:00Z",
};

const newsPayload = {
  symbol: "SPY", window_days: 7,
  headlines: [
    { id: "n1", kind: "HEADLINE", title: "Synthetic Inc. posts record margin", summary: "Margins rose.", url: "https://example.com/n1", publisher: "Wire", published_at: "2026-11-04T21:00:00+00:00", sentiment: { label: "positive", net: 0.85, positive: 0.9, neutral: 0.05, negative: 0.05, model: "ProsusAI/finbert" } },
    { id: "n2", kind: "HEADLINE", title: "Synthetic Inc. guidance disappoints", summary: null, url: "https://example.com/n2", publisher: "Yahoo Finance", published_at: "2026-11-03T13:00:00+00:00", sentiment: { label: "negative", net: -0.7, positive: 0.1, neutral: 0.1, negative: 0.8, model: "ProsusAI/finbert" } },
  ],
  filings: [{ id: "f1", kind: "FILING", title: "8-K: Earnings results", summary: null, url: "https://www.sec.gov/Archives/f1", publisher: "SEC EDGAR", published_at: "2026-11-04T00:00:00+00:00", sentiment: null }],
  sentiment: { available: true, reason: null, model: "ProsusAI/finbert", net: 0.075, counts: { positive: 1, neutral: 0, negative: 1 }, scored: 2,
    trend: ["2026-10-30", "2026-10-31", "2026-11-01", "2026-11-02", "2026-11-03", "2026-11-04", "2026-11-05"].map((date) => ({ date, count: date === "2026-11-04" || date === "2026-11-03" ? 1 : 0, net: date === "2026-11-04" ? 0.85 : date === "2026-11-03" ? -0.7 : null })) },
  latest_published_at: "2026-11-04T21:00:00+00:00", fetched_at: "2026-11-05T12:00:00+00:00", stale: false, warnings: [],
  sources: ["Yahoo Finance RSS", "Nasdaq RSS", "SEC EDGAR 8-K filings"],
};

const macroSnapshot = {
  generated_at: "2026-11-06T15:00:00+00:00", fred_configured: true,
  indicators: { source: "FRED", items: [
    { key: "unemployment", label: "Unemployment rate", unit: "%", group: "Jobs", frequency: "monthly", available: true, value: 4.1, as_of: "2026-10-01", previous: 4.2, previous_as_of: "2026-09-01", change: -0.1, compared_with: "previous release" },
    { key: "curve", label: "10-year minus 2-year", unit: "pts", group: "Rates", available: true, value: -0.12, as_of: "2026-11-05", previous: 0.1, previous_as_of: "2026-10-06", change: -0.22, compared_with: "about a month earlier" },
    { key: "gdp", label: "Real GDP growth", unit: "%", group: "Growth", available: false, reason: "FRED returned HTTP 500" },
  ] },
  calendar: { days: 45, warnings: [], unavailable: null, events: [
    { date: "2026-12-04", name: "Jobs report", impact: "high", detail: "Payrolls and the unemployment rate", source: "FRED" },
    { date: "2026-12-09", name: "Fed rate decision (FOMC)", impact: "high", detail: "Rate decision with economic projections", source: "Federal Reserve" },
  ] },
  news: {
    days: 7, sentiment_reason: null, fetched_at: "2026-11-06T15:00:00+00:00", stale: false, warnings: [], sources: ["CNBC", "MarketWatch", "Federal Reserve"],
    themes: [
      { key: "geopolitics", label: "War and geopolitics", count: 2, last_day: 1, net: -0.5, sectors: ["Energy", "Industrials"], holdings: [{ symbol: "XOM", weight: 0.063 }], holdings_weight: 0.063 },
      { key: "rates", label: "Fed and rates", count: 1, last_day: 0, net: 0.02, sectors: ["Financials"], holdings: [], holdings_weight: null },
      { key: "trade", label: "Trade and tariffs", count: 0, last_day: 0, net: null, sectors: ["Industrials"], holdings: [], holdings_weight: null },
    ],
    headlines: [
      { id: "m1", title: "Oil jumps as Iran conflict threatens supply", summary: null, url: "https://example.com/m1", publisher: "CNBC", published_at: "2026-11-06T13:00:00+00:00", themes: ["geopolitics"], sentiment: { label: "negative", net: -0.6 } },
      { id: "m2", title: "Powell signals patience on rate cuts", summary: null, url: "https://example.com/m2", publisher: "MarketWatch", published_at: "2026-11-05T13:00:00+00:00", themes: ["rates"], sentiment: { label: "neutral", net: 0.02 } },
    ],
  },
};

function journalFor(symbol: string, decision: string | null = null) {
  return {
    symbol, instrument_id: decision ? "instrument-9" : null,
    decision: decision ? { instrument_id: "instrument-9", symbol, decision, reason: "", decision_date: "2026-10-20", review_due_date: null, updated_at: "2026-10-20T00:00:00Z" } : null,
    triggers: [{ id: "trigger-1", instrument_id: "instrument-9", symbol, trigger_type: "PRICE_ABOVE", lower_value: null, upper_value: "140", trigger_date: null, note: "", reason: "", expires_at: null, state: "ACTIVE", created_at: "2026-10-20T00:00:00Z", triggered_at: null, observed_value: null, quote_source: null, quote_timestamp: null, frozen_holding_snapshot_id: null, frozen_valuation_snapshot_id: null }],
    notes: symbol === "SPY" ? [note] : [],
    exit_plans: symbol === "SPY" ? [proposal, acceptedPlan] : [],
  };
}

function response(body: unknown, code = 200) {
  return new Response(JSON.stringify(body), { status: code, headers: { "Content-Type": "application/json" } });
}

function createFetch(overrides: Record<string, unknown> = {}) {
  return vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const method = init?.method ?? "GET";
    const key = `${method} ${url}`;
    if (key in overrides) return response(overrides[key]);
    if (url === "/api/market/strip") return response({ items: [
      { label: "SPY", symbol: "SPY", description: "S&P 500 ETF", last: 765.37, change: 5.4, change_pct: 0.0071, as_of: "2026-09-30" },
      { label: "VIX", symbol: "^VIX", description: "Volatility index", last: 18.39, change: -1.06, change_pct: -0.0545, as_of: "2026-09-30" },
    ], fetched_at: "2026-09-30T20:00:00Z", source: "Yahoo" });
    const chartMatch = /^\/api\/market\/([^/]+)\/chart\?range=(\w+)$/.exec(url);
    if (chartMatch) {
      const symbol = decodeURIComponent(chartMatch[1]);
      if (symbol === "NOPE") return response({ detail: "NOPE was not found" }, 422);
      return response(chartPayload(symbol, chartMatch[2]));
    }
    if (/^\/api\/market\/[^/]+\/technicals$/.test(url)) return response(technicals);
    if (/^\/api\/market\/[^/]+\/fundamentals$/.test(url)) return response(fundamentals);
    const journalMatch = /^\/api\/market\/([^/]+)\/(journal|decision|notes)$/.exec(url);
    if (journalMatch) {
      const symbol = decodeURIComponent(journalMatch[1]);
      if (journalMatch[2] === "decision") return response(journalFor(symbol, JSON.parse(String(init?.body)).decision));
      if (journalMatch[2] === "notes") return response({ status: "ok", note: { ...note, id: "note-2", ...JSON.parse(String(init?.body)) } });
      return response(journalFor(symbol));
    }
    if (/^\/api\/market\/[^/]+\/insiders\?days=90$/.test(url)) return response(insiders);
    if (/^\/api\/market\/[^/]+\/news$/.test(url)) return response(newsPayload);
    if (/^\/api\/market\/[^/]+\/peers$/.test(url)) {
      if (method === "PUT") return response({ ...peers, peers: JSON.parse(String(init?.body)).symbols, list_source: "USER" });
      return response(peers);
    }
    if (url === "/api/watchlist" && method === "GET") return response({ items: [], source: "Yahoo" });
    if (url === "/api/portfolio/history") return response({ history: [] });
    if (url === "/api/portfolio/sectors") return response({ status: "ok", analysis: sectors });
    if (url === "/api/portfolio") return response({ status: "ok", portfolio });
    if (url === "/api/analytics") return response({ analytics });
    if (url.startsWith("/api/activity") && method === "GET") return response({
      activities: [{
        id: "activity-1", activity_type: "DIVIDEND", symbol: "ACME", trade_date: "2026-06-30",
        quantity: null, price: null, fee: null, cash_amount: "12.50", note: "Quarterly dividend",
        data_origin: "manual", created_at: "2026-07-01T12:00:00Z",
      }],
      coverage: { start: "2026-06-30", end: "2026-06-30", count: 1 },
      warnings: [], source: "Manually recorded activity ledger",
    });
    if (url === "/api/income") return response({ income: {
      period_start: "2025-09-11", period_end: "2026-09-11", source: "Manually recorded activity ledger",
      received: "12.50", withholding_tax: "0", income_by_holding: [{ symbol: "ACME", amount: "12.50" }],
      forward_annual_estimate: null, portfolio_yield: null, upcoming_distributions: [],
      coverage: { start: "2026-06-30", end: "2026-06-30", count: 1 },
      warnings: ["Income is calculated only from activities recorded in this application."],
    } });
    if (url === "/api/journal") return response({ journal });
    if (url === "/api/macro") return response(macroSnapshot);
    if (url === "/api/mcp/setup") return response({
      server_name: "investment-tracker",
      config: { mcpServers: { "investment-tracker": { command: "/repo/.venv/bin/python", args: ["-m", "app.mcp_server"], env: { PYTHONPATH: "/repo/backend", PORTFOLIO_MANAGER_SEC_USER_AGENT: "Your Name your.email@example.com" } } } },
      checks: { python: { ok: true, detail: "/repo/.venv/bin/python" }, mcp_package: { ok: true, detail: "Installed" }, sec_contact: { ok: false, detail: "Replace the placeholder with your name and email" } },
      data_folder: "/home/.portfolio-manager", config_file: "~/Library/Application Support/Claude/claude_desktop_config.json",
      read_tools: { get_quote: "Latest daily close and change" }, write_tools: { save_exit_plan: "Saves an exit plan as a proposal" },
      prompt: "Full stock analysis",
    });
    if (url === "/api/exit-plans?status=PROPOSED") return response({ plans: [proposal] });
    if (/^\/api\/market\/[^/]+\/exit-plans$/.test(url)) return response({ status: "ok", plan: { ...proposal, id: "plan-2", proposed_by: "USER", status: "ACCEPTED" } });
    if (url === "/api/research/prompts") return response({ prompts: [{
      id: "prompt-1", name: "US evidence review", prompt_text: "Use sources and as-of dates.",
      is_default: 1, created_at: "2026-09-11T12:00:00Z", updated_at: "2026-09-11T12:00:00Z",
    }] });
    if (url === "/api/research/reviews") return response({ reviews: [] });
    if (url === "/api/portfolio/status") return response(status);
    if (url === "/api/prices/capabilities") return response({
      provider: "Yahoo daily/manual", automatic_refresh_supported: false, automatic_refresh_seconds: null,
    });
    if (url === "/api/research/packs/preview") return response({ pack: {
      export_id: null, instrument_id: "instrument-1", symbol: "ACME", prompt_id: "prompt-1",
      trigger_id: null,
      privacy: { weights_only: true, include_quantities: false, include_dollar_values: false, include_account_name: false },
      markdown: "# ACME evidence review\n\nQuantity: excluded\nMissing data: adjusted total return unavailable.",
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

  async function openPortfolio() {
    fireEvent.click(await screen.findByRole("tab", { name: "Portfolio" }));
  }

  async function openPortfolioView(button: string | RegExp) {
    await openPortfolio();
    fireEvent.click(await screen.findByRole("button", { name: button }));
    return within(await screen.findByRole("dialog"));
  }

  async function openSummaryCard(label: RegExp) {
    fireEvent.click(await screen.findByRole("button", { name: label }));
    return within(await screen.findByRole("dialog"));
  }

  it("opens Research by default with a chart, market pulse and summary cards", async () => {
    vi.stubGlobal("fetch", createFetch());
    render(<App />);
    expect(await screen.findByRole("heading", { name: "SPY" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Research" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByText("SPY Synthetic Inc. · NYSE · STOCK")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "SPY daily candlestick chart, 1Y range" })).toBeInTheDocument();
    expect(screen.getByText("765.37")).toBeInTheDocument();
    const summary = within(screen.getByRole("region", { name: "Summary" }));
    for (const label of ["Trend", "Valuation", "Insiders", "Peers", "Notes", "Strategies"]) {
      expect(summary.getByText(label)).toBeInTheDocument();
    }
    expect(await summary.findByText("P/E 52.3×")).toBeInTheDocument();
    expect(summary.getByText("40th percentile of its 5 years")).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    const drawer = await openSummaryCard(/^Trend/);
    expect(await drawer.findByText("below / above / above")).toBeInTheDocument();
    expect(drawer.getByText("64.2 · neutral")).toBeInTheDocument();
    expect(drawer.getByText("1.62×")).toBeInTheDocument();
    fireEvent.keyDown(window, { key: "Escape" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(window.location.hash).toBe("#research/SPY");
  });

  it("opens tickers from the command bar and saves chart preferences", async () => {
    const fetchMock = createFetch();
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);
    await screen.findByRole("heading", { name: "SPY" });
    fireEvent.keyDown(window, { key: "k", metaKey: true });
    const search = screen.getByRole("textbox", { name: "Ticker search" });
    expect(search).toHaveFocus();
    fireEvent.change(search, { target: { value: "brk-b" } });
    fireEvent.submit(search);
    expect(await screen.findByRole("heading", { name: "BRK.B" })).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith("/api/market/BRK.B/chart?range=1Y");
    fireEvent.click(screen.getByRole("button", { name: "5Y" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith("/api/market/BRK.B/chart?range=5Y"));
    fireEvent.click(screen.getByRole("button", { name: "Line" }));
    expect(screen.getByRole("img", { name: "BRK.B daily line chart, 5Y range" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("checkbox", { name: "Bollinger" }));
    expect(JSON.parse(window.localStorage.getItem("investment-tracker.chart-prefs.v1") ?? "{}")).toMatchObject({ range: "5Y", chartType: "line", overlays: ["ema20", "ema50", "sma200", "bollinger"] });
    fireEvent.click(screen.getByRole("button", { name: "Add BRK.B to watchlist" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      "/api/watchlist", expect.objectContaining({ method: "POST", body: JSON.stringify({ symbol: "BRK.B" }) }),
    ));
  });

  it("shows SEC fundamentals, insider activity and editable peers in drawers", async () => {
    const fetchMock = createFetch();
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);
    await screen.findByText("P/E 52.3×");
    let drawer = await openSummaryCard(/^Valuation/);
    expect(drawer.getByText("Gross margin")).toBeInTheDocument();
    expect(drawer.getByText("$4.5T")).toBeInTheDocument();
    expect(drawer.getAllByText("52.3×").length).toBeGreaterThan(0);
    expect(drawer.getByText("+62.0%")).toBeInTheDocument();
    expect(drawer.getByTitle("EBITDA negative or unavailable")).toHaveTextContent("N/A");
    expect(drawer.getByRole("img", { name: "P/E 52.3×, 40th percentile of 20 quarters" })).toBeInTheDocument();
    expect(drawer.getByText(/Needs at least 8 quarters/)).toBeInTheDocument();
    expect(drawer.getByText("LATEST 10-Q · FILED Aug 5, 2026")).toHaveAttribute("href", fundamentals.latest_filing.url);
    fireEvent.click(drawer.getByRole("button", { name: "Close" }));

    drawer = await openSummaryCard(/^Insiders/);
    expect(drawer.getByText("$50K · 1 buyer")).toBeInTheDocument();
    expect(drawer.getByText("Open-market sale · 10b5-1")).toBeInTheDocument();
    expect(drawer.getByRole("link", { name: "Jane Doe" })).toHaveAttribute("href", "https://www.sec.gov/a-index.htm");
    fireEvent.click(drawer.getByRole("button", { name: "Close" }));

    drawer = await openSummaryCard(/^Peers/);
    expect(drawer.getByText("Not available (RuntimeError)")).toBeInTheDocument();
    fireEvent.click(drawer.getByRole("button", { name: "Edit peers" }));
    fireEvent.change(drawer.getByRole("textbox", { name: "Peer tickers" }), { target: { value: "tsm, umc" } });
    fireEvent.click(drawer.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      "/api/market/SPY/peers", expect.objectContaining({ method: "PUT", body: JSON.stringify({ symbols: ["TSM", "UMC"] }) }),
    ));
    expect(await drawer.findByText("YOUR LIST")).toBeInTheDocument();
    fireEvent.click(drawer.getByRole("button", { name: "AMD" }));
    expect(await screen.findByRole("heading", { name: "AMD" })).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("keeps notes pinned to the chart and records a decision for any ticker", async () => {
    chartMocks.setMarkers.mockClear();
    chartMocks.clickHandlers.length = 0;
    const fetchMock = createFetch();
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);
    expect(await screen.findByText(note.body)).toBeInTheDocument();
    await waitFor(() => expect(chartMocks.setMarkers).toHaveBeenCalledWith([
      expect.objectContaining({ time: "2026-09-15", position: "aboveBar", text: "N" }),
    ]));

    act(() => chartMocks.clickHandlers.at(-1)?.({ time: "2026-09-20" }));
    fireEvent.click(await screen.findByRole("button", { name: "Pin a note · Sep 20, 2026" }));
    const drawer = within(await screen.findByRole("dialog"));
    expect(drawer.getByText("PINNED SEP 15, 2026")).toBeInTheDocument();
    expect(drawer.getByText("Review above 140 · ACTIVE")).toBeInTheDocument();
    expect(drawer.getByLabelText("Pin note to date")).toHaveValue("2026-09-20");
    fireEvent.click(drawer.getByRole("button", { name: "Add note" }));
    expect(drawer.getByRole("alert")).toHaveTextContent("Write a note first.");
    fireEvent.change(drawer.getByRole("textbox", { name: "New note for SPY" }), { target: { value: "Breakout above 130." } });
    fireEvent.click(drawer.getByRole("button", { name: "Add note" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith("/api/market/SPY/notes", expect.objectContaining({
      method: "POST", body: JSON.stringify({ body: "Breakout above 130.", pinned_date: "2026-09-20" }),
    })));

    fireEvent.change(drawer.getByRole("combobox", { name: "My decision for SPY" }), { target: { value: "CONSIDER_ADD" } });
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith("/api/market/SPY/decision", expect.objectContaining({ method: "POST" })));
    expect(await drawer.findByRole("combobox", { name: "My decision for SPY" })).toHaveValue("CONSIDER_ADD");

    fireEvent.click(drawer.getByRole("button", { name: "Delete note from Sep 16, 2026" }));
    fireEvent.click(drawer.getByRole("button", { name: "Confirm delete" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith("/api/notes/note-1", expect.objectContaining({ method: "DELETE" })));
  });

  it("explains when SEC EDGAR is not configured", async () => {
    const fetchMock = createFetch();
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => (
      String(input).endsWith("/fundamentals")
        ? response({ detail: "SEC EDGAR needs a contact. Set PORTFOLIO_MANAGER_SEC_USER_AGENT to your name and email." }, 503)
        : fetchMock(input, init)
    )));
    render(<App />);
    expect(await screen.findByText(/Set PORTFOLIO_MANAGER_SEC_USER_AGENT/)).toBeInTheDocument();
  });

  it("explains when a ticker cannot be loaded, including old Terminal links", async () => {
    vi.stubGlobal("fetch", createFetch());
    window.history.replaceState({}, "", "/#terminal/NOPE");
    render(<App />);
    expect(await screen.findByRole("alert")).toHaveTextContent("NOPE was not found");
    expect(screen.getByText("NOPE is unavailable")).toBeInTheDocument();
    expect(window.location.hash).toBe("#research/NOPE");
  });

  it("summarizes the portfolio and opens detail views as drawers", async () => {
    const onOpen = createFetch();
    vi.stubGlobal("fetch", onOpen);
    render(<App />);
    await openPortfolio();
    expect(await screen.findByText("Portfolio value")).toBeInTheDocument();
    expect(screen.getByText("Manual portfolio")).toBeInTheDocument();
    expect(screen.getByText(/1 holdings · as of/)).toBeInTheDocument();
    expect(screen.getAllByText("$100.00").length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole("button", { name: "ACME details" }));
    const position = within(await screen.findByRole("dialog"));
    expect(position.getByText("Market value")).toBeInTheDocument();
    fireEvent.click(position.getByRole("button", { name: "Open in Research" }));
    expect(await screen.findByRole("heading", { name: "ACME" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Research" })).toHaveAttribute("aria-selected", "true");

    const income = await openPortfolioView("Income");
    expect(income.getAllByRole("heading", { name: "Income" }).length).toBeGreaterThan(0);
    expect(window.location.hash).toBe("#portfolio/income");
    expect(screen.queryByText(/place order/i)).not.toBeInTheDocument();
  });

  it("provides all analytics views without fabricating unavailable returns or risk", async () => {
    vi.stubGlobal("fetch", createFetch());
    render(<App />);
    const drawer = await openPortfolioView("Analytics");
    const tabs = drawer.getByRole("tablist", { name: "Analytics views" });
    for (const name of ["Diversification", "Performance", "Risk", "ETF look-through"]) {
      expect(within(tabs).getByRole("tab", { name })).toBeInTheDocument();
    }
    fireEvent.click(within(tabs).getByRole("tab", { name: "Performance" }));
    expect(drawer.getAllByText(/INSUFFICIENT TRANSACTION HISTORY/).length).toBeGreaterThan(0);
    expect(drawer.getByText(/current holdings are not backfilled/i)).toBeInTheDocument();
    fireEvent.click(within(tabs).getByRole("tab", { name: "Risk" }));
    expect(drawer.getByText("Historical risk · not a forecast")).toBeInTheDocument();
    fireEvent.click(within(tabs).getByRole("tab", { name: "ETF look-through" }));
    expect(drawer.getByText(/verified constituent holdings are not stored/)).toBeInTheDocument();
    expect(drawer.getByText("NO BROAD AUTOMATIC SUPPORT CLAIM")).toBeInTheDocument();
  });

  it("keeps the holdings worksheet configurable and confirms keyboard row deletion locally", async () => {
    const fetchMock = createFetch();
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);
    const drawer = await openPortfolioView("Edit holdings");
    expect(drawer.queryByRole("columnheader", { name: "Account" })).not.toBeInTheDocument();
    expect(drawer.getByRole("combobox", { name: "Sector for ACME" })).toBeInTheDocument();
    expect(drawer.getByRole("combobox", { name: "My decision for ACME" })).toHaveValue("WATCH");
    fireEvent.click(drawer.getByText(/COLUMNS \d+\/\d+/));
    fireEvent.click(drawer.getByRole("checkbox", { name: "Account" }));
    expect(drawer.getByRole("columnheader", { name: "Account" })).toBeInTheDocument();
    expect(window.localStorage.getItem("portfolio-manager.visible-columns.v2")).toContain("account");
    const rowButton = drawer.getByRole("button", { name: "Select row 1: ACME" });
    fireEvent.click(rowButton);
    fireEvent.keyDown(rowButton, { key: "Delete" });
    const confirm = await screen.findByRole("alertdialog");
    expect(confirm).toHaveTextContent("It is not a sale");
    expect(confirm).toHaveTextContent("never contacts a brokerage");
    fireEvent.click(within(confirm).getByRole("button", { name: "DELETE LOCAL ROW" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      "/api/portfolio/positions/position-1", expect.objectContaining({ method: "DELETE" }),
    ));
  });

  it("separates decisions, Claude suggestions, thesis data and review-only triggers", async () => {
    const fetchMock = createFetch();
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);
    const drawer = await openPortfolioView(/^Alerts/);
    expect(drawer.getByText("MY DECISION ≠ CLAUDE SUGGESTION")).toBeInTheDocument();
    expect(drawer.getByRole("combobox", { name: "My decision for ACME" })).toHaveValue("WATCH");
    expect(drawer.getByText("Manual Claude workflow only")).toBeInTheDocument();
    expect(drawer.getByRole("combobox", { name: "Portfolio role" })).toBeInTheDocument();
    expect(drawer.getByRole("combobox", { name: "Thesis strength" })).toBeInTheDocument();
    expect(drawer.getByRole("combobox", { name: "Trigger condition" })).toBeInTheDocument();
    fireEvent.change(drawer.getByRole("textbox", { name: "Decision reason" }), {
      target: { value: "Revisit after the next evidence update" },
    });
    fireEvent.change(drawer.getByRole("combobox", { name: "Claude suggestion response" }), {
      target: { value: "CONSIDERING" },
    });
    fireEvent.change(drawer.getByLabelText("Decision review due date"), {
      target: { value: "2026-10-15" },
    });
    fireEvent.click(drawer.getByRole("button", { name: "RECORD DECISION" }));
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
    expect(drawer.getByText("REVIEW ONLY · NEVER AN ORDER")).toBeInTheDocument();
    expect(drawer.getByText(/never contacts? Claude or a brokerage/i)).toBeInTheDocument();
  });

  it("previews a weights-only Claude review pack without sending data to Claude", async () => {
    vi.stubGlobal("fetch", createFetch());
    render(<App />);
    const drawer = await openPortfolioView("AI review packs");
    fireEvent.change(drawer.getByRole("combobox", { name: "Research holding" }), {
      target: { value: "instrument-1" },
    });
    fireEvent.click(drawer.getByRole("button", { name: "PREVIEW EXACT MARKDOWN" }));
    expect(await drawer.findByText(/# ACME evidence review/)).toBeInTheDocument();
    expect(drawer.getByLabelText("Claude review pack Markdown preview")).toHaveTextContent("Quantity: excluded");
    expect(drawer.getByText(/no Claude API connection/i)).toBeInTheDocument();
    expect(drawer.getByText("STORED SEPARATELY FROM MY DECISION")).toBeInTheDocument();
  });

  it("records activities in the local ledger and confirms deletion", async () => {
    const fetchMock = createFetch();
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);
    const drawer = await openPortfolioView("Activity");
    expect(drawer.getByText("NO ORDER ACTIONS AVAILABLE")).toBeInTheDocument();
    expect(drawer.getByText("Quarterly dividend")).toBeInTheDocument();
    expect(drawer.getByText("$12.50")).toBeInTheDocument();
    expect(drawer.getByText("Jun 30, 2026")).toBeInTheDocument();
    fireEvent.change(drawer.getByRole("combobox", { name: "New activity type" }), { target: { value: "DEPOSIT" } });
    fireEvent.change(drawer.getByLabelText("New activity date"), { target: { value: "2026-09-01" } });
    fireEvent.change(drawer.getByRole("textbox", { name: "New activity cash amount" }), { target: { value: "500" } });
    fireEvent.click(drawer.getByRole("button", { name: "RECORD ACTIVITY" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      "/api/activity",
      expect.objectContaining({ method: "POST", body: expect.stringContaining('"activity_type":"DEPOSIT"') }),
    ));
    fireEvent.click(drawer.getByRole("button", { name: "Delete DIVIDEND ACME 2026-06-30" }));
    fireEvent.click(within(await screen.findByRole("alertdialog")).getByRole("button", { name: "DELETE ACTIVITY" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      "/api/activity/activity-1", expect.objectContaining({ method: "DELETE" }),
    ));
    expect(screen.queryByRole("button", { name: /buy|sell|order/i })).not.toBeInTheDocument();
  });

  it("adds a position from the holdings form and prefills it when a row is selected", async () => {
    const fetchMock = createFetch();
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);
    const drawer = await openPortfolioView("Edit holdings");
    fireEvent.change(drawer.getByRole("textbox", { name: "Position symbol" }), { target: { value: "voo" } });
    fireEvent.change(drawer.getByRole("textbox", { name: "Position quantity" }), { target: { value: "3" } });
    fireEvent.change(drawer.getByRole("textbox", { name: "Position average cost" }), { target: { value: "410.5" } });
    fireEvent.click(drawer.getByRole("button", { name: "SAVE POSITION" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      "/api/portfolio/positions",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ symbol: "voo", quantity: "3", average_cost: "410.5", account_name: "Brokerage" }),
      }),
    ));
    fireEvent.click(drawer.getByRole("button", { name: "Select row 1: ACME" }));
    expect(drawer.getByRole("textbox", { name: "Position symbol" })).toHaveValue("ACME");
    expect(drawer.getByRole("textbox", { name: "Position quantity" })).toHaveValue("2");
    expect(drawer.getByRole("button", { name: "SAVE CHANGES" })).toBeInTheDocument();
  });

  it("shows portfolio data controls and loads the demo only after confirmation", async () => {
    const fetchMock = createFetch({ "GET /api/portfolio/status": { data_origin: null, snapshot_count: 0, latest_snapshot_at: null } });
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);
    const drawer = await openPortfolioView("Settings");
    expect(drawer.getAllByText("No portfolio").length).toBeGreaterThan(0);
    expect(drawer.getByText(/Yahoo daily\/manual · separate from holdings/)).toBeInTheDocument();
    fireEvent.click(drawer.getByRole("button", { name: "VIEW HISTORY" }));
    expect(drawer.getByText("NO HISTORICAL VALUATION SNAPSHOTS")).toBeInTheDocument();
    expect(drawer.getByRole("button", { name: "DELETE LOCAL DATA" })).toBeInTheDocument();
    fireEvent.click(drawer.getByRole("button", { name: "LOAD DEMO" }));
    const dialog = await screen.findByRole("alertdialog");
    expect(dialog).toHaveTextContent("Manual portfolios are never overwritten");
    expect(fetchMock).not.toHaveBeenCalledWith("/api/portfolio/demo", expect.anything());
    fireEvent.click(within(dialog).getByRole("button", { name: "LOAD DEMO" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      "/api/portfolio/demo",
      expect.objectContaining({ method: "POST", body: JSON.stringify({ confirm: "LOAD DEMO" }) }),
    ));
  });
  it("reviews Claude's exit-plan proposal, draws its levels and accepts it only on request", async () => {
    chartMocks.priceLines.length = 0;
    const fetchMock = createFetch();
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);
    const button = await screen.findByRole("button", { name: "Exit plan · 1 proposal" });
    await waitFor(() => expect(chartMocks.priceLines.map((line) => line.title)).toEqual(
      ["Target", "Stop", "Target · proposed", "Stop · proposed"],
    ));
    expect(chartMocks.priceLines.map((line) => line.price)).toEqual([780, 720, 800, 700]);
    expect(fetchMock).not.toHaveBeenCalledWith("/api/exit-plans/plan-1/accept", expect.anything());

    fireEvent.click(button);
    const drawer = within(await screen.findByRole("dialog"));
    const card = within(drawer.getByRole("article", { name: "SPY exit plan, proposed" }));
    expect(card.getByText("Proposed by Claude")).toBeInTheDocument();
    expect(card.getByText(proposal.reasoning)).toBeInTheDocument();
    expect(card.getByText("Proposed when the close was 765.37 (Sep 30, 2026)")).toBeInTheDocument();
    expect(drawer.getByRole("article", { name: "SPY exit plan, accepted" })).toHaveTextContent("My plan");
    fireEvent.click(card.getByRole("button", { name: "Accept" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      "/api/exit-plans/plan-1/accept", expect.objectContaining({ method: "POST" }),
    ));

    fireEvent.click(drawer.getByRole("button", { name: "Replace with my own plan" }));
    fireEvent.click(drawer.getByRole("button", { name: "Save my plan" }));
    expect(drawer.getByRole("alert")).toHaveTextContent("Write down why these levels matter.");
    fireEvent.change(drawer.getByRole("textbox", { name: "Exit plan target price" }), { target: { value: "820" } });
    fireEvent.change(drawer.getByRole("textbox", { name: "Exit plan reasoning" }), { target: { value: "My level." } });
    fireEvent.click(drawer.getByRole("button", { name: "Save my plan" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith("/api/market/SPY/exit-plans", expect.objectContaining({
      method: "POST", body: JSON.stringify({ target_price: "820", stop_price: null, review_date: null, reasoning: "My level." }),
    })));
  });

  it("lists exit-plan proposals in the Portfolio review queue", async () => {
    const fetchMock = createFetch();
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);
    const drawer = await openPortfolioView("Alerts · 1");
    const queue = within(drawer.getByRole("region", { name: "Review queue" }));
    expect(queue.getByText("Exit plans waiting for review · 1")).toBeInTheDocument();
    fireEvent.click(queue.getByRole("button", { name: "Reject" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      "/api/exit-plans/plan-1/reject", expect.objectContaining({ method: "POST" }),
    ));
    expect(await screen.findByText(/exit plan rejected and kept in its history/)).toBeInTheDocument();
  });
  it("opens MCP setup instructions with this computer's paths", async () => {
    vi.stubGlobal("fetch", createFetch());
    const writeText = vi.fn(async () => undefined);
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    render(<App />);
    fireEvent.click(await screen.findByRole("button", { name: "MCP Server" }));
    const drawer = within(await screen.findByRole("dialog", { name: "MCP Server" }));
    const config = await drawer.findByLabelText("Claude Desktop configuration");
    expect(config).toHaveTextContent('"command": "/repo/.venv/bin/python"');
    expect(config).toHaveTextContent('"PYTHONPATH": "/repo/backend"');
    expect(drawer.getByText(/Needs attention · Replace the placeholder/)).toBeInTheDocument();
    expect(drawer.getByText("save_exit_plan")).toBeInTheDocument();
    fireEvent.click(drawer.getByRole("button", { name: "Copy" }));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith(expect.stringContaining('"app.mcp_server"')));
    expect(await drawer.findByRole("button", { name: "Copied" })).toBeInTheDocument();
  });
  it("summarizes headline sentiment and lists headlines and 8-K filings", async () => {
    vi.stubGlobal("fetch", createFetch());
    render(<App />);
    const summary = within(await screen.findByRole("region", { name: "Summary" }));
    expect(await summary.findByText("Mixed +0.07")).toBeInTheDocument();
    expect(summary.getByText("2 headlines in 7 days · 1 8-K")).toBeInTheDocument();
    const drawer = await openSummaryCard(/^News/);
    expect(drawer.getByText("1 positive · 0 neutral · 1 negative")).toBeInTheDocument();
    expect(drawer.getByRole("img", { name: /Daily headline sentiment/ })).toHaveAccessibleName(expect.stringContaining("+0.85"));
    expect(drawer.getByRole("link", { name: "Synthetic Inc. posts record margin" })).toHaveAttribute("href", "https://example.com/n1");
    expect(drawer.getByText("positive +0.85")).toBeInTheDocument();
    expect(drawer.getByText("negative −0.70")).toBeInTheDocument();
    expect(drawer.getByRole("link", { name: "8-K: Earnings results" })).toBeInTheDocument();
    expect(drawer.getByText(/not a signal/)).toBeInTheDocument();
  });
  it("shows world news by theme, upcoming reports and the latest data in the Macro drawer", async () => {
    vi.stubGlobal("fetch", createFetch());
    render(<App />);
    fireEvent.click(await screen.findByRole("button", { name: "Macro" }));
    const drawer = within(await screen.findByRole("dialog", { name: "Macro" }));
    const world = within(await drawer.findByRole("region", { name: "This week in the world" }));
    expect(world.getByText("Your holdings: XOM · 6.3%")).toBeInTheDocument();
    expect(world.queryByText("Trade and tariffs")).not.toBeInTheDocument();
    expect(world.getAllByRole("link")).toHaveLength(2);
    fireEvent.click(world.getByRole("button", { name: /War and geopolitics/ }));
    expect(world.getAllByRole("link").map((link) => link.textContent)).toEqual(["Oil jumps as Iran conflict threatens supply"]);

    const calendar = within(drawer.getByRole("region", { name: "Coming up" }));
    expect(calendar.getByText("Fed rate decision (FOMC)")).toBeInTheDocument();
    expect(calendar.getAllByText("High impact")).toHaveLength(2);

    const data = within(drawer.getByRole("region", { name: "Latest data" }));
    expect(data.getByText("4.1%")).toBeInTheDocument();
    expect(data.getByText(/vs prior · October 2026/)).toBeInTheDocument();
    expect(data.getByText("Inverted")).toBeInTheDocument();
    expect(data.getByText(/Not available · FRED returned HTTP 500/)).toBeInTheDocument();
  });
});
