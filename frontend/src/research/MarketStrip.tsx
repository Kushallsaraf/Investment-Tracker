import { signedPercent, price } from "../lib/format";
import type { StripItem } from "../types";

const OPENABLE = new Set(["SPY", "QQQ", "DIA", "IWM"]);
// The header keeps a short pulse; the rest of the strip belongs to the macro view.
const PULSE = ["SPY", "QQQ", "^VIX", "^TNX"];

export function MarketStrip({ items, onOpen }: { items: StripItem[] | null; onOpen: (symbol: string) => void }) {
  return (
    <section className="market-strip" aria-label="Market overview">
      {items === null && <span className="strip-note">Loading markets…</span>}
      {items?.length === 0 && <span className="strip-note">Market overview unavailable</span>}
      {items?.filter((item) => PULSE.includes(item.symbol)).map((item) => {
        const tone = item.change_pct == null ? "" : item.change_pct >= 0 ? "positive" : "negative";
        const body = (
          <>
            <span className="strip-label">{item.label}</span>
            <span className="strip-price">{price(item.last)}</span>
            <span className={`strip-change ${tone}`}>{signedPercent(item.change_pct)}</span>
          </>
        );
        return OPENABLE.has(item.symbol) ? (
          <button type="button" key={item.symbol} className="strip-item" title={`${item.description} · open chart`} onClick={() => onOpen(item.symbol)}>{body}</button>
        ) : (
          <span key={item.symbol} className="strip-item" title={`${item.description} · as of ${item.as_of ?? "unknown"}`}>{body}</span>
        );
      })}
    </section>
  );
}
