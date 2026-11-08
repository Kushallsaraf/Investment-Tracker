import { useCallback, useEffect, useState } from "react";
import {
  addToWatchlist,
  getChart,
  getFundamentals,
  getInsiderActivity,
  getNews,
  getPeers,
  getSymbolJournal,
  getTechnicals,
  getWatchlist,
  removeFromWatchlist,
} from "../api";
import { DataPanel } from "../components/ui";
import { Drawer } from "../components/Drawer";
import { dateOnly, decisionLabel, multiple, price, signedPercent, timestamp, usdCompact } from "../lib/format";
import type {
  ChartPayload,
  ExitPlan,
  ChartRange,
  Fundamentals,
  InsiderActivity,
  NewsPayload,
  PeerComparison,
  SymbolJournal,
  Technicals,
  WatchlistItem,
} from "../types";
import { AnalystPanel } from "./AnalystPanel";
import { ExitPlanPanel } from "./ExitPlanPanel";
import { NewsPanel, sentimentWord } from "./NewsPanel";
import { NotesPanel } from "./NotesPanel";
import { type ChartType, type LowerPane, type Overlay, OVERLAY_LABELS, PriceChart, type PriceLevel } from "./PriceChart";
import { FundamentalsPanel, InsiderPanel, type Loadable, PeersPanel, useSymbolData } from "./SecPanels";

const RANGES: ChartRange[] = ["1M", "3M", "6M", "1Y", "5Y", "MAX"];
const OVERLAYS = Object.keys(OVERLAY_LABELS) as Overlay[];
const CHART_PREFS_KEY = "investment-tracker.chart-prefs.v1";

type ChartPrefs = { range: ChartRange; chartType: ChartType; overlays: Overlay[]; lowerPane: LowerPane };
const DEFAULT_PREFS: ChartPrefs = { range: "1Y", chartType: "candle", overlays: ["ema20", "ema50", "sma200"], lowerPane: "rsi" };

type DrawerKey = "tech" | "fund" | "insiders" | "peers" | "news" | "notes" | "exit" | "ai" | "strategy" | "data";

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

function ordinal(value: number): string {
  const tens = value % 100;
  if (tens >= 11 && tens <= 13) return `${value}th`;
  return `${value}${({ 1: "st", 2: "nd", 3: "rd" } as Record<number, string>)[value % 10] ?? "th"}`;
}

