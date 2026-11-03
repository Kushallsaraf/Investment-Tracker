import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";

const chartMocks = vi.hoisted(() => ({
  setMarkers: vi.fn(),
  clickHandlers: [] as Array<(param: { time?: string }) => void>,
}));

vi.mock("lightweight-charts", () => {
  const series = () => ({ setData: vi.fn(), createPriceLine: vi.fn(), priceScale: () => ({ applyOptions: vi.fn() }) });
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
function journalFor(symbol: string, decision: string | null = null) {
  return {
    symbol, instrument_id: decision ? "instrument-9" : null,
    decision: decision ? { instrument_id: "instrument-9", symbol, decision, reason: "", decision_date: "2026-10-20", review_due_date: null, updated_at: "2026-10-20T00:00:00Z" } : null,
    triggers: [{ id: "trigger-1", instrument_id: "instrument-9", symbol, trigger_type: "PRICE_ABOVE", lower_value: null, upper_value: "140", trigger_date: null, note: "", reason: "", expires_at: null, state: "ACTIVE", created_at: "2026-10-20T00:00:00Z", triggered_at: null, observed_value: null, quote_source: null, quote_timestamp: null, frozen_holding_snapshot_id: null, frozen_valuation_snapshot_id: null }],
    notes: symbol === "SPY" ? [note] : [],
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

  it("opens the terminal by default with a chart, market strip and technical setup", async () => {
    vi.stubGlobal("fetch", createFetch());
    render(<App />);
    expect(await screen.findByRole("heading", { name: "SPY" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Terminal" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByText("SPY Synthetic Inc. · NYSE · STOCK")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "SPY daily candlestick chart, 1Y range" })).toBeInTheDocument();
    expect(screen.getByText("765.37")).toBeInTheDocument();
    expect(await screen.findByText("below / above / above")).toBeInTheDocument();
    expect(screen.getByText("64.2 · neutral")).toBeInTheDocument();
    expect(screen.getByText("1.62×")).toBeInTheDocument();
    for (const title of ["AI analyst", "Strategy scanner", "Fundamentals", "News and sentiment", "Insider activity", "Peers", "Macro and markets"]) {
      expect(screen.getByRole("heading", { name: title })).toBeInTheDocument();
    }
    expect(screen.getAllByText("Not connected yet")).toHaveLength(4);
    expect(window.location.hash).toBe("#terminal/SPY");
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
    expect(JSON.parse(window.localStorage.getItem("investment-tracker.chart-prefs.v1") ?? "{}")).toMatchObject({ range: "5Y", chartType: "line" });
    fireEvent.click(screen.getByRole("button", { name: "☆ WATCH" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      "/api/watchlist", expect.objectContaining({ method: "POST", body: JSON.stringify({ symbol: "BRK.B" }) }),
    ));
  });

  it("shows SEC fundamentals, insider activity and editable peers", async () => {
    const fetchMock = createFetch();
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);
    await screen.findByText("Gross margin");
    const fundamentalsPanel = within(screen.getByRole("heading", { name: "Fundamentals" }).closest("section") as HTMLElement);
    expect(fundamentalsPanel.getByText("$4.5T")).toBeInTheDocument();
    expect(fundamentalsPanel.getAllByText("52.3×").length).toBeGreaterThan(0);
    expect(fundamentalsPanel.getByText("+62.0%")).toBeInTheDocument();
    expect(fundamentalsPanel.getByTitle("EBITDA negative or unavailable")).toHaveTextContent("N/A");
    expect(screen.getByRole("img", { name: "P/E 52.3×, 40th percentile of 20 quarters" })).toBeInTheDocument();
    expect(screen.getByText(/Needs at least 8 quarters/)).toBeInTheDocument();
    expect(screen.getByText("LATEST 10-Q · FILED Aug 5, 2026")).toHaveAttribute("href", fundamentals.latest_filing.url);
    expect(screen.getByText("$50K · 1 buyer")).toBeInTheDocument();
    expect(screen.getByText("Open-market sale · 10b5-1")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Jane Doe" })).toHaveAttribute("href", "https://www.sec.gov/a-index.htm");
    expect(screen.getByText("Not available (RuntimeError)")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "EDIT PEERS" }));
    fireEvent.change(screen.getByRole("textbox", { name: "Peer tickers" }), { target: { value: "tsm, umc" } });
    fireEvent.click(screen.getByRole("button", { name: "SAVE" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      "/api/market/SPY/peers", expect.objectContaining({ method: "PUT", body: JSON.stringify({ symbols: ["TSM", "UMC"] }) }),
    ));
    expect(await screen.findByText("YOUR LIST")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "AMD" }));
    expect(await screen.findByRole("heading", { name: "AMD" })).toBeInTheDocument();
  });

  it("keeps notes pinned to the chart and records a decision for any ticker", async () => {
    chartMocks.setMarkers.mockClear();
    chartMocks.clickHandlers.length = 0;
    const fetchMock = createFetch();
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);
    expect(await screen.findByText(note.body)).toBeInTheDocument();
    expect(screen.getByText("PINNED SEP 15, 2026")).toBeInTheDocument();
    expect(screen.getByText("Review above 140 · ACTIVE")).toBeInTheDocument();
    await waitFor(() => expect(chartMocks.setMarkers).toHaveBeenCalledWith([
      expect.objectContaining({ time: "2026-09-15", position: "aboveBar", text: "N" }),
    ]));

    act(() => chartMocks.clickHandlers.at(-1)?.({ time: "2026-09-20" }));
    expect(await screen.findByLabelText("Pin note to date")).toHaveValue("2026-09-20");
    fireEvent.click(screen.getByRole("button", { name: "ADD NOTE" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Write a note first.");
    fireEvent.change(screen.getByRole("textbox", { name: "New note for SPY" }), { target: { value: "Breakout above 130." } });
    fireEvent.click(screen.getByRole("button", { name: "ADD NOTE" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith("/api/market/SPY/notes", expect.objectContaining({
      method: "POST", body: JSON.stringify({ body: "Breakout above 130.", pinned_date: "2026-09-20" }),
    })));

    fireEvent.change(screen.getByRole("combobox", { name: "My decision for SPY" }), { target: { value: "CONSIDER_ADD" } });
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith("/api/market/SPY/decision", expect.objectContaining({ method: "POST" })));
    expect(await screen.findByRole("combobox", { name: "My decision for SPY" })).toHaveValue("CONSIDER_ADD");

    fireEvent.click(screen.getByRole("button", { name: "Delete note from Sep 16, 2026" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm delete" }));
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

  it("explains when a ticker cannot be loaded", async () => {
    vi.stubGlobal("fetch", createFetch());
    window.history.replaceState({}, "", "/#terminal/NOPE");
    render(<App />);
    expect(await screen.findByRole("alert")).toHaveTextContent("NOPE was not found");
    expect(screen.getByText("NOPE is unavailable")).toBeInTheDocument();
  });

  it("keeps the portfolio views under the Portfolio tab with explicit evidence states", async () => {
    vi.stubGlobal("fetch", createFetch());
    render(<App />);
    await openPortfolio();
    expect(await screen.findByRole("heading", { name: "Portfolio dashboard" })).toBeInTheDocument();
    const nav = screen.getByRole("tablist", { name: "Portfolio views" });
    for (const name of ["Overview", "Holdings", "Analytics", "Income", "Activity", "Decisions", "Research", "Settings"]) {
      expect(within(nav).getByRole("tab", { name })).toBeInTheDocument();
    }
    expect(screen.getByText("MANUAL PORTFOLIO")).toBeInTheDocument();
    expect(screen.getByText(/Manual portfolio · 1 holdings · USD reporting/)).toBeInTheDocument();
    expect(screen.getAllByText("$100.00").length).toBeGreaterThan(0);
    expect(screen.getByText("Today’s change").nextElementSibling).toHaveTextContent("NOT AVAILABLE");
    fireEvent.click(within(nav).getByRole("tab", { name: "Income" }));
    expect(screen.getByRole("heading", { name: "Income" })).toBeInTheDocument();
    expect(window.localStorage.getItem("investment-tracker.portfolio-view.v1")).toBe("Income");
    expect(window.location.hash).toBe("#portfolio/income");
    expect(screen.queryByText(/place order/i)).not.toBeInTheDocument();
  });

  it("provides all analytics views without fabricating unavailable returns or risk", async () => {
    vi.stubGlobal("fetch", createFetch());
    render(<App />);
    await openPortfolio();
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
    fireEvent.click(within(tabs).getByRole("tab", { name: "ETF look-through" }));
    expect(screen.getByText(/verified constituent holdings are not stored/)).toBeInTheDocument();
    expect(screen.getByText("NO BROAD AUTOMATIC SUPPORT CLAIM")).toBeInTheDocument();
  });

  it("keeps the holdings worksheet configurable and confirms keyboard row deletion locally", async () => {
    const fetchMock = createFetch();
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);
    await openPortfolio();
    fireEvent.click(await screen.findByRole("tab", { name: "Holdings" }));
    expect(screen.queryByRole("columnheader", { name: "Account" })).not.toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Sector for ACME" })).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "My decision for ACME" })).toHaveValue("WATCH");
    fireEvent.click(screen.getByText(/COLUMNS \d+\/\d+/));
    fireEvent.click(screen.getByRole("checkbox", { name: "Account" }));
    expect(screen.getByRole("columnheader", { name: "Account" })).toBeInTheDocument();
    expect(window.localStorage.getItem("portfolio-manager.visible-columns.v2")).toContain("account");
    const rowButton = screen.getByRole("button", { name: "Select row 1: ACME" });
    fireEvent.click(rowButton);
    fireEvent.keyDown(rowButton, { key: "Delete" });
    expect(await screen.findByRole("dialog")).toHaveTextContent("It is not a sale");
    expect(screen.getByRole("dialog")).toHaveTextContent("never contacts a brokerage");
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "DELETE LOCAL ROW" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      "/api/portfolio/positions/position-1", expect.objectContaining({ method: "DELETE" }),
    ));
  });

  it("separates decisions, Claude suggestions, thesis data and review-only triggers", async () => {
    const fetchMock = createFetch();
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);
    await openPortfolio();
    fireEvent.click(await screen.findByRole("tab", { name: "Decisions" }));
    expect(screen.getByText("MY DECISION ≠ CLAUDE SUGGESTION")).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "My decision for ACME" })).toHaveValue("WATCH");
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
    await openPortfolio();
    fireEvent.click(await screen.findByRole("tab", { name: "Research" }));
    fireEvent.change(screen.getByRole("combobox", { name: "Research holding" }), {
      target: { value: "instrument-1" },
    });
    fireEvent.click(screen.getByRole("button", { name: "PREVIEW EXACT MARKDOWN" }));
    expect(await screen.findByText(/# ACME evidence review/)).toBeInTheDocument();
    expect(screen.getByLabelText("Claude review pack Markdown preview")).toHaveTextContent("Quantity: excluded");
    expect(screen.getByText(/no Claude API connection/i)).toBeInTheDocument();
    expect(screen.getByText("STORED SEPARATELY FROM MY DECISION")).toBeInTheDocument();
  });

  it("records activities in the local ledger and confirms deletion", async () => {
    const fetchMock = createFetch();
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);
    await openPortfolio();
    fireEvent.click(await screen.findByRole("tab", { name: "Activity" }));
    expect(screen.getByText("NO ORDER ACTIONS AVAILABLE")).toBeInTheDocument();
    expect(screen.getByText("Quarterly dividend")).toBeInTheDocument();
    expect(screen.getByText("$12.50")).toBeInTheDocument();
    expect(screen.getByText("Jun 30, 2026")).toBeInTheDocument();
    fireEvent.change(screen.getByRole("combobox", { name: "New activity type" }), { target: { value: "DEPOSIT" } });
    fireEvent.change(screen.getByLabelText("New activity date"), { target: { value: "2026-09-01" } });
    fireEvent.change(screen.getByRole("textbox", { name: "New activity cash amount" }), { target: { value: "500" } });
    fireEvent.click(screen.getByRole("button", { name: "RECORD ACTIVITY" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      "/api/activity",
      expect.objectContaining({ method: "POST", body: expect.stringContaining('"activity_type":"DEPOSIT"') }),
    ));
    fireEvent.click(screen.getByRole("button", { name: "Delete DIVIDEND ACME 2026-06-30" }));
    fireEvent.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "DELETE ACTIVITY" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      "/api/activity/activity-1", expect.objectContaining({ method: "DELETE" }),
    ));
    expect(screen.queryByRole("button", { name: /buy|sell|order/i })).not.toBeInTheDocument();
  });

  it("adds a position from the holdings form and prefills it when a row is selected", async () => {
    const fetchMock = createFetch();
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);
    await openPortfolio();
    fireEvent.click(await screen.findByRole("tab", { name: "Holdings" }));
    fireEvent.change(screen.getByRole("textbox", { name: "Position symbol" }), { target: { value: "voo" } });
    fireEvent.change(screen.getByRole("textbox", { name: "Position quantity" }), { target: { value: "3" } });
    fireEvent.change(screen.getByRole("textbox", { name: "Position average cost" }), { target: { value: "410.5" } });
    fireEvent.click(screen.getByRole("button", { name: "SAVE POSITION" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      "/api/portfolio/positions",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ symbol: "voo", quantity: "3", average_cost: "410.5", account_name: "Brokerage" }),
      }),
    ));
    fireEvent.click(screen.getByRole("button", { name: "Select row 1: ACME" }));
    expect(screen.getByRole("textbox", { name: "Position symbol" })).toHaveValue("ACME");
    expect(screen.getByRole("textbox", { name: "Position quantity" })).toHaveValue("2");
    expect(screen.getByRole("button", { name: "SAVE CHANGES" })).toBeInTheDocument();
  });

  it("shows portfolio data controls and loads the demo only after confirmation", async () => {
    const fetchMock = createFetch({ "GET /api/portfolio/status": { data_origin: null, snapshot_count: 0, latest_snapshot_at: null } });
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);
    await openPortfolio();
    fireEvent.click(await screen.findByRole("tab", { name: "Settings" }));
    expect(screen.getAllByText("NO PORTFOLIO").length).toBeGreaterThan(0);
    expect(screen.getByText(/Yahoo daily\/manual · separate from holdings/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "VIEW HISTORY" }));
    expect(screen.getByText("NO HISTORICAL VALUATION SNAPSHOTS")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "DELETE LOCAL DATA" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "LOAD DEMO" }));
    const dialog = await screen.findByRole("dialog");
    expect(dialog).toHaveTextContent("Manual portfolios are never overwritten");
    expect(fetchMock).not.toHaveBeenCalledWith("/api/portfolio/demo", expect.anything());
    fireEvent.click(within(dialog).getByRole("button", { name: "LOAD DEMO" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      "/api/portfolio/demo",
      expect.objectContaining({ method: "POST", body: JSON.stringify({ confirm: "LOAD DEMO" }) }),
    ));
  });
});
