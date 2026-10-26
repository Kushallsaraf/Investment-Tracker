import type { Holding } from "../types";

export function usd(value: string | number | null | undefined): string {
  if (value == null || !Number.isFinite(Number(value))) return "NOT AVAILABLE";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2,
  }).format(Number(value));
}

export function amount(value: string | null | undefined, currency?: string | null): string {
  if (value == null || !Number.isFinite(Number(value))) return "—";
  const formatted = new Intl.NumberFormat("en-US", { maximumFractionDigits: 6 }).format(Number(value));
  return currency ? `${formatted} ${currency}` : formatted;
}

export function percent(value: string | number | null | undefined, digits = 1): string {
  if (value == null || !Number.isFinite(Number(value))) return "NOT AVAILABLE";
  return new Intl.NumberFormat("en-US", {
    style: "percent",
    maximumFractionDigits: digits,
  }).format(Number(value));
}

export function signedUsd(value: string | number | null | undefined): string {
  if (value == null || !Number.isFinite(Number(value))) return "NOT AVAILABLE";
  const rendered = usd(value);
  return Number(value) > 0 ? `+${rendered}` : rendered;
}

export function timestamp(value: string | null | undefined): string {
  if (!value) return "NOT AVAILABLE";
  if (/^\d{4}-\d{2}-\d{2}$/.test(value)) return dateOnly(value);
  const parsed = new Date(value);
  if (Number.isNaN(parsed.valueOf())) return value;
  return parsed.toLocaleString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    timeZoneName: "short",
  });
}

export function dateOnly(value: string | null | undefined): string {
  if (!value) return "NOT AVAILABLE";
  // Plain ISO dates are calendar days, not UTC instants; parse them in local time.
  const day = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  const parsed = day ? new Date(Number(day[1]), Number(day[2]) - 1, Number(day[3])) : new Date(value);
  if (Number.isNaN(parsed.valueOf())) return value.slice(0, 10);
  return parsed.toLocaleDateString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

export function statusLabel(holding: Holding): string {
  if (!holding.price) return "MISSING";
  if (holding.price_stale || holding.data_status.toLowerCase().includes("stale")) return "STALE";
  const base = (holding.quote_status ?? "AVAILABLE").replaceAll("_", " ").toUpperCase();
  return holding.delay_minutes ? `${base} ${holding.delay_minutes}M` : base;
}

export function statusTone(holding: Holding): "positive" | "warning" | "negative" {
  if (!holding.price) return "negative";
  return holding.price_stale || holding.data_status.toLowerCase().includes("stale")
    ? "warning"
    : "positive";
}

export function decisionLabel(value: string | null | undefined): string {
  return value ? value.replaceAll("_", " ") : "WATCH";
}