export function ResearchView({ symbol, onOpenSymbol }: { symbol: string; onOpenSymbol: (symbol: string) => void }) {
  const [prefs, setPrefs] = useState<ChartPrefs>(loadPrefs);
  const [chart, setChart] = useState<{ symbol: string; payload: ChartPayload } | null>(null);
  const [technicals, setTechnicals] = useState<Technicals | null>(null);
  const [watchlist, setWatchlist] = useState<WatchlistItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [journal, setJournal] = useState<SymbolJournal | null>(null);
  const [selectedDate, setSelectedDate] = useState<string | null>(null);
  const [drawer, setDrawer] = useState<DrawerKey | null>(null);
  const [fundamentals] = useSymbolData<Fundamentals>(symbol, getFundamentals);
  const [insiders] = useSymbolData<InsiderActivity>(symbol, getInsiderActivity);
  const [peers, setPeers] = useSymbolData<PeerComparison>(symbol, getPeers);
  const [news] = useSymbolData<NewsPayload>(symbol, getNews);

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

  const loadJournal = useCallback(() => {
    void getSymbolJournal(symbol).then((payload) => setJournal(payload)).catch(() => undefined);
  }, [symbol]);
  useEffect(() => {
    setJournal(null);
    setSelectedDate(null);
    loadJournal();
  }, [loadJournal]);

  const loadWatchlist = useCallback(() => {
    void getWatchlist().then(setWatchlist).catch(() => setWatchlist([]));
  }, []);
  useEffect(loadWatchlist, [loadWatchlist]);

  const shown = chart?.symbol === symbol ? chart.payload : null;
  const currentJournal = journal?.symbol === symbol ? journal : null;
  const onWatchlist = Boolean(watchlist?.some((item) => item.symbol === (shown?.symbol ?? symbol)));

  async function toggleWatchlist() {
    const target = shown?.symbol ?? symbol;
    try {
      if (onWatchlist) await removeFromWatchlist(target);
      else await addToWatchlist(target);
      loadWatchlist();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Watchlist update failed");
    }
  }

  const signals = signalCards({ technicals, fundamentals, insiders, peers, news, journal: currentJournal });
  const decision = currentJournal?.decision?.decision ?? "WATCH";
  const exitPlans = currentJournal?.exit_plans ?? [];
  const proposals = exitPlans.filter((plan) => plan.status === "PROPOSED");
  const activePlan = exitPlans.find((plan) => plan.status === "ACCEPTED");
  const levels = chartLevels(activePlan, proposals[0]);
  const exitLabel = proposals.length
    ? `Exit plan · ${proposals.length} proposal${proposals.length === 1 ? "" : "s"}`
    : activePlan ? "Exit plan · active" : "Exit plan";
  const close = () => setDrawer(null);

  return (
    <div className="research">
      <aside className="watch-rail" aria-label="Watchlist">
        <div className="rail-head">
          <span>Watchlist</span>
          <button
            type="button"
            className="icon-button"
            aria-pressed={onWatchlist}
            aria-label={onWatchlist ? `Remove ${symbol} from watchlist` : `Add ${symbol} to watchlist`}
            title={onWatchlist ? "On your watchlist" : "Add to watchlist"}
            onClick={() => void toggleWatchlist()}
          >
            {onWatchlist ? "★" : "+"}
          </button>
        </div>
        {watchlist?.length === 0 && <p className="panel-note" style={{ margin: 0 }}>Use + to keep this ticker here.</p>}
        <ul className="watchlist">
          {watchlist?.map((item) => (
            <li key={item.symbol} className={item.symbol === (shown?.symbol ?? symbol) ? "active" : undefined}>
              <button type="button" className="watch-remove" aria-label={`Remove ${item.symbol} from watchlist`} onClick={() => void removeFromWatchlist(item.symbol).then(loadWatchlist).catch(() => setError("Watchlist update failed"))}>×</button>
              <button type="button" className="watch-open" title={item.security_name} onClick={() => onOpenSymbol(item.symbol)}>
                <span><span className="watch-symbol">{item.symbol}</span><span className="watch-name">{item.security_name}</span></span>
                <span><span>{price(item.last)}</span><span className={tone(item.change_pct)}>{signedPercent(item.change_pct)}</span></span>
              </button>
            </li>
          ))}
        </ul>
      </aside>

      <div className="research-main">
        <section className="ticker-head" aria-label={`${symbol} overview`}>
          <div className="ticker-title">
            <div>
              <h2>{shown?.symbol ?? symbol}</h2>
              <span className="ticker-name">{shown ? `${shown.name} · ${shown.exchange} · ${shown.asset_type}` : loading ? "Loading…" : "Not available"}</span>
            </div>
            {shown && (
              <div>
                <span className="ticker-price">{price(shown.quote.last)}</span>
                <span className={`ticker-change ${tone(shown.quote.change)}`}>{shown.quote.change == null ? "—" : `${shown.quote.change >= 0 ? "+" : "−"}${price(Math.abs(shown.quote.change))}`} · {signedPercent(shown.quote.change_pct)}</span>
                <span className="ticker-asof">Close {dateOnly(shown.quote.as_of)}{shown.stale ? " · stale" : ""} · daily data</span>
              </div>
            )}
          </div>
          <div className="ticker-actions">
            <button type="button" className="decision-button" onClick={() => setDrawer("notes")}>
              <span>My decision</span><strong>{decisionLabel(decision).toUpperCase()}</strong>
            </button>
            <button type="button" className="action outline large" onClick={() => setDrawer("exit")}>{exitLabel}</button>
            <button type="button" className="action primary large" onClick={() => setDrawer("ai")}>Ask AI</button>
          </div>
        </section>

        <section className="chart-card" aria-label={`${symbol} chart`}>
          <div className="chart-toolbar">
            <fieldset className="segmented" aria-label="Chart range">
              {RANGES.map((range) => <button type="button" key={range} aria-pressed={prefs.range === range} onClick={() => updatePrefs({ range })}>{range}</button>)}
            </fieldset>
            <span className="toolbar-divider" aria-hidden="true" />
            <fieldset className="segmented" aria-label="Chart type">
              <button type="button" aria-pressed={prefs.chartType === "candle"} onClick={() => updatePrefs({ chartType: "candle" })}>Candles</button>
              <button type="button" aria-pressed={prefs.chartType === "line"} onClick={() => updatePrefs({ chartType: "line" })}>Line</button>
            </fieldset>
            <details className="indicator-menu">
              <summary>Indicators · {prefs.overlays.length + (prefs.lowerPane === "none" ? 0 : 1)}</summary>
              <div className="indicator-pop">
                <fieldset>
                  <legend>On the price</legend>
                  {OVERLAYS.map((overlay) => (
                    <label key={overlay}>
                      <input type="checkbox" checked={prefs.overlays.includes(overlay)} onChange={() => updatePrefs({ overlays: prefs.overlays.includes(overlay) ? prefs.overlays.filter((item) => item !== overlay) : [...prefs.overlays, overlay] })} />
                      {OVERLAY_LABELS[overlay]}
                    </label>
                  ))}
                </fieldset>
                <fieldset>
                  <legend>Lower pane</legend>
                  {(["rsi", "macd", "none"] as LowerPane[]).map((pane) => (
                    <label key={pane}>
                      <input type="radio" name="lower-pane" checked={prefs.lowerPane === pane} onChange={() => updatePrefs({ lowerPane: pane })} />
                      {pane === "none" ? "None" : pane.toUpperCase()}
                    </label>
                  ))}
                </fieldset>
              </div>
            </details>
            {selectedDate && (
              <button type="button" className="pick-chip" onClick={() => setDrawer("notes")}>Pin a note · {dateOnly(selectedDate)}</button>
            )}
          </div>
          {error && !shown ? (
            <div className="chart-empty" role="alert"><strong>{symbol} is unavailable</strong><span>{error}</span></div>
          ) : shown ? (
            <PriceChart data={shown} chartType={prefs.chartType} overlays={prefs.overlays} lowerPane={prefs.lowerPane} notes={currentJournal?.notes ?? []} levels={levels} onSelectDate={setSelectedDate} />
          ) : (
            <div className="chart-empty"><span>Loading daily history…</span></div>
          )}
          {error && shown && <div className="panel-warning" role="alert">{error}</div>}
          <div className="source-line"><span>{shown?.source ?? "Source not available"}</span><span>Fetched {timestamp(shown?.fetched_at)}</span><span>Daily bars, delayed</span></div>
        </section>

        <section className="signal-grid" aria-label="Summary">
          {signals.map((card) => (
            <button type="button" key={card.key} className={`signal-card ${card.planned ? "planned" : ""}`.trim()} onClick={() => setDrawer(card.key)}>
              <span className="signal-label">{card.label}</span>
              <span className={`signal-value ${card.tone ?? ""}`.trim()}>{card.value}</span>
              <span className="signal-detail">{card.detail}</span>
            </button>
          ))}
        </section>

        <footer className="page-footer">
          <span>Research only. Nothing here places or suggests a trade.</span>
          <button type="button" className="text-button" onClick={() => setDrawer("data")}>How this works · data sources and freshness</button>
        </footer>
      </div>

      <Drawer open={drawer === "tech"} eyebrow={symbol} title="Technical setup" subtitle={technicals ? `Daily · as of ${dateOnly(technicals.as_of)}` : "Daily closes"} onClose={close}>
        <div className="drawer-solo"><TechnicalPanel data={technicals} /></div>
      </Drawer>
      <Drawer open={drawer === "fund"} eyebrow={symbol} title="Valuation and fundamentals" subtitle="SEC EDGAR 10-K and 10-Q filings" onClose={close}>
        <div className="drawer-solo"><FundamentalsPanel state={fundamentals} /></div>
      </Drawer>
      <Drawer open={drawer === "insiders"} eyebrow={symbol} title="Insider activity" subtitle="SEC Form 4 · last 90 days" onClose={close}>
        <div className="drawer-solo"><InsiderPanel state={insiders} /></div>
      </Drawer>
      <Drawer open={drawer === "peers"} eyebrow={symbol} title="Peers" subtitle="Trailing-twelve-month figures from each company's filings" wide onClose={close}>
        <PeersPanel symbol={symbol} state={peers} setData={setPeers} onOpenSymbol={(next) => { close(); onOpenSymbol(next); }} />
      </Drawer>
      <Drawer open={drawer === "news"} eyebrow={symbol} title="News and sentiment" subtitle="Yahoo Finance and Nasdaq headlines · SEC 8-K filings" onClose={close}>
        <NewsPanel state={news} />
      </Drawer>
      <Drawer open={drawer === "notes"} eyebrow={symbol} title="Notes and decision" subtitle="Saved on this computer" onClose={close}>
        <NotesPanel symbol={symbol} journal={currentJournal} selectedDate={selectedDate} onChanged={(next) => (next ? setJournal(next) : loadJournal())} />
      </Drawer>
      <Drawer open={drawer === "exit"} eyebrow={symbol} title="Exit plan" subtitle="Target, stop and review date, with the reasoning" onClose={close}>
        <ExitPlanPanel symbol={symbol} plans={exitPlans} onChanged={loadJournal} />
      </Drawer>
      <Drawer open={drawer === "ai"} eyebrow={symbol} title="Ask AI" subtitle="A research assistant that explains this screen's numbers" onClose={close}>
        <AnalystPanel symbol={symbol} onNoteSaved={loadJournal} />
      </Drawer>
      <Drawer open={drawer === "strategy"} eyebrow={symbol} title="Strategies" subtitle="Planned for a later phase" onClose={close}>
        <PlannedPanel title="Strategy checks" source="Your rules, evaluated in code · backtested on daily history" lines={[
          "Write a strategy in plain English. It becomes a checklist of exact rules you confirm once.",
          "Each strategy shows which rules pass on this chart and how it performed historically on this ticker.",
        ]} />
      </Drawer>
      <Drawer open={drawer === "data"} title="How this works" subtitle="Where each number comes from and how fresh it is" onClose={close}>
        <HowItWorks chart={shown} />
      </Drawer>
    </div>
  );
}

