import { type FormEvent, type ReactNode, useEffect, useState } from "react";
import { percent, timestamp, usd } from "../lib/format";
import type { ClaudePrompt, HistoryPoint, PortfolioStatus, PriceCapabilities, ReviewPrivacy } from "../types";
import { originLabel } from "../components/AppShell";
import { DataPanel, SourceTimestamp, ViewHeader } from "../components/ui";

export function SettingsPage({
  status,
  priceCapabilities,
  history,
  privacy,
  prompts,
  busy,
  onPrivacy,
  onRefresh,
  onLoadDemo,
  onDeleteData,
  onSavePrompt,
}: {
  status: PortfolioStatus | null;
  priceCapabilities: PriceCapabilities | null;
  history: HistoryPoint[];
  privacy: ReviewPrivacy;
  prompts: ClaudePrompt[];
  busy: boolean;
  onPrivacy: (privacy: ReviewPrivacy) => void;
  onRefresh: () => void;
  onLoadDemo: () => void;
  onDeleteData: () => void;
  onSavePrompt: (prompt: { id?: string; name: string; prompt_text: string }) => void;
}) {
  const [promptId, setPromptId] = useState("");
  const [promptName, setPromptName] = useState("");
  const [promptText, setPromptText] = useState("");
  const [showHistory, setShowHistory] = useState(false);
  const hasManualData = status?.data_origin === "manual";

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
      <ViewHeader title="Settings and data" subtitle="Local-first configuration, portfolio data source and explicit privacy controls" asOf={status?.latest_snapshot_at} />
      <div className="settings-grid">
        <DataPanel title="Portfolio data" meta={originLabel(status?.data_origin)}>
          <div className="settings-lines">
            <SettingLine label="Data source" value={status?.data_origin === "demo" ? "Synthetic demo portfolio" : status?.data_origin === "manual" ? "Positions entered manually" : "No holdings yet"}><span>NO BROKERAGE CONNECTION</span></SettingLine>
            <SettingLine label="Latest holdings snapshot" value={timestamp(status?.latest_snapshot_at)}><span>{status?.snapshot_count ?? 0} SNAPSHOTS</span></SettingLine>
            <SettingLine label="Demo portfolio" value="Illustrative US stocks, ETFs, cash and activities"><button className="action" type="button" disabled={busy || hasManualData} onClick={onLoadDemo}>LOAD DEMO</button></SettingLine>
            <SettingLine label="Market prices" value={`${priceCapabilities?.provider ?? "NOT AVAILABLE"} · separate from holdings`}><button className="action" type="button" disabled={busy || !status?.snapshot_count} onClick={onRefresh}>REFRESH</button></SettingLine>
          </div>
          {hasManualData && <div className="panel-warning">The demo portfolio is unavailable while manual holdings exist, so your data is never overwritten. Delete local portfolio data first to load it.</div>}
          <SourceTimestamp source="Local SQLite snapshots" asOf={status?.latest_snapshot_at} status="NO EXTERNAL ACCOUNT ACCESS" />
        </DataPanel>
        <DataPanel title="Claude review privacy" meta="LOCAL DEFAULTS">
          <div className="privacy-options">
            <label><input type="checkbox" checked={privacy.weights_only} onChange={(event) => onPrivacy({ ...privacy, weights_only: event.target.checked })} />Use weights-only mode</label>
            <label><input type="checkbox" checked={!privacy.include_quantities} disabled={privacy.weights_only} onChange={(event) => onPrivacy({ ...privacy, include_quantities: !event.target.checked })} />Exclude quantities</label>
            <label><input type="checkbox" checked={!privacy.include_dollar_values} disabled={privacy.weights_only} onChange={(event) => onPrivacy({ ...privacy, include_dollar_values: !event.target.checked })} />Exclude dollar values</label>
            <label><input type="checkbox" checked={privacy.include_account_name} onChange={(event) => onPrivacy({ ...privacy, include_account_name: event.target.checked })} />Include account name</label>
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
            <SettingLine label="Reporting currency" value="USD"><span>US LISTINGS ONLY</span></SettingLine>
            <SettingLine label="Historical snapshots" value={`${history.length} immutable valuation snapshot${history.length === 1 ? "" : "s"}`}><button className="action" type="button" onClick={() => setShowHistory((shown) => !shown)}>{showHistory ? "HIDE HISTORY" : "VIEW HISTORY"}</button></SettingLine>
            <SettingLine label="Runtime storage" value="~/.portfolio-manager/"><span>OUTSIDE GIT</span></SettingLine>
            <SettingLine label="Local portfolio data" value="Deletes holdings, valuations, quotes and activities; keeps decisions and AI reviews"><button className="action danger" type="button" disabled={busy} onClick={onDeleteData}>DELETE LOCAL DATA</button></SettingLine>
          </div>
          {showHistory && (
            <div className="table-wrap">
              <table className="data-table">
                <thead><tr><th>Snapshot timestamp</th><th className="numeric">Market value</th><th className="numeric">Price coverage</th></tr></thead>
                <tbody>{history.length ? history.map((row) => <tr key={row.id}><td>{timestamp(row.created_at)}</td><td className="numeric">{usd(row.total_value)}</td><td className="numeric">{percent(row.position_coverage_pct)}</td></tr>) : <tr><td colSpan={3} className="unavailable-cell">NO HISTORICAL VALUATION SNAPSHOTS</td></tr>}</tbody>
              </table>
            </div>
          )}
          <p className="panel-note">No account number, name, address or brokerage credential is collected or stored.</p>
        </DataPanel>
      </div>
    </>
  );
}

function SettingLine({ label, value, children }: { label: string; value: string; children: ReactNode }) {
  return <div className="setting-line"><span>{label}</span><strong>{value}</strong><div>{children}</div></div>;
}
