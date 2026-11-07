import { useEffect, useState } from "react";
import { getMacro } from "../api";
import { dateOnly, percent, timestamp } from "../lib/format";
import type { MacroEvent, MacroIndicator, MacroSnapshot, MacroTheme } from "../types";

const GROUPS = ["Jobs", "Inflation", "Rates", "Growth", "Energy"];
const IMPACT_LABEL = { high: "High impact", medium: "Medium impact", low: "Low impact" } as const;

function formatValue(indicator: MacroIndicator, value: number | null | undefined): string {
  if (value == null) return "—";
  switch (indicator.unit) {
    case "%": return `${value.toFixed(indicator.key === "fed_funds" ? 2 : 1)}%`;
    case "K": return `${value.toLocaleString("en-US", { maximumFractionDigits: 0 })}K`;
    case "$": return `$${value.toFixed(2)}`;
    case "pts": return `${value >= 0 ? "+" : "−"}${Math.abs(value).toFixed(2)}`;
    default: return value.toFixed(1);
  }
}

function changeText(indicator: MacroIndicator): string | null {
  if (indicator.change == null) return null;
  if (indicator.change === 0) return "unchanged";
  const size = Math.abs(indicator.change);
  const amount = indicator.unit === "%" || indicator.unit === "pts"
    ? `${size.toFixed(2)} pts`
    : indicator.unit === "$" ? `$${size.toFixed(2)}` : indicator.unit === "K" ? `${size.toFixed(0)}K` : size.toFixed(1);
  return `${indicator.change > 0 ? "▲" : "▼"} ${amount}`;
}

function daysUntil(day: string): string {
  const today = new Date();
  const start = Date.UTC(today.getFullYear(), today.getMonth(), today.getDate());
  const [year, month, date] = day.split("-").map(Number);
  const diff = Math.round((Date.UTC(year, month - 1, date) - start) / 86_400_000);
  if (diff === 0) return "Today";
  if (diff === 1) return "Tomorrow";
  return `In ${diff} days`;
}

/** FRED dates a month or quarter by its first day; show the period it covers instead. */
function periodLabel(item: MacroIndicator): string {
  if (!item.as_of) return "";
  const date = new Date(`${item.as_of}T12:00:00`);
  if (item.frequency === "monthly") return date.toLocaleDateString("en-US", { month: "long", year: "numeric" });
  if (item.frequency === "quarterly") return `Q${Math.floor(date.getMonth() / 3) + 1} ${date.getFullYear()}`;
  if (item.frequency === "weekly") return `week of ${dateOnly(item.as_of)}`;
  return dateOnly(item.as_of);
}

function shortDate(day: string): string {
  return new Date(`${day}T12:00:00`).toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" });
}

function toneWord(net: number | null): { text: string; tone: string } {
  if (net == null) return { text: "not scored", tone: "" };
  if (net >= 0.15) return { text: "mostly positive", tone: "positive" };
  if (net <= -0.15) return { text: "mostly negative", tone: "negative" };
  return { text: "mixed", tone: "" };
}

function Calendar({ events, unavailable }: { events: MacroEvent[]; unavailable?: string | null }) {
  const byDate = new Map<string, MacroEvent[]>();
  for (const event of events) byDate.set(event.date, [...(byDate.get(event.date) ?? []), event]);
  return (
    <section className="setup-section" aria-label="Coming up">
      <h3>Coming up · next 45 days</h3>
      {unavailable && <p className="exit-empty">Economic reports need FRED · {unavailable}</p>}
      {events.length === 0 && !unavailable && <p className="exit-empty">No scheduled reports found.</p>}
      <ol className="macro-calendar">
        {[...byDate.entries()].map(([day, rows]) => (
          <li key={day}>
            <div className="macro-date"><strong>{shortDate(day)}</strong><span>{daysUntil(day)}</span></div>
            <ul>
              {rows.map((event) => (
                <li key={event.name}>
                  <i className={`impact ${event.impact}`} title={IMPACT_LABEL[event.impact]} aria-hidden="true" />
                  <span><strong>{event.name}</strong><small>{event.detail}</small></span>
                  <span className="visually-hidden">{IMPACT_LABEL[event.impact]}</span>
                </li>
              ))}
            </ul>
          </li>
        ))}
      </ol>
    </section>
  );
}

function Indicators({ items, unavailable }: { items: MacroIndicator[]; unavailable?: string }) {
  if (unavailable) {
    return (
      <section className="setup-section" aria-label="Latest data">
        <h3>Latest data</h3>
        <p className="exit-empty">Not available · {unavailable}</p>
      </section>
    );
  }
  return (
    <section className="setup-section" aria-label="Latest data">
      <h3>Latest data</h3>
      {GROUPS.map((group) => {
        const rows = items.filter((item) => item.group === group);
        if (!rows.length) return null;
        return (
          <div key={group} className="macro-group">
            <span className="macro-group-label">{group}</span>
            <div className="macro-grid">
              {rows.map((item) => (
                <div key={item.key} className={`macro-stat ${item.key === "curve" && (item.value ?? 0) < 0 ? "alert" : ""}`.trim()}>
                  <span className="macro-stat-label" title={item.note}>{item.label}</span>
                  {item.available ? (
                    <>
                      <strong>{formatValue(item, item.value)}</strong>
                      <small>
                        {changeText(item) && <b className={item.change && item.change > 0 ? "up" : "down"}>{changeText(item)}</b>}
                        {" "}vs {item.compared_with === "previous release" ? "prior" : "a month ago"} · {periodLabel(item)}{item.stale ? " · stale" : ""}
                      </small>
                      {item.key === "curve" && (item.value ?? 0) < 0 && <small className="warning">Inverted</small>}
                    </>
                  ) : (
                    <small>Not available · {item.reason}</small>
                  )}
                </div>
              ))}
            </div>
          </div>
        );
      })}
    </section>
  );
}

