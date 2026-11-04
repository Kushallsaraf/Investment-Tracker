import {
  CandlestickSeries,
  ColorType,
  CrosshairMode,
  createChart,
  createSeriesMarkers,
  HistogramSeries,
  type IChartApi,
  type IPriceLine,
  type ISeriesApi,
  type ISeriesMarkersPluginApi,
  type SeriesType,
  LineSeries,
  LineStyle,
  type MouseEventParams,
  type SeriesMarker,
  type Time,
} from "lightweight-charts";
import { useEffect, useMemo, useRef, useState } from "react";
import { compactNumber, price, signedPercent } from "../lib/format";
import type { ChartPayload, IndicatorName, Note, PriceBar } from "../types";

export type ChartType = "candle" | "line";
export type Overlay = "ema20" | "ema50" | "sma200" | "bollinger";
export type LowerPane = "rsi" | "macd" | "none";

/** A horizontal level from an exit plan: solid when accepted, dotted while only proposed. */
export type PriceLevel = { price: number; label: string; kind: "target" | "stop"; proposed: boolean };

export const OVERLAY_LABELS: Record<Overlay, string> = {
  ema20: "EMA 20",
  ema50: "EMA 50",
  sma200: "SMA 200",
  bollinger: "Bollinger",
};

const COLORS = {
  background: "#16181b",
  text: "#8e939c",
  grid: "#1f2226",
  border: "#2a2d33",
  up: "#3dd68c",
  down: "#ff6b6b",
  line: "#2ec4b6",
  ema20: "#6fa8ff",
  ema50: "#e3b65c",
  sma200: "#b39df2",
  band: "#5c6068",
  volumeUp: "rgba(61, 214, 140, 0.28)",
  volumeDown: "rgba(255, 107, 107, 0.28)",
  userNote: "#e3b65c",
  target: "#2ec4b6",
  stop: "#ff6b6b",
  claudeNote: "#b39df2",
};

/** Group pinned notes onto the first trading day on or after each pinned date in view. */
function pinNotes(bars: PriceBar[], notes: Note[]): Map<string, Note[]> {
  const pins = new Map<string, Note[]>();
  if (!bars.length) return pins;
  for (const note of notes) {
    if (!note.pinned_date || note.pinned_date < bars[0].date) continue;
    const bar = bars.find((candidate) => candidate.date >= (note.pinned_date as string));
    if (!bar) continue;
    pins.set(bar.date, [...(pins.get(bar.date) ?? []), note]);
  }
  return pins;
}

function pinMarkers(pins: Map<string, Note[]>): SeriesMarker<Time>[] {
  return [...pins.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([date, notes]) => ({
    time: date as Time,
    position: "aboveBar",
    shape: "square",
    color: notes.some((note) => note.author === "CLAUDE") ? COLORS.claudeNote : COLORS.userNote,
    text: notes.length > 1 ? `N${notes.length}` : "N",
  }));
}

function points(bars: PriceBar[], values: Array<number | null>) {
  return bars.flatMap((bar, index) => {
    const value = values[index];
    return value == null ? [] : [{ time: bar.date as Time, value }];
  });
}

