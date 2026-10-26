import type { Holding } from "../types";

export function cad(value: string | number | null | undefined): string {
  if (value == null || !Number.isFinite(Number(value))) return "NOT AVAILABLE";
  return new Intl.NumberFormat("en-CA", {
    style: "currency",
    currency: "CAD",
    maximumFractionDigits: 2,
  }).format(Number(value));
}

export function amount(value: string | null | undefined, currency?: string | null): string {
  if (value == null || !Number.isFinite(Number(value))) return "—";
  const formatted = new Intl.NumberFormat("en-CA", { maximumFractionDigits: 6 }).format(Number(value));
  return currency ? `${formatted} ${currency}` : formatted;
}

export function percent(value: string | number | null | undefined, digits = 1): string {
  if (value == null || !Number.isFinite(Number(value))) return "NOT AVAILABLE";
  return new Intl.NumberFormat("en-CA", {
    style: "percent",
    maximumFractionDigits: digits,
  }).format(Number(value));
}

export function signedCad(value: string | number | null | undefined): string {
  if (value == null || !Number.isFinite(Number(value))) return "NOT AVAILABLE";
  const rendered = cad(value);
  return Number(value) > 0 ? `+${rendered}` : rendered;
}

export function timestamp(value: string | null | undefined): string {
  if (!value) return "NOT AVAILABLE";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.valueOf())) return value;
  return parsed.toLocaleString("en-CA", {
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
  const parsed = new Date(value);
  if (Number.isNaN(parsed.valueOf())) return value.slice(0, 10);
  return parsed.toLocaleDateString("en-CA", {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

export function statusLabel(holding: Holding): string {
  if (!holding.price) return "MISSING";
  if (holding.price_stale || holding.data_status.toLowerCase().includes("stale")) {
    return holding.quote_status === "imported" ? "STALE / IMPORTED" : "STALE";
  }
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
