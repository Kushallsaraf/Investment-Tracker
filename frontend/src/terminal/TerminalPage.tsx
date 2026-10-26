import { useCallback, useEffect, useState } from "react";
import { addToWatchlist, getChart, getTechnicals, getWatchlist, removeFromWatchlist } from "../api";
import { DataPanel } from "../components/ui";
import { dateOnly, price, signedPercent, timestamp } from "../lib/format";
import type { ChartPayload, ChartRange, Technicals, WatchlistItem } from "../types";
import { type ChartType, type LowerPane, type Overlay, OVERLAY_LABELS, PriceChart } from "./PriceChart";

const RANGES: ChartRange[] = ["1M", "3M", "6M", "1Y", "5Y", "MAX"];
const OVERLAYS = Object.keys(OVERLAY_LABELS) as Overlay[];
const CHART_PREFS_KEY = "investment-tracker.chart-prefs.v1";

type ChartPrefs = { range: ChartRange; chartType: ChartType; overlays: Overlay[]; lowerPane: LowerPane };
const DEFAULT_PREFS: ChartPrefs = { range: "1Y", chartType: "candle", overlays: ["ema20", "ema50", "sma200"], lowerPane: "rsi" };

function loadPrefs(): ChartPrefs {
  try {
    const stored = JSON.parse(window.localStorage.getItem(CHART_PREFS_KEY) ?? "null");
    if (stored && typeof stored === "object") {
      return {
        range: RANGES.includes(stored.range) ? stored.range : DEFAULT_PREFS.range,
        chartType: stored.chartType === "line" ? "line" : "candle",
        overlays: Array.isArray(stored.overlays) ? stored.overlays.filter((item: Overlay) => OVERLAYS.includes(item)) : DEFAULT_PREFS.overlays,
        lowerPane: ["rsi", "macd", "none"].includes(stored.lowerPane) ? stored.lowerPane : DEFAULT_PREFS.lowerPane,
      };
    }
  } catch {
    // Invalid or unavailable storage falls back to defaults.
  }
  return DEFAULT_PREFS;
}

function tone(value: number | null | undefined): string {
  if (value == null) return "";
  return value >= 0 ? "positive" : "negative";
}