export function PriceChart({
  data,
  chartType,
  overlays,
  lowerPane,
  notes = [],
  levels = [],
  onSelectDate,
}: {
  data: ChartPayload;
  chartType: ChartType;
  overlays: Overlay[];
  lowerPane: LowerPane;
  notes?: Note[];
  levels?: PriceLevel[];
  onSelectDate?: (date: string) => void;
}) {
  const container = useRef<HTMLDivElement>(null);
  const [hovered, setHovered] = useState<number | null>(null);
  const indexByDate = useMemo(() => new Map(data.bars.map((bar, index) => [bar.date, index])), [data]);
  const overlayKey = overlays.join(",");
  const pins = useMemo(() => pinNotes(data.bars, notes), [data, notes]);
  const markers = useMemo(() => pinMarkers(pins), [pins]);
  // Notes and the click handler change without rebuilding the chart, so the build effect reads them from refs.
  const markersRef = useRef(markers);
  markersRef.current = markers;
  const onSelectRef = useRef(onSelectDate);
  onSelectRef.current = onSelectDate;
  const markerApi = useRef<ISeriesMarkersPluginApi<Time> | null>(null);
  const mainSeries = useRef<ISeriesApi<SeriesType> | null>(null);
  const priceLines = useRef<IPriceLine[]>([]);
  const levelsRef = useRef(levels);
  levelsRef.current = levels;
  const levelKey = levels.map((level) => `${level.kind}:${level.price}:${level.proposed}`).join("|");

  function drawLevels() {
    const target = mainSeries.current;
    if (!target) return;
    for (const line of priceLines.current) target.removePriceLine(line);
    priceLines.current = levelsRef.current.map((level) => target.createPriceLine({
      price: level.price,
      color: level.kind === "target" ? COLORS.target : COLORS.stop,
      lineWidth: 1,
      lineStyle: level.proposed ? LineStyle.Dotted : LineStyle.Dashed,
      axisLabelVisible: true,
      title: level.label,
    }));
  }

  useEffect(() => {
    if (!container.current || !data.bars.length) return;
    const chart: IChartApi = createChart(container.current, {
      autoSize: true,
      layout: {
        background: { type: ColorType.Solid, color: COLORS.background },
        textColor: COLORS.text,
        fontSize: 10,
        fontFamily: "IBM Plex Mono, ui-monospace, Menlo, monospace",
        attributionLogo: false,
        panes: { separatorColor: COLORS.border, separatorHoverColor: COLORS.border, enableResize: false },
      },
      grid: { vertLines: { color: COLORS.grid }, horzLines: { color: COLORS.grid } },
      rightPriceScale: { borderColor: COLORS.border },
      timeScale: { borderColor: COLORS.border, rightOffset: 3, lockVisibleTimeRangeOnResize: true },
      crosshair: { mode: CrosshairMode.Normal },
    });
    const { bars, indicators } = data;
    // Rebuild from the joined key so a new array holding the same overlays does not redraw the chart.
    const activeOverlays = overlayKey ? (overlayKey.split(",") as Overlay[]) : [];
    const series = (name: IndicatorName) => points(bars, indicators[name]);

    if (chartType === "candle") {
      const candles = chart.addSeries(CandlestickSeries, {
        upColor: COLORS.up,
        downColor: COLORS.down,
        borderVisible: false,
        wickUpColor: COLORS.up,
        wickDownColor: COLORS.down,
      });
      candles.setData(bars.map((bar) => ({ time: bar.date as Time, open: bar.open, high: bar.high, low: bar.low, close: bar.close })));
      markerApi.current = createSeriesMarkers(candles, markersRef.current);
      mainSeries.current = candles;
    } else {
      const line = chart.addSeries(LineSeries, { color: COLORS.line, lineWidth: 2 });
      line.setData(bars.map((bar) => ({ time: bar.date as Time, value: bar.close })));
      markerApi.current = createSeriesMarkers(line, markersRef.current);
      mainSeries.current = line;
    }
    priceLines.current = [];
    drawLevels();

    const volume = chart.addSeries(HistogramSeries, { priceFormat: { type: "volume" }, priceScaleId: "volume", lastValueVisible: false, priceLineVisible: false });
    volume.priceScale().applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
    volume.setData(bars.flatMap((bar, index) => bar.volume == null ? [] : [{
      time: bar.date as Time,
      value: bar.volume,
      color: bar.close >= (bars[index - 1]?.close ?? bar.open) ? COLORS.volumeUp : COLORS.volumeDown,
    }]));

    const overlayLine = { lineWidth: 1, lastValueVisible: false, priceLineVisible: false, crosshairMarkerVisible: false } as const;
    for (const overlay of activeOverlays) {
      if (overlay === "bollinger") {
        for (const band of ["bb_upper", "bb_middle", "bb_lower"] as const) {
          chart.addSeries(LineSeries, { ...overlayLine, color: COLORS.band, lineStyle: band === "bb_middle" ? LineStyle.Dotted : LineStyle.Solid }).setData(series(band));
        }
      } else {
        chart.addSeries(LineSeries, { ...overlayLine, color: COLORS[overlay] }).setData(series(overlay));
      }
    }

    if (lowerPane === "rsi") {
      const rsi = chart.addSeries(LineSeries, { color: COLORS.line, lineWidth: 1, priceLineVisible: false }, 1);
      rsi.setData(series("rsi14"));
      for (const level of [70, 30]) {
        rsi.createPriceLine({ price: level, color: COLORS.band, lineStyle: LineStyle.Dashed, lineWidth: 1, axisLabelVisible: false, title: "" });
      }
    } else if (lowerPane === "macd") {
      chart.addSeries(HistogramSeries, { priceLineVisible: false, lastValueVisible: false }, 1).setData(
        bars.flatMap((bar, index) => {
          const value = indicators.macd_histogram[index];
          return value == null ? [] : [{ time: bar.date as Time, value, color: value >= 0 ? COLORS.volumeUp : COLORS.volumeDown }];
        }),
      );
      chart.addSeries(LineSeries, { color: COLORS.line, lineWidth: 1, priceLineVisible: false }, 1).setData(series("macd"));
      chart.addSeries(LineSeries, { color: COLORS.ema50, lineWidth: 1, priceLineVisible: false }, 1).setData(series("macd_signal"));
    }
    if (lowerPane !== "none") chart.panes()[1]?.setHeight(110);

    chart.timeScale().fitContent();
    const onMove = (param: MouseEventParams) => {
      setHovered(param.time == null ? null : indexByDate.get(String(param.time)) ?? null);
    };
    const onClick = (param: MouseEventParams) => {
      if (param.time != null) onSelectRef.current?.(String(param.time));
    };
    chart.subscribeCrosshairMove(onMove);
    chart.subscribeClick(onClick);
    return () => {
      chart.unsubscribeCrosshairMove(onMove);
      chart.unsubscribeClick(onClick);
      markerApi.current = null;
      mainSeries.current = null;
      priceLines.current = [];
      chart.remove();
    };
  }, [data, chartType, overlayKey, lowerPane, indexByDate]);

  useEffect(() => {
    markerApi.current?.setMarkers(markers);
  }, [markers]);

  // Levels are read through a ref, so redraw only when their values change.
  useEffect(drawLevels, [levelKey]);

  const index = hovered ?? data.bars.length - 1;
  const bar = data.bars[index];
  const previous = data.bars[index - 1];
  const change = bar && previous ? bar.close / previous.close - 1 : null;
  const barNotes = bar ? pins.get(bar.date) ?? [] : [];

  return (
    <div className="price-chart">
      {bar && (
        <div className="chart-legend" aria-live="off">
          <span>{bar.date}</span>
          <span>O <b>{price(bar.open)}</b></span>
          <span>H <b>{price(bar.high)}</b></span>
          <span>L <b>{price(bar.low)}</b></span>
          <span>C <b>{price(bar.close)}</b></span>
          <span className={change == null ? "" : change >= 0 ? "positive" : "negative"}>{signedPercent(change)}</span>
          <span>Vol <b>{compactNumber(bar.volume)}</b></span>
          {overlays.map((overlay) => <span key={overlay} className={`legend-key ${overlay}`}>{OVERLAY_LABELS[overlay]}</span>)}
          {barNotes.length > 0 && (
            <span className="legend-note">NOTE · {barNotes[0].body.length > 90 ? `${barNotes[0].body.slice(0, 90)}…` : barNotes[0].body}{barNotes.length > 1 ? ` (+${barNotes.length - 1})` : ""}</span>
          )}
        </div>
      )}
      <div ref={container} className="chart-canvas" role="img" aria-label={`${data.symbol} daily ${chartType === "candle" ? "candlestick" : "line"} chart, ${data.range} range`} />
    </div>
  );
}
