import { type FormEvent, type ReactNode, useEffect, useState } from "react";
import { cad, percent, timestamp } from "../lib/format";
import type { ClaudePrompt, HistoryPoint, PriceCapabilities, ReviewPrivacy, SnapTradeStatus } from "../types";
import { connectionLabel } from "../components/AppShell";
import { DataPanel, SourceTimestamp, ViewHeader } from "../components/ui";

export function SettingsPage({
  status,
  priceCapabilities,
  history,
  privacy,
  prompts,
  busy,
  previewOpen,
  onPrivacy,
  onConnect,
  onCheck,
  onSync,
  onRefresh,
  onDisconnect,
  onDeleteData,
  onSavePrompt,
}: {
  status: SnapTradeStatus | null;
  priceCapabilities: PriceCapabilities | null;
  history: HistoryPoint[];
  privacy: ReviewPrivacy;
  prompts: ClaudePrompt[];
  busy: boolean;
  previewOpen: boolean;
  onPrivacy: (privacy: ReviewPrivacy) => void;
  onConnect: () => void;
  onCheck: () => void;
  onSync: () => void;
  onRefresh: () => void;
  onDisconnect: () => void;
  onDeleteData: () => void;
  onSavePrompt: (prompt: { id?: string; name: string; prompt_text: string }) => void;
}) {
  const [promptId, setPromptId] = useState("");
  const [promptName, setPromptName] = useState("");
  const [promptText, setPromptText] = useState("");
  const [showHistory, setShowHistory] = useState(false);
  const connected = status?.connection_status === "connected_read_only";
  const canConnect = Boolean(status?.adapter_enabled && ["not_checked", "not_connected"].includes(status.connection_status));
  const canDisconnect = Boolean(status?.adapter_enabled && ["connected_read_only", "disabled_connection", "rejected_trade_enabled", "disconnect_pending"].includes(status.connection_status));

  useEffect(() => {
    const selected = prompts.find((prompt) => prompt.id === promptId) ?? prompts[0];
    if (selected) {
      setPromptId(selected.id);
      setPromptName(selected.name);
      setPromptText(selected.prompt_text);
    }
  }, [promptId, prompts]);

  function choosePrompt(value: string) {
    const selected = prompts.find((prompt) => prompt.id === value);
    setPromptId(value);
    setPromptName(selected?.name ?? "");
    setPromptText(selected?.prompt_text ?? "");
  }

  function savePrompt(event: FormEvent) {
    event.preventDefault();
    onSavePrompt({ id: promptId || undefined, name: promptName, prompt_text: promptText });
  }

  return (
    <>
      <ViewHeader title="Settings and data" subtitle="Local-first configuration, synchronization status and explicit privacy controls" asOf={status?.last_checked_at} />
      <div className="settings-grid">
        <DataPanel title="Brokerage connection" meta={connectionLabel(status).replace("SNAPTRADE · ", "")}>
          <div className="settings-lines">
            <SettingLine label="Provider" value="SnapTrade / Wealthsimple"><button className="action" type="button" disabled={!status?.adapter_enabled || busy} onClick={onCheck}>CHECK STATUS</button></SettingLine>
            <SettingLine label="Last holdings sync" value={timestamp(status?.last_successful_sync_at)}><button className="action" type="button" disabled={!connected || !status?.sync_allowed || busy || previewOpen} onClick={onSync}>SYNC</button></SettingLine>
            <SettingLine label="Holdings as of" value={timestamp(status?.holdings_as_of)}><span>{status?.stale ? "STALE" : "LATEST REPORTED"}</span></SettingLine>
            <SettingLine label="Last connection check" value={timestamp(status?.last_checked_at)}><span>{status?.connection_permission === "read" ? "READ ONLY" : "NO READ PERMISSION"}</span></SettingLine>
            <SettingLine label="Next sync eligible" value={status?.sync_allowed ? "AVAILABLE NOW" : timestamp(status?.next_sync_allowed_at)}><span>10 MINIMUM</span></SettingLine>
            <SettingLine label="Market prices" value={`${priceCapabilities?.provider ?? "NOT AVAILABLE"} · separate from holdings`}><button className="action" type="button" disabled={busy} onClick={onRefresh}>REFRESH</button></SettingLine>
          </div>
          {status?.warnings.map((warning) => <div className="panel-warning" key={warning}>{warning}</div>)}
          {!status?.adapter_enabled && <div className="panel-warning">The adapter is disabled by default. Credentials cannot be entered here; real Personal API keys remain in macOS Keychain.</div>}
          <div className="connection-actions">
            <span>Wealthsimple credentials and MFA are entered only in SnapTrade’s hosted portal.</span>
            {!connected && <button className="action primary" type="button" disabled={!canConnect || busy} onClick={onConnect}>CONNECT</button>}
            <button className="action danger" type="button" disabled={!canDisconnect || busy} onClick={onDisconnect}>DISCONNECT</button>
          </div>
          <SourceTimestamp source="SnapTrade Personal API Key · account data only" asOf={status?.holdings_as_of} status={status?.connection_permission === "read" ? "READ ONLY" : "NO ACTIVE READ CONNECTION"} />
        </DataPanel>
        <DataPanel title="Claude review privacy" meta="LOCAL DEFAULTS">
          <div className="privacy-options">
            <label><input type="checkbox" checked={privacy.weights_only} onChange={(event) => onPrivacy({ ...privacy, weights_only: event.target.checked })} />Use weights-only mode</label>
            <label><input type="checkbox" checked={!privacy.include_quantities} disabled={privacy.weights_only} onChange={(event) => onPrivacy({ ...privacy, include_quantities: !event.target.checked })} />Exclude quantities</label>
            <label><input type="checkbox" checked={!privacy.include_dollar_values} disabled={privacy.weights_only} onChange={(event) => onPrivacy({ ...privacy, include_dollar_values: !event.target.checked })} />Exclude dollar values</label>
            <label><input type="checkbox" checked={privacy.include_account_type} onChange={(event) => onPrivacy({ ...privacy, include_account_type: event.target.checked })} />Include account type</label>
            <label><input type="checkbox" checked readOnly />Preview exact pack before export</label>
          </div>
          <p className="panel-note">No Claude API integration. Review packs leave the application only when you manually copy or export them.</p>
        </DataPanel>
      </div>
      <div className="settings-grid below-grid">
        <DataPanel title="Reusable Claude prompt" meta="SAVED LOCALLY">
          <form className="editor-form" onSubmit={savePrompt}>
            <label>PROMPT<select aria-label="Reusable prompt selection" value={promptId} onChange={(event) => choosePrompt(event.target.value)}>{prompts.map((prompt) => <option key={prompt.id} value={prompt.id}>{prompt.name}</option>)}</select></label>
            <label>NAME<input value={promptName} onChange={(event) => setPromptName(event.target.value)} required /></label>
            <label>PROMPT TEXT<textarea className="large" value={promptText} onChange={(event) => setPromptText(event.target.value)} required /></label>
            <div className="form-actions"><button className="action primary" type="submit" disabled={busy}>SAVE PROMPT</button></div>
          </form>
        </DataPanel>
        <DataPanel title="Data controls" meta="CONFIRMATIONS REQUIRED">
          <div className="settings-lines">
            <SettingLine label="Reporting currency" value="CAD"><span>FIXED</span></SettingLine>
            <SettingLine label="Historical snapshots" value={`${history.length} immutable valuation snapshot${history.length === 1 ? "" : "s"}`}><button className="action" type="button" onClick={() => setShowHistory((shown) => !shown)}>{showHistory ? "HIDE HISTORY" : "VIEW HISTORY"}</button></SettingLine>
            <SettingLine label="Runtime storage" value="~/.canadian-portfolio-manager/"><span>OUTSIDE GIT</span></SettingLine>
            <SettingLine label="Disconnect" value="Stops future synchronization; preserves local snapshots"><button className="action danger" type="button" disabled={!canDisconnect || busy} onClick={onDisconnect}>DISCONNECT</button></SettingLine>
            <SettingLine label="Local brokerage data" value="Deletes SnapTrade-derived snapshots and normalized activities; preserves legacy snapshots"><button className="action danger" type="button" disabled={busy} onClick={onDeleteData}>DELETE LOCAL DATA</button></SettingLine>
          </div>
          {showHistory && (
            <div className="table-wrap">
              <table className="data-table">
                <thead><tr><th>Snapshot timestamp</th><th className="numeric">Market value</th><th className="numeric">Price coverage</th></tr></thead>
                <tbody>{history.length ? history.map((row) => <tr key={row.id}><td>{timestamp(row.created_at)}</td><td className="numeric">{cad(row.total_cad)}</td><td className="numeric">{percent(row.position_coverage_pct)}</td></tr>) : <tr><td colSpan={3} className="unavailable-cell">NO HISTORICAL VALUATION SNAPSHOTS</td></tr>}</tbody>
              </table>
            </div>
          )}
          <p className="panel-note">No raw portfolio upload, account number, name, address, brokerage credential, consumer key or client ID is stored in SQLite.</p>
        </DataPanel>
      </div>
    </>
  );
}

function SettingLine({ label, value, children }: { label: string; value: string; children: ReactNode }) {
  return <div className="setting-line"><span>{label}</span><strong>{value}</strong><div>{children}</div></div>;
}