export function TerminalPage({ symbol, onOpenSymbol }: { symbol: string; onOpenSymbol: (symbol: string) => void }) {
  const [prefs, setPrefs] = useState<ChartPrefs>(loadPrefs);
  const [chart, setChart] = useState<{ symbol: string; payload: ChartPayload } | null>(null);
  const [technicals, setTechnicals] = useState<Technicals | null>(null);
  const [watchlist, setWatchlist] = useState<WatchlistItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  function updatePrefs(next: Partial<ChartPrefs>) {
    setPrefs((current) => {
      const merged = { ...current, ...next };
      try {
        window.localStorage.setItem(CHART_PREFS_KEY, JSON.stringify(merged));
      } catch {
        // Preferences are optional.
      }
      return merged;
    });
  }

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    getChart(symbol, prefs.range)
      .then((payload) => { if (!cancelled) setChart({ symbol, payload }); })
      .catch((cause) => {
        if (cancelled) return;
        setChart(null);
        setError(cause instanceof Error ? cause.message : `Unable to load ${symbol}`);
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [symbol, prefs.range]);

  useEffect(() => {
    let cancelled = false;
    setTechnicals(null);
    getTechnicals(symbol)
      .then((payload) => { if (!cancelled) setTechnicals(payload); })
      .catch(() => undefined);
    return () => { cancelled = true; };
  }, [symbol]);

  const loadWatchlist = useCallback(() => {
    void getWatchlist().then(setWatchlist).catch(() => setWatchlist([]));
  }, []);
  useEffect(loadWatchlist, [loadWatchlist]);

  const shown = chart?.symbol === symbol ? chart.payload : null;
  const onWatchlist = Boolean(shown && watchlist?.some((item) => item.symbol === shown.symbol));

  async function toggleWatchlist() {
    if (!shown) return;
    try {
      if (onWatchlist) await removeFromWatchlist(shown.symbol);
      else await addToWatchlist(shown.symbol);
      loadWatchlist();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Watchlist update failed");
    }
  }

  return (
    <div className="terminal">
      <div className="terminal-main">
        <WatchlistPanel items={watchlist} active={shown?.symbol ?? symbol} onOpen={onOpenSymbol} onRemove={(item) => void removeFromWatchlist(item).then(loadWatchlist).catch(() => setError("Watchlist update failed"))} />
        <section className="data-panel chart-panel" aria-label={`${symbol} chart`}>
          <div className="chart-header">
            <div className="chart-title">
              <h2>{shown?.symbol ?? symbol}</h2>
              <span>{shown ? `${shown.name} · ${shown.exchange} · ${shown.asset_type}` : loading ? "Loading…" : "Not available"}</span>
            </div>
            {shown && (
              <div className="chart-quote">
                <strong>{price(shown.quote.last)}</strong>
                <span className={tone(shown.quote.change)}>{shown.quote.change == null ? "—" : `${shown.quote.change >= 0 ? "+" : ""}${price(shown.quote.change)}`} · {signedPercent(shown.quote.change_pct)}</span>
                <small>Close {dateOnly(shown.quote.as_of)}{shown.stale ? " · STALE" : ""}</small>
              </div>
            )}
            <button className="action" type="button" disabled={!shown} onClick={() => void toggleWatchlist()}>{onWatchlist ? "★ WATCHING" : "☆ WATCH"}</button>
          </div>
          <div className="chart-toolbar">
            <fieldset className="segmented" aria-label="Chart range">
              {RANGES.map((range) => <button type="button" key={range} aria-pressed={prefs.range === range} onClick={() => updatePrefs({ range })}>{range}</button>)}
            </fieldset>
            <fieldset className="segmented" aria-label="Chart type">
              <button type="button" aria-pressed={prefs.chartType === "candle"} onClick={() => updatePrefs({ chartType: "candle" })}>Candles</button>
              <button type="button" aria-pressed={prefs.chartType === "line"} onClick={() => updatePrefs({ chartType: "line" })}>Line</button>
            </fieldset>
            <fieldset className="segmented" aria-label="Overlays">
              {OVERLAYS.map((overlay) => (
                <button type="button" key={overlay} aria-pressed={prefs.overlays.includes(overlay)} onClick={() => updatePrefs({ overlays: prefs.overlays.includes(overlay) ? prefs.overlays.filter((item) => item !== overlay) : [...prefs.overlays, overlay] })}>{OVERLAY_LABELS[overlay]}</button>
              ))}
            </fieldset>
            <fieldset className="segmented" aria-label="Lower pane">
              {(["rsi", "macd", "none"] as LowerPane[]).map((pane) => <button type="button" key={pane} aria-pressed={prefs.lowerPane === pane} onClick={() => updatePrefs({ lowerPane: pane })}>{pane === "none" ? "No pane" : pane.toUpperCase()}</button>)}
            </fieldset>
          </div>
          {error && !shown ? (
            <div className="chart-empty" role="alert"><strong>{symbol} is unavailable</strong><span>{error}</span></div>
          ) : shown ? (
            <PriceChart data={shown} chartType={prefs.chartType} overlays={prefs.overlays} lowerPane={prefs.lowerPane} />
          ) : (
            <div className="chart-empty"><span>Loading daily history…</span></div>
          )}
          {error && shown && <div className="panel-warning" role="alert">{error}</div>}
          <div className="source-line"><span>SOURCE · {shown?.source ?? "NOT AVAILABLE"}</span><span>FETCHED · {timestamp(shown?.fetched_at)}</span><span>DAILY BARS · DELAYED</span></div>
        </section>
        <PlannedPanel className="ai-panel" title="AI analyst" meta={`CONTEXT · ${symbol}`} source="Ollama locally · free cloud tier fallback" lines={[
          "Ask questions about this ticker in plain English.",
          "Answers use the numbers on this screen and cite them; the AI never computes prices or signals itself.",
          "One-click prompts: bull vs bear, explain the setup, summarize the latest 10-Q.",
        ]} />
      </div>
      <PlannedPanel title="Strategy scanner" meta="NO STRATEGIES YET" source="Your rules, evaluated in code · backtested on daily history" lines={[
        "Write a strategy in plain English. It becomes a checklist of exact rules you confirm once.",
        "Each loaded strategy shows which rules pass on this chart, entry/stop/target levels, and how it performed historically on this ticker.",
      ]} />
      <div className="terminal-row">
        <TechnicalPanel data={technicals} />
        <PlannedPanel title="Fundamentals" meta="SEC EDGAR" source="Company 10-K and 10-Q filings" lines={["Market cap, valuation multiples, growth, margins, free cash flow and debt.", "Valuation compared with the company's own history.", "ETFs show top holdings instead."]} />
        <PlannedPanel title="News and sentiment" meta="RSS · 8-K" source="Headline feeds and SEC filings · FinBERT scoring" lines={["Latest headlines and filings for this ticker.", "Each headline scored positive, neutral or negative, with a 7-day trend."]} />
      </div>
      <div className="terminal-row">
        <PlannedPanel title="Insider activity" meta="SEC FORM 4" source="Insider buys and sells, last 90 days" lines={["Who bought or sold, how much, and whether it was a pre-planned sale.", "Net insider buying or selling over the period."]} />
        <PlannedPanel title="Peers" meta="EDITABLE LIST" source="Seeded from the SEC industry code" lines={["Valuation and growth side by side with competitors.", "Add or remove peers yourself."]} />
        <PlannedPanel title={`My notes · ${symbol}`} meta="LOCAL" source="Saved on this computer" lines={["Notes for this ticker, optionally pinned to a date on the chart."]} />
      </div>
      <PlannedPanel title="Macro and markets" meta="DAILY" source="Sector ETFs · FRED economic data" lines={["Sector heatmap, Fed funds rate, yield curve, inflation and this week's economic calendar."]} />
    </div>
  );
}

function WatchlistPanel({
  items,
  active,
  onOpen,
  onRemove,
}: {
  items: WatchlistItem[] | null;
  active: string;
  onOpen: (symbol: string) => void;
  onRemove: (symbol: string) => void;
}) {
  return (
    <DataPanel title="Watchlist" meta={items ? `${items.length}` : "…"} className="watchlist-panel">
      {items?.length === 0 && <p className="panel-note">Open a ticker and choose ☆ Watch to keep it here.</p>}
      <ul className="watchlist">
        {items?.map((item) => (
          <li key={item.symbol} className={item.symbol === active ? "active" : undefined}>
            <button type="button" className="watch-open" title={item.security_name} onClick={() => onOpen(item.symbol)}>
              <span className="watch-symbol">{item.symbol}</span>
              <span className="watch-price">{price(item.last)}</span>
              <span className={`watch-change ${tone(item.change_pct)}`}>{signedPercent(item.change_pct)}</span>
            </button>
            <button type="button" className="watch-remove" aria-label={`Remove ${item.symbol} from watchlist`} onClick={() => onRemove(item.symbol)}>×</button>
          </li>
        ))}
      </ul>
    </DataPanel>
  );
}

function TechnicalPanel({ data }: { data: Technicals | null }) {
  const rs = data?.relative_strength_3m;
  const rows: Array<[string, string, string?]> = data ? [
    ["Trend", data.trend.label ? `${data.trend.label} · ${data.trend.above_sma50 ? "above" : "below"} 50 / ${data.trend.above_sma200 ? "above" : "below"} 200 SMA` : "Not enough history", data.trend.label === "Uptrend" ? "positive" : data.trend.label === "Downtrend" ? "negative" : ""],
    ["RSI (14)", data.rsi14 == null ? "—" : `${data.rsi14.toFixed(1)} · ${data.rsi_zone}`, data.rsi_zone === "overbought" ? "warning" : data.rsi_zone === "oversold" ? "warning" : ""],
    ["MACD", data.macd.state ? `${data.macd.state} crossover state` : "—", data.macd.state === "bullish" ? "positive" : data.macd.state === "bearish" ? "negative" : ""],
    ["52-week range", data.range_52w.position == null ? "—" : `${Math.round(data.range_52w.position * 100)}% · ${price(data.range_52w.low)}–${price(data.range_52w.high)}`],
    [`vs ${rs?.benchmark ?? "SPY"} (3M)`, rs?.difference == null ? "—" : `${rs.difference >= 0 ? "+" : ""}${(rs.difference * 100).toFixed(1)} pts`, tone(rs?.difference)],
    ["Distance from 50 SMA", signedPercent(data.trend.distance_sma50_pct, 1), tone(data.trend.distance_sma50_pct)],
    ["ATR (14)", data.atr14 == null ? "—" : `${price(data.atr14)} · ${signedPercent(data.atr_pct, 1).replace("+", "")}`],
    ["2× ATR stop", price(data.atr_stop)],
    ["Volume vs 20-day avg", data.volume_ratio == null ? "—" : `${data.volume_ratio.toFixed(2)}×`, data.volume_ratio != null && data.volume_ratio >= 1.5 ? "warning" : ""],
  ] : [];
  return (
    <DataPanel title="Technical setup" meta={data ? `DAILY · ${dateOnly(data.as_of)}` : "LOADING"}>
      <div className="metric-list">
        {rows.map(([label, value, rowTone]) => <div className="metric-row" key={label}><span>{label}</span><strong className={rowTone}>{value}</strong></div>)}
      </div>
      <p className="panel-note">Calculated from daily closes. Descriptive only, not a signal or a forecast.</p>
    </DataPanel>
  );
}

function PlannedPanel({ title, meta, source, lines, className }: { title: string; meta: string; source: string; lines: string[]; className?: string }) {
  return (
    <DataPanel title={title} meta={meta} className={`planned-panel ${className ?? ""}`.trim()}>
      <div className="planned-body">
        <strong>Not connected yet</strong>
        <ul>{lines.map((line) => <li key={line}>{line}</li>)}</ul>
      </div>
      <div className="source-line"><span>PLANNED SOURCE · {source}</span></div>
    </DataPanel>
  );
}