function chartLevels(active: ExitPlan | undefined, proposal: ExitPlan | undefined): PriceLevel[] {
  const result: PriceLevel[] = [];
  for (const [plan, proposed] of [[active, false], [proposal, true]] as const) {
    if (!plan) continue;
    const suffix = proposed ? " · proposed" : "";
    if (plan.target_price) result.push({ price: Number(plan.target_price), label: `Target${suffix}`, kind: "target", proposed });
    if (plan.stop_price) result.push({ price: Number(plan.stop_price), label: `Stop${suffix}`, kind: "stop", proposed });
  }
  return result;
}

type SignalCard = { key: DrawerKey; label: string; value: string; detail: string; tone?: string; planned?: boolean };

function signalCards({
  technicals,
  fundamentals,
  insiders,
  peers,
  news,
  journal,
}: {
  technicals: Technicals | null;
  fundamentals: Loadable<Fundamentals> | null;
  insiders: Loadable<InsiderActivity> | null;
  peers: Loadable<PeerComparison> | null;
  news: Loadable<NewsPayload> | null;
  journal: SymbolJournal | null;
}): SignalCard[] {
  const trend: SignalCard = technicals
    ? {
        key: "tech",
        label: "Trend",
        value: technicals.trend.label ?? "Not enough history",
        tone: technicals.trend.label === "Uptrend" ? "positive" : technicals.trend.label === "Downtrend" ? "negative" : undefined,
        detail: [
          technicals.rsi14 == null ? null : `RSI ${technicals.rsi14.toFixed(0)}`,
          technicals.trend.above_sma200 == null ? null : `${technicals.trend.above_sma200 ? "above" : "below"} 200-day`,
        ].filter(Boolean).join(" · ") || "Daily closes",
      }
    : { key: "tech", label: "Trend", value: "…", detail: "Loading daily history" };

  const valuation = loadableCard(fundamentals, "fund", "Valuation", (data) => {
    if (!data.applicable) return { value: "N/A", detail: data.reason };
    const pe = data.valuation_history.pe;
    if (pe.current == null) return { value: "No P/E", detail: data.valuation.ps_ttm.value == null ? "Earnings not available" : `P/S ${multiple(data.valuation.ps_ttm.value)}` };
    return {
      value: `P/E ${multiple(pe.current)}`,
      detail: pe.status === "available" && pe.percentile != null ? `${ordinal(Math.round(pe.percentile * 100))} percentile of its 5 years` : "Not enough history for a range",
    };
  });

  const insider = loadableCard(insiders, "insiders", "Insiders", (data) => {
    if (!data.applicable) return { value: "N/A", detail: data.reason };
    const { net_value, buyers, sellers } = data.summary;
    if (!buyers && !sellers) return { value: "Quiet", detail: `No open-market trades in ${data.days} days` };
    return {
      value: `${net_value >= 0 ? "Net buy" : "Net sell"} ${usdCompact(Math.abs(net_value))}`,
      tone: tone(net_value),
      detail: `${buyers} buyer${buyers === 1 ? "" : "s"}, ${sellers} seller${sellers === 1 ? "" : "s"} · ${data.days} days`,
    };
  });

  const peer = loadableCard(peers, "peers", "Peers", (data) => {
    if (!data.applicable) return { value: "N/A", detail: data.reason };
    const ranked = data.rows.filter((row) => row.return_3m != null).sort((a, b) => (b.return_3m ?? 0) - (a.return_3m ?? 0));
    const rank = ranked.findIndex((row) => row.symbol === data.symbol);
    if (data.rows.length <= 1) return { value: "None yet", detail: "Add peer tickers to compare" };
    return {
      value: rank < 0 ? `${data.rows.length - 1} peers` : `${rank + 1} of ${ranked.length}`,
      detail: rank < 0 ? "3-month return not available" : "Ranked by 3-month return",
    };
  });

  const headlines = news?.data?.headlines.length ?? 0;
  const newsCard: SignalCard = !news
    ? { key: "news", label: "News", value: "…", detail: "Loading headlines" }
    : news.error || !news.data
      ? { key: "news", label: "News", value: "N/A", detail: news.error ?? "Not available" }
      : news.data.sentiment.available
        ? {
            key: "news",
            label: "News",
            value: `${sentimentWord(news.data.sentiment.net)} ${news.data.sentiment.net >= 0 ? "+" : "−"}${Math.abs(news.data.sentiment.net).toFixed(2)}`,
            tone: news.data.sentiment.net >= 0.15 ? "positive" : news.data.sentiment.net <= -0.15 ? "negative" : undefined,
            detail: `${news.data.sentiment.scored} headline${news.data.sentiment.scored === 1 ? "" : "s"} in 7 days${news.data.filings.length ? ` · ${news.data.filings.length} 8-K` : ""}`,
          }
        : {
            key: "news",
            label: "News",
            value: `${headlines} headline${headlines === 1 ? "" : "s"}`,
            detail: `Sentiment not available · ${news.data.sentiment.reason}`,
          };

  const noteCount = journal?.notes.length ?? 0;
  const latest = journal?.notes[0]?.body;
  const notes: SignalCard = {
    key: "notes",
    label: "Notes",
    value: journal ? `${noteCount} note${noteCount === 1 ? "" : "s"}` : "…",
    detail: latest ? (latest.length > 60 ? `${latest.slice(0, 60)}…` : latest) : "Write down what you're watching for",
  };

  const strategies: SignalCard = { key: "strategy", label: "Strategies", value: "None yet", detail: "Planned · rules you write, tested on history", planned: true };
  return [trend, valuation, insider, peer, newsCard, notes, strategies];
}

