import {
  CandlestickSeries,
  ColorType,
  CrosshairMode,
  createChart,
  HistogramSeries,
  type IChartApi,
  LineSeries,
  LineStyle,
  type MouseEventParams,
  type Time,
} from "lightweight-charts";
import { useEffect, useMemo, useRef, useState } from "react";
import { compactNumber, price, signedPercent } from "../lib/format";
import type { ChartPayload, IndicatorName, PriceBar } from "../types";

export type ChartType = "candle" | "line";
export type Overlay = "ema20" | "ema50" | "sma200" | "bollinger";
export type LowerPane = "rsi" | "macd" | "none";

export const OVERLAY_LABELS: Record<Overlay, string> = {
  ema20: "EMA 20",
  ema50: "EMA 50",
  sma200: "SMA 200",
  bollinger: "Bollinger",
};

const COLORS = {
  background: "#11151a",
  text: "#8f98a5",
  grid: "#1b2027",
  border: "#2a3038",
  up: "#70cfa5",
  down: "#eb8686",
  line: "#78a9dd",
  ema20: "#78a9dd",
  ema50: "#e8c56b",
  sma200: "#b190dd",
  band: "#5e6874",
  volumeUp: "rgba(112, 207, 165, 0.32)",
  volumeDown: "rgba(235, 134, 134, 0.32)",
};

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
}: {
  data: ChartPayload;
  chartType: ChartType;
  overlays: Overlay[];
  lowerPane: LowerPane;
}) {
  const container = useRef<HTMLDivElement>(null);
  const [hovered, setHovered] = useState<number | null>(null);
  const indexByDate = useMemo(() => new Map(data.bars.map((bar, index) => [bar.date, index])), [data]);
  const overlayKey = overlays.join(",");

  useEffect(() => {
    if (!container.current || !data.bars.length) return;
    const chart: IChartApi = createChart(container.current, {
      autoSize: true,
      layout: {
        background: { type: ColorType.Solid, color: COLORS.background },
        textColor: COLORS.text,
        fontSize: 10,
        fontFamily: "Inter, -apple-system, BlinkMacSystemFont, sans-serif",
        attributionLogo: false,
        panes: { separatorColor: COLORS.border, separatorHoverColor: COLORS.border, enableResize: false },
      },
      grid: { vertLines: { color: COLORS.grid }, horzLines: { color: COLORS.grid } },
      rightPriceScale: { borderColor: COLORS.border },
      timeScale: { borderColor: COLORS.border, rightOffset: 3 },
      crosshair: { mode: CrosshairMode.Normal },
    });
    const { bars, indicators } = data;
    // Rebuild from the joined key so a new array holding the same overlays does not redraw the chart.
    const activeOverlays = overlayKey ? (overlayKey.split(",") as Overlay[]) : [];
    const series = (name: IndicatorName) => points(bars, indicators[name]);

    if (chartType === "candle") {
      chart.addSeries(CandlestickSeries, {
        upColor: COLORS.up,
        downColor: COLORS.down,
        borderVisible: false,
        wickUpColor: COLORS.up,
        wickDownColor: COLORS.down,
      }).setData(bars.map((bar) => ({ time: bar.date as Time, open: bar.open, high: bar.high, low: bar.low, close: bar.close })));
    } else {
      chart.addSeries(LineSeries, { color: COLORS.line, lineWidth: 2 })
        .setData(bars.map((bar) => ({ time: bar.date as Time, value: bar.close })));
    }

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
    chart.subscribeCrosshairMove(onMove);
    return () => {
      chart.unsubscribeCrosshairMove(onMove);
      chart.remove();
    };
  }, [data, chartType, overlayKey, lowerPane, indexByDate]);

  const index = hovered ?? data.bars.length - 1;
  const bar = data.bars[index];
  const previous = data.bars[index - 1];
  const change = bar && previous ? bar.close / previous.close - 1 : null;

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
        </div>
      )}
      <div ref={container} className="chart-canvas" role="img" aria-label={`${data.symbol} daily ${chartType === "candle" ? "candlestick" : "line"} chart, ${data.range} range`} />
    </div>
  );
}
