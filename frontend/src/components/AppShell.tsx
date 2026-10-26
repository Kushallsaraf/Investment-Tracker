import type { PropsWithChildren } from "react";
import { timestamp } from "../lib/format";
import type { SnapTradeStatus } from "../types";

export const MAIN_TABS = [
  "Dashboard",
  "Holdings",
  "Analytics",
  "Income",
  "Activity",
  "Decisions",
  "Research",
  "Settings",
] as const;

export type MainTab = (typeof MAIN_TABS)[number];

export function connectionLabel(status: SnapTradeStatus | null): string {
  if (!status) return "SNAPTRADE · CHECKING";
  const labels: Record<string, string> = {
    adapter_disabled: "SNAPTRADE · DISABLED",
    not_checked: "SNAPTRADE · NOT CHECKED",
    credentials_missing: "SNAPTRADE · KEYCHAIN REQUIRED",
    not_connected: "SNAPTRADE · NOT CONNECTED",
    connected_read_only: "SNAPTRADE · READ ONLY",
    disabled_connection: "SNAPTRADE · CONNECTION DISABLED",
    rejected_trade_enabled: "SNAPTRADE · REJECTED",
    disconnect_pending: "SNAPTRADE · DISCONNECTING",
  };
  return labels[status.connection_status]
    ?? `SNAPTRADE · ${status.connection_status.replaceAll("_", " ").toUpperCase()}`;
}

export function AppShell({
  activeTab,
  onTab,
  holdingsAsOf,
  snaptradeStatus,
  children,
}: PropsWithChildren<{
  activeTab: MainTab;
  onTab: (tab: MainTab) => void;
  holdingsAsOf: string | null;
  snaptradeStatus: SnapTradeStatus | null;
}>) {
  const connectionTone = snaptradeStatus?.connection_status === "connected_read_only"
    ? "positive"
    : snaptradeStatus?.connection_status === "rejected_trade_enabled"
      ? "negative"
      : "warning";
  return (
    <div className="app-shell">
      <header className="global-header">
        <div className="top-line">
          <div className="brand">
            <span className="brand-mark">IT</span>
            <div>
              <h1>Investment Tracker</h1>
              <p>Canadian portfolio · CAD reporting</p>
            </div>
          </div>
          <div className="header-meta">
            <span>Holdings as of {timestamp(holdingsAsOf)}</span>
            <strong className={connectionTone}>{connectionLabel(snaptradeStatus)}</strong>
          </div>
        </div>
        <nav aria-label="Investment Tracker sections">
          <div className="main-navigation" role="tablist" aria-label="Main views">
            {MAIN_TABS.map((tab) => (
              <button
                type="button"
                role="tab"
                key={tab}
                aria-selected={activeTab === tab}
                onClick={() => onTab(tab)}
              >
                {tab}
              </button>
            ))}
          </div>
        </nav>
      </header>
      <main className="workspace">{children}</main>
      <footer className="global-footer">
        Research only · No orders · No brokerage credentials · Exact timestamps · Missing data shown explicitly
      </footer>
    </div>
  );
}

export function StatusBanner({
  error,
  notice,
}: {
  error: string | null;
  notice: string | null;
}) {
  return (
    <>
      {error && <div className="status-banner error" role="alert">ERROR · {error}</div>}
      {notice && <div className="status-banner notice" role="status">{notice}</div>}
    </>
  );
}