function loadableCard<T>(
  state: Loadable<T> | null,
  key: DrawerKey,
  label: string,
  summarize: (data: T) => { value: string; detail: string; tone?: string },
): SignalCard {
  if (!state) return { key, label, value: "…", detail: "Loading from SEC EDGAR" };
  if (state.error || state.data == null) return { key, label, value: "N/A", detail: state.error ?? "Not available" };
  return { key, label, ...summarize(state.data) };
}

function TechnicalPanel({ data }: { data: Technicals | null }) {
  const rs = data?.relative_strength_3m;
  const rows: Array<[string, string, string?]> = data ? [
    ["Trend", data.trend.label ?? "Not enough history", data.trend.label === "Uptrend" ? "positive" : data.trend.label === "Downtrend" ? "negative" : ""],
    ["Price vs 20 / 50 / 200 SMA", [data.trend.above_sma20, data.trend.above_sma50, data.trend.above_sma200].map((above) => (above == null ? "—" : above ? "above" : "below")).join(" / ")],
    ["RSI (14)", data.rsi14 == null ? "—" : `${data.rsi14.toFixed(1)} · ${data.rsi_zone}`, data.rsi_zone === "overbought" || data.rsi_zone === "oversold" ? "warning" : ""],
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

function PlannedPanel({ title, source, lines }: { title: string; source: string; lines: string[] }) {
  return (
    <DataPanel title={title} className="planned-panel">
      <div className="planned-body">
        <strong>Not connected yet</strong>
        <ul>{lines.map((line) => <li key={line}>{line}</li>)}</ul>
      </div>
      <div className="source-line"><span>Planned source · {source}</span></div>
    </DataPanel>
  );
}

function HowItWorks({ chart }: { chart: ChartPayload | null }) {
  return (
    <>
      <ol className="how-list">
        <li><strong>Prices</strong><span>Daily bars from Yahoo Finance, saved in a local SQLite database. Ten years load once, then only recent days are fetched, at most every 15 minutes. If a fetch fails, the last saved copy is shown and marked stale.</span></li>
        <li><strong>Indicators</strong><span>Moving averages, RSI, MACD, Bollinger Bands and ATR are calculated in Python from the saved closes. Nothing is estimated by an AI.</span></li>
        <li><strong>Company filings</strong><span>Revenue, earnings, margins and insider trades come from SEC EDGAR (10-K, 10-Q and Form 4). Requests are rate-limited and cached, and every figure keeps its filing date.</span></li>
        <li><strong>Your notes and decisions</strong><span>Stored only on this computer. The local server accepts changes only from this app.</span></li>
        <li><strong>Missing data</strong><span>When a number is not available it says so, with the reason, instead of being filled in.</span></li>
      </ol>
      <div className="source-line" style={{ borderTop: 0, padding: 0 }}>
        <span>Chart source · {chart?.source ?? "not loaded"}</span>
        <span>Fetched {timestamp(chart?.fetched_at)}</span>
      </div>
    </>
  );
}