function ThemeRow({ theme, active, onSelect }: { theme: MacroTheme; active: boolean; onSelect: () => void }) {
  const tone = toneWord(theme.net);
  return (
    <button type="button" className="macro-theme" aria-pressed={active} onClick={onSelect}>
      <span className="macro-theme-head">
        <strong>{theme.label}</strong>
        <span>{theme.count} headline{theme.count === 1 ? "" : "s"}{theme.last_day ? ` · ${theme.last_day} today` : ""}</span>
      </span>
      <span className={`macro-theme-tone ${tone.tone}`.trim()}>{tone.text}</span>
      <span className="macro-theme-holdings">
        {theme.holdings.length
          ? `Your holdings: ${theme.holdings.slice(0, 4).map((row) => row.symbol).join(", ")}${theme.holdings.length > 4 ? ` +${theme.holdings.length - 4}` : ""} · ${percent(theme.holdings_weight)}`
          : `Sensitive sectors: ${theme.sectors.slice(0, 3).join(", ")}`}
      </span>
    </button>
  );
}

function WorldNews({ news }: { news: MacroSnapshot["news"] }) {
  const [theme, setTheme] = useState<string | null>(null);
  const active = news.themes.filter((row) => row.count > 0);
  const labels = new Map(news.themes.map((row) => [row.key, row.label]));
  const shown = theme ? news.headlines.filter((row) => row.themes.includes(theme)) : news.headlines;
  return (
    <section className="setup-section" aria-label="This week in the world">
      <h3>This week in the world</h3>
      {active.length === 0 && <p className="exit-empty">No macro headlines in the last {news.days} days.</p>}
      <div className="macro-themes">
        {active.map((row) => <ThemeRow key={row.key} theme={row} active={theme === row.key} onSelect={() => setTheme(theme === row.key ? null : row.key)} />)}
      </div>
      {active.length > 0 && (
        <p className="exit-reference" style={{ margin: 0 }}>
          {theme ? <>Showing {labels.get(theme)} · <button type="button" className="link-button" onClick={() => setTheme(null)}>show all</button></> : "Select a theme to filter the headlines."} Holdings are matched by sector, which shows where a theme usually matters, not what will happen.
        </p>
      )}
      <ul className="news-list">
        {shown.map((item) => (
          <li className="news-item" key={item.id}>
            <div className="news-meta">
              <span>{timestamp(item.published_at)}</span>
              <span>{item.publisher}</span>
              {item.themes.map((key) => <span key={key} className="macro-tag">{labels.get(key) ?? key}</span>)}
              {item.sentiment && <span className={`news-chip ${item.sentiment.label}`}>{item.sentiment.label}</span>}
            </div>
            <a href={item.url} target="_blank" rel="noreferrer">{item.title}</a>
            {item.summary && <p>{item.summary}</p>}
          </li>
        ))}
      </ul>
      {news.sentiment_reason && <p className="exit-reference" style={{ margin: 0 }}>Sentiment not available · {news.sentiment_reason}</p>}
    </section>
  );
}

/** Macro picture: world news by theme, upcoming market-moving reports, and the latest data. */
export function MacroPanel() {
  const [snapshot, setSnapshot] = useState<MacroSnapshot | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getMacro().then(setSnapshot).catch((cause) => setError(cause instanceof Error ? cause.message : "Macro data is unavailable"));
  }, []);

  if (error) return <div className="status-banner error" role="alert" style={{ margin: 0 }}>{error}</div>;
  if (!snapshot) return <p className="panel-note" style={{ margin: 0 }}>Loading the macro picture… the first load takes a few seconds.</p>;

  const warnings = [...snapshot.news.warnings, ...snapshot.calendar.warnings];
  return (
    <div className="macro-layout">
      <div className="macro-main">
        <WorldNews news={snapshot.news} />
      </div>
      <div className="macro-side">
        <Calendar events={snapshot.calendar.events} unavailable={snapshot.calendar.unavailable} />
        <Indicators items={snapshot.indicators.items} unavailable={snapshot.indicators.unavailable} />
      </div>
      <div className="macro-foot">
        {warnings.map((warning) => <div className="panel-warning" key={warning} style={{ border: 0, padding: 0 }}>{warning}</div>)}
        <div className="source-line" style={{ borderTop: 0, padding: 0 }}>
          <span>{snapshot.news.sources.join(" · ")} · FRED · Federal Reserve calendar</span>
          <span>Updated {timestamp(snapshot.generated_at)}{snapshot.news.stale ? " · headlines stale" : ""}</span>
        </div>
      </div>
    </div>
  );
}
