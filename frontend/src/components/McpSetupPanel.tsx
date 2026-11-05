import { useEffect, useState } from "react";
import { getMcpSetup } from "../api";
import type { McpCheck, McpSetup } from "../types";

const CHECK_LABELS: Record<keyof McpSetup["checks"], string> = {
  python: "Python",
  mcp_package: "MCP package",
  sec_contact: "SEC contact",
};

/** Setup steps for connecting Claude Desktop, with this computer's paths filled in. */
export function McpSetupPanel() {
  const [setup, setSetup] = useState<McpSetup | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    getMcpSetup().then(setSetup).catch((cause) => setError(cause instanceof Error ? cause.message : "Setup details are unavailable"));
  }, []);

  if (error) return <div className="status-banner error" role="alert" style={{ margin: 0 }}>{error}</div>;
  if (!setup) return <p className="panel-note" style={{ margin: 0 }}>Loading setup details…</p>;

  const config = JSON.stringify(setup.config, null, 2);
  async function copy() {
    try {
      await navigator.clipboard.writeText(config);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      setError("Copy failed. Select the text and copy it instead.");
    }
  }

  return (
    <>
      <p className="panel-note" style={{ margin: 0 }}>
        Claude Desktop can read your research data, add notes and watchlist tickers, and propose exit plans that you accept or reject here. It runs on this computer and has no way to trade.
      </p>

      <section className="setup-section" aria-label="Checks">
        <h3>This computer</h3>
        <ul className="setup-checks">
          {(Object.entries(setup.checks) as Array<[keyof McpSetup["checks"], McpCheck]>).map(([key, check]) => (
            <li key={key}>
              <span className={check.ok ? "ok" : "missing"} aria-hidden="true">{check.ok ? "✓" : "!"}</span>
              <span>{CHECK_LABELS[key]}</span>
              <span>{check.ok ? "" : "Needs attention · "}{check.detail}</span>
            </li>
          ))}
        </ul>
      </section>

      <section className="setup-section" aria-label="Setup steps">
        <h3>Set it up</h3>
        <ol className="setup-steps">
          <li>
            Open Claude Desktop → <strong>Settings → Developer → Edit Config</strong>.
            <p>This opens <code>{setup.config_file}</code>.</p>
          </li>
          <li>
            Paste this in. If the file already has <code>mcpServers</code>, add the <code>{setup.server_name}</code> entry inside it.
            <figure className="code-block" aria-label="Claude Desktop configuration">
              <pre>{config}</pre>
              <button type="button" className="action" onClick={() => void copy()}>{copied ? "Copied" : "Copy"}</button>
            </figure>
            {!setup.checks.sec_contact.ok && <p>Replace the SEC contact with your name and email so fundamentals and insider data load.</p>}
          </li>
          <li>
            Quit and reopen Claude Desktop.
            <p>If macOS asks whether Claude can access the folder this project is in, allow it.</p>
          </li>
          <li>
            In a new chat, open the tools menu and check that <code>{setup.server_name}</code> is listed.
            <p>If it isn't, Settings → Developer shows the server's error log.</p>
          </li>
        </ol>
      </section>

      <section className="setup-section" aria-label="Using it">
        <h3>Use it</h3>
        <ol className="setup-steps">
          <li>Ask in plain English, for example "What's the technical setup on GFS?" Claude asks before using each tool for the first time.</li>
          <li>Run <strong>{setup.prompt}</strong> from the prompts menu (+) with a ticker. It ends by offering to save an exit plan.</li>
          <li>Review proposals under Research → Exit plan or Portfolio → Alerts. Nothing changes until you accept.</li>
        </ol>
      </section>

      <section className="setup-section" aria-label="Tools">
        <h3>What Claude can do</h3>
        <dl className="setup-tools">
          {Object.entries(setup.read_tools).map(([name, detail]) => <div key={name}><dt><code>{name}</code></dt><dd>{detail}</dd></div>)}
          {Object.entries(setup.write_tools).map(([name, detail]) => <div key={name}><dt><code>{name}</code></dt><dd>{detail}</dd></div>)}
        </dl>
      </section>

      <div className="source-line" style={{ borderTop: 0, padding: 0 }}>
        <span>Data folder · {setup.data_folder}</span>
        <span>The app doesn't need to be running</span>
      </div>
    </>
  );
}
