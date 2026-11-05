import { dateOnly, timestamp } from "../lib/format";
import type { NewsItem, NewsPayload } from "../types";
import type { Loadable } from "./SecPanels";

export function sentimentWord(net: number): string {
  if (net >= 0.15) return "Positive";
  if (net <= -0.15) return "Negative";
  return "Mixed";
}

function signed(value: number): string {
  return `${value >= 0 ? "+" : "−"}${Math.abs(value).toFixed(2)}`;
}

function toneFor(net: number | null | undefined): string {
  if (net == null) return "";
  if (net >= 0.15) return "positive";
  if (net <= -0.15) return "negative";
  return "";
}

function Headline({ item }: { item: NewsItem }) {
  const sentiment = item.sentiment;
  return (
    <li className="news-item">
      <div className="news-meta">
        <span>{dateOnly(item.published_at)}</span>
        <span>{item.publisher}</span>
        {sentiment && (
          <span className={`news-chip ${sentiment.label}`} title={`Positive ${sentiment.positive} · neutral ${sentiment.neutral} · negative ${sentiment.negative}`}>
            {sentiment.label} {signed(sentiment.net)}
          </span>
        )}
      </div>
      <a href={item.url} target="_blank" rel="noreferrer">{item.title}</a>
      {item.summary && <p>{item.summary}</p>}
    </li>
  );
}

export function NewsPanel({ state }: { state: Loadable<NewsPayload> | null }) {
  if (!state) return <p className="panel-note" style={{ margin: 0 }}>Loading headlines…</p>;
  if (state.error || !state.data) {
    return <div className="panel-state" role="status"><strong>NOT AVAILABLE</strong><span>{state.error ?? "News could not be loaded"}</span></div>;
  }
  const data = state.data;
  const sentiment = data.sentiment;
  const peak = sentiment.available ? Math.max(...sentiment.trend.map((day) => day.count), 1) : 1;
  return (
    <>
      <section className="setup-section" aria-label="Sentiment">
        <h3>Sentiment · last {data.window_days} days</h3>
        {sentiment.available ? (
          <>
            <div className="news-summary">
              <strong className={toneFor(sentiment.net)}>{sentimentWord(sentiment.net)} {signed(sentiment.net)}</strong>
              <span>{sentiment.counts.positive} positive · {sentiment.counts.neutral} neutral · {sentiment.counts.negative} negative</span>
            </div>
            <div className="news-trend" role="img" aria-label={`Daily headline sentiment: ${sentiment.trend.map((day) => `${dateOnly(day.date)} ${day.net == null ? "no headlines" : signed(day.net)}`).join(", ")}`}>
              {sentiment.trend.map((day) => (
                <div key={day.date} className="news-day">
                  <div className="news-bar-track">
                    {day.net != null && (
                      <i
                        className={day.net >= 0 ? "up" : "down"}
                        style={{ height: `${Math.max(6, Math.abs(day.net) * 100)}%`, opacity: 0.35 + 0.65 * (day.count / peak) }}
                      />
                    )}
                  </div>
                  <span>{new Date(`${day.date}T12:00:00`).toLocaleDateString("en-US", { weekday: "narrow" })}</span>
                </div>
              ))}
            </div>
            <p className="exit-reference" style={{ margin: 0 }}>
              Scored on this computer with {sentiment.model}. It rates the wording of headlines, not the stock, and is not a signal.
            </p>
          </>
        ) : (
          <p className="exit-empty">Not available · {sentiment.reason}</p>
        )}
      </section>

      <section className="setup-section" aria-label="Headlines">
        <h3>Headlines · {data.headlines.length}</h3>
        {data.headlines.length === 0
          ? <p className="exit-empty">No headlines from the news feeds.</p>
          : <ul className="news-list">{data.headlines.map((item) => <Headline key={item.id} item={item} />)}</ul>}
      </section>

      {data.filings.length > 0 && (
        <section className="setup-section" aria-label="SEC filings">
          <h3>8-K filings · last 30 days</h3>
          <ul className="news-list">{data.filings.map((item) => <Headline key={item.id} item={item} />)}</ul>
        </section>
      )}

      {data.warnings.map((warning) => <div className="panel-warning" key={warning} style={{ border: 0, padding: 0 }}>{warning}</div>)}
      <div className="source-line" style={{ borderTop: 0, padding: 0 }}>
        <span>{data.sources.join(" · ")}</span>
        <span>Fetched {timestamp(data.fetched_at)}{data.stale ? " · stale" : ""}</span>
      </div>
    </>
  );
}
