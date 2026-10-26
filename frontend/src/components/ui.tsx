import type { PropsWithChildren, ReactNode } from "react";
import { timestamp } from "../lib/format";

export function StatCell({
  label,
  value,
  detail,
  tone,
}: {
  label: string;
  value: ReactNode;
  detail: ReactNode;
  tone?: "positive" | "negative" | "warning";
}) {
  return (
    <div className="stat-cell">
      <span className="compact-label">{label}</span>
      <strong className={tone}>{value}</strong>
      <small className={tone}>{detail}</small>
    </div>
  );
}

export function DataPanel({
  title,
  meta,
  actions,
  className = "",
  children,
}: PropsWithChildren<{
  title: string;
  meta?: ReactNode;
  actions?: ReactNode;
  className?: string;
}>) {
  return (
    <section className={`data-panel ${className}`.trim()}>
      <div className="panel-header">
        <h3>{title}</h3>
        <div className="panel-meta">{actions ?? meta}</div>
      </div>
      {children}
    </section>
  );
}

export function SourceTimestamp({
  source,
  asOf,
  coverage,
  status,
}: {
  source?: string | null;
  asOf?: string | null;
  coverage?: string | null;
  status?: string | null;
}) {
  return (
    <div className="source-line">
      <span>SOURCE · {source || "NOT AVAILABLE"}</span>
      <span>AS OF · {timestamp(asOf)}</span>
      {coverage && <span>COVERAGE · {coverage}</span>}
      {status && <span>STATUS · {status}</span>}
    </div>
  );
}

export function MissingDataWarning({
  title = "NOT AVAILABLE",
  reason,
}: {
  title?: string;
  reason: string;
}) {
  return (
    <div className="missing-state" role="status">
      <strong>{title}</strong>
      <p>{reason}</p>
    </div>
  );
}

export function EmptyState({ title, children }: PropsWithChildren<{ title: string }>) {
  return (
    <div className="empty-state">
      <strong>{title}</strong>
      <div>{children}</div>
    </div>
  );
}

export function ViewHeader({
  title,
  subtitle,
  asOf,
}: {
  title: string;
  subtitle: string;
  asOf?: string | null;
}) {
  return (
    <div className="view-header">
      <div>
        <h2>{title}</h2>
        <p>{subtitle}</p>
      </div>
      {asOf && <span className="view-asof">AS OF · {timestamp(asOf)}</span>}
    </div>
  );
}

export function Meter({ label, value }: { label: string; value: number }) {
  const safe = Math.max(0, Math.min(1, value));
  return (
    <div className="meter-row">
      <div>
        <span>{label}</span>
        <div className="meter" aria-hidden="true"><i style={{ width: `${safe * 100}%` }} /></div>
      </div>
      <strong>{new Intl.NumberFormat("en-CA", { style: "percent", maximumFractionDigits: 1 }).format(safe)}</strong>
    </div>
  );
}

export function Donut({
  segments,
  label,
  centerLabel = "Allocation",
}: {
  segments: Array<{ label: string; value: number; color: string }>;
  label: string;
  centerLabel?: string;
}) {
  const total = segments.reduce((sum, row) => sum + row.value, 0);
  let cursor = 0;
  const stops = total > 0
    ? segments.map((row) => {
        const start = (cursor / total) * 100;
        cursor += row.value;
        const end = (cursor / total) * 100;
        return `${row.color} ${start}% ${end}%`;
      }).join(", ")
    : "#2a3038 0 100%";
  return (
    <div className="donut-wrap">
      <div
        className="donut"
        role="img"
        aria-label={label}
        style={{ background: `conic-gradient(${stops})` }}
      >
        <span>{centerLabel}</span>
      </div>
      <div className="donut-legend">
        {segments.map((row) => (
          <div key={row.label}>
            <i style={{ background: row.color }} />
            <span>{row.label}</span>
            <strong>{total ? `${((row.value / total) * 100).toFixed(1)}%` : "—"}</strong>
          </div>
        ))}
      </div>
    </div>
  );
}

export function ConfirmationDialog({
  open,
  title,
  description,
  confirmLabel,
  danger = false,
  onConfirm,
  onCancel,
}: {
  open: boolean;
  title: string;
  description: string;
  confirmLabel: string;
  danger?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  if (!open) return null;
  return (
    <div className="dialog-backdrop" role="presentation">
      <div
        aria-labelledby="confirmation-title"
        aria-describedby="confirmation-description"
        aria-modal="true"
        className="confirmation-dialog"
        role="dialog"
      >
        <h2 id="confirmation-title">{title}</h2>
        <p id="confirmation-description">{description}</p>
        <div className="dialog-actions">
          <button className="action" type="button" onClick={onCancel}>CANCEL</button>
          <button className={`action ${danger ? "danger" : "primary"}`} type="button" onClick={onConfirm}>
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
