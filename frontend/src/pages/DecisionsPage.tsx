import { type FormEvent, useEffect, useState } from "react";
import { dateOnly, decisionLabel, timestamp } from "../lib/format";
import type { DecisionName, JournalEntry, JournalPayload } from "../types";
import { DataPanel, EmptyState, SourceTimestamp, ViewHeader } from "../components/ui";

const DECISIONS: DecisionName[] = ["WATCH", "HOLD", "CONSIDER_ADD", "CONSIDER_REDUCE", "EXIT_CANDIDATE"];
const ROLES = ["", "CORE", "DIVERSIFIER", "INCOME", "SPECULATIVE"];
const TRIGGER_TYPES = [
  "PRICE_BELOW", "PRICE_ABOVE", "CONSIDER_ADD_RANGE", "CONSIDER_REDUCE_RANGE",
  "DATE", "AFTER_EARNINGS", "THESIS_NOTE",
];

type ProfileForm = {
  portfolio_role: string;
  thesis_strength: string;
  why_owned: string;
  supporting_evidence: string;
  principal_risks: string;
  invalidation_conditions: string;
  maximum_weight: string;
  source_links: string;
  last_reviewed_date: string;
  next_review_date: string;
};

const EMPTY_PROFILE: ProfileForm = {
  portfolio_role: "", thesis_strength: "", why_owned: "", supporting_evidence: "",
  principal_risks: "", invalidation_conditions: "", maximum_weight: "",
  source_links: "", last_reviewed_date: "", next_review_date: "",
};

export function DecisionsPage({
  journal,
  busy,
  onDecision,
  onProfile,
  onTrigger,
}: {
  journal: JournalPayload | null;
  busy: boolean;
  onDecision: (
    instrumentId: string,
    decision: DecisionName,
    reason?: string,
    claudeDisposition?: "ACCEPTED" | "REJECTED" | "CONSIDERING" | null,
    reviewDueDate?: string | null,
  ) => void;
  onProfile: (instrumentId: string, profile: Record<string, unknown>) => void;
  onTrigger: (instrumentId: string, trigger: Record<string, unknown>) => void;
}) {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [profile, setProfile] = useState<ProfileForm>(EMPTY_PROFILE);
  const [triggerType, setTriggerType] = useState("PRICE_ABOVE");
  const [lower, setLower] = useState("");
  const [upper, setUpper] = useState("");
  const [triggerDate, setTriggerDate] = useState("");
  const [triggerReason, setTriggerReason] = useState("");
  const [triggerNote, setTriggerNote] = useState("");
  const [triggerExpiry, setTriggerExpiry] = useState("");
  const [decisionChoice, setDecisionChoice] = useState<DecisionName>("WATCH");
  const [decisionReason, setDecisionReason] = useState("");
  const [decisionDisposition, setDecisionDisposition] = useState("");
  const [decisionReviewDue, setDecisionReviewDue] = useState("");
  const selected = (journal?.entries ?? []).find((entry) => entry.holding.instrument_id === selectedId)
    ?? journal?.entries[0]
    ?? null;

  useEffect(() => {
    if (!selected) return;
    if (!selectedId) setSelectedId(selected.holding.instrument_id);
    setDecisionChoice(selected.decision?.decision ?? "WATCH");
    setDecisionReason(selected.decision?.reason ?? "");
    setDecisionReviewDue(selected.decision?.review_due_date ?? "");
    const existing = selected.profile;
    setProfile(existing ? {
      portfolio_role: existing.portfolio_role ?? "",
      thesis_strength: existing.thesis_strength?.toString() ?? "",
      why_owned: existing.why_owned,
      supporting_evidence: existing.supporting_evidence,
      principal_risks: existing.principal_risks,
      invalidation_conditions: existing.invalidation_conditions,
      maximum_weight: existing.maximum_weight ?? "",
      source_links: existing.source_links.join("\n"),
      last_reviewed_date: existing.last_reviewed_date ?? "",
      next_review_date: existing.next_review_date ?? "",
    } : EMPTY_PROFILE);
  }, [selected, selectedId]);

  function saveProfile(event: FormEvent) {
    event.preventDefault();
    if (!selected) return;
    onProfile(selected.holding.instrument_id, {
      portfolio_role: profile.portfolio_role || null,
      thesis_strength: profile.thesis_strength ? Number(profile.thesis_strength) : null,
      why_owned: profile.why_owned,
      supporting_evidence: profile.supporting_evidence,
      principal_risks: profile.principal_risks,
      invalidation_conditions: profile.invalidation_conditions,
      maximum_weight: profile.maximum_weight || null,
      source_links: profile.source_links.split("\n").map((line) => line.trim()).filter(Boolean),
      last_reviewed_date: profile.last_reviewed_date || null,
      next_review_date: profile.next_review_date || null,
    });
  }

  function saveDecision(event: FormEvent) {
    event.preventDefault();
    if (!selected) return;
    onDecision(
      selected.holding.instrument_id,
      decisionChoice,
      decisionReason,
      decisionDisposition
        ? decisionDisposition as "ACCEPTED" | "REJECTED" | "CONSIDERING"
        : null,
      decisionReviewDue || null,
    );
  }

  function saveTrigger(event: FormEvent) {
    event.preventDefault();
    if (!selected) return;
    onTrigger(selected.holding.instrument_id, {
      trigger_type: triggerType,
      lower_value: lower || null,
      upper_value: upper || null,
      trigger_date: triggerDate || null,
      reason: triggerReason,
      note: triggerNote,
      expires_at: triggerExpiry || null,
    });
  }

  return (
    <>
      <ViewHeader title="Decisions and conviction" subtitle="Your decisions remain separate from Claude’s non-binding suggestions" asOf={journal?.generated_at} />
      <DataPanel title="Decision worksheet" meta="MY DECISION ≠ CLAUDE SUGGESTION">
        {!journal?.entries.length ? <EmptyState title="NO HOLDINGS">A current holding snapshot is required before recording decisions.</EmptyState> : (
          <div className="table-wrap">
            <table className="data-table decision-table">
              <thead><tr><th>Holding</th><th>Portfolio role</th><th className="numeric">Thesis strength</th><th>My decision</th><th>Claude suggestion</th><th>Next review</th><th>Active trigger</th></tr></thead>
              <tbody>{journal.entries.map((entry) => <DecisionRow key={entry.holding.instrument_id} entry={entry} selected={selected?.holding.instrument_id === entry.holding.instrument_id} onSelect={() => setSelectedId(entry.holding.instrument_id)} onDecision={onDecision} />)}</tbody>
            </table>
          </div>
        )}
      </DataPanel>
      {selected && (
        <div className="two-panel-row">
          <DataPanel title={`Selected thesis · ${selected.holding.canonical_symbol}`} meta="LOCAL DECISION JOURNAL">
            <form className="editor-form decision-record" onSubmit={saveDecision}>
              <div className="editor-section-title">RECORD A DECISION</div>
              <div className="form-grid">
                <label>MY DECISION<select aria-label="Decision to record" value={decisionChoice} onChange={(event) => setDecisionChoice(event.target.value as DecisionName)}>{DECISIONS.map((decision) => <option key={decision}>{decision}</option>)}</select></label>
                <label>CLAUDE SUGGESTION RESPONSE<select aria-label="Claude suggestion response" value={decisionDisposition} onChange={(event) => setDecisionDisposition(event.target.value)}><option value="">NOT APPLICABLE</option><option>ACCEPTED</option><option>REJECTED</option><option>CONSIDERING</option></select></label>
                <label>REVIEW DUE<input aria-label="Decision review due date" type="date" value={decisionReviewDue} onChange={(event) => setDecisionReviewDue(event.target.value)} /></label>
              </div>
              <label>DECISION REASON<textarea aria-label="Decision reason" value={decisionReason} onChange={(event) => setDecisionReason(event.target.value)} required /></label>
              <div className="form-actions"><button className="action primary" type="submit" disabled={busy || !decisionReason.trim()}>RECORD DECISION</button></div>
            </form>
            <form className="editor-form" onSubmit={saveProfile}>
              <div className="editor-section-title">CONVICTION AND THESIS</div>
              <div className="form-grid">
                <label>PORTFOLIO ROLE<select aria-label="Portfolio role" value={profile.portfolio_role} onChange={(event) => setProfile({ ...profile, portfolio_role: event.target.value })}>{ROLES.map((role) => <option key={role} value={role}>{role || "NOT SET"}</option>)}</select></label>
                <label>THESIS STRENGTH<select aria-label="Thesis strength" value={profile.thesis_strength} onChange={(event) => setProfile({ ...profile, thesis_strength: event.target.value })}><option value="">NOT SET</option>{[1, 2, 3, 4, 5].map((score) => <option key={score} value={score}>{score} / 5</option>)}</select></label>
              </div>
              <label>WHY I OWN IT<textarea value={profile.why_owned} onChange={(event) => setProfile({ ...profile, why_owned: event.target.value })} /></label>
              <label>IMPORTANT SUPPORTING EVIDENCE<textarea value={profile.supporting_evidence} onChange={(event) => setProfile({ ...profile, supporting_evidence: event.target.value })} /></label>
              <label>PRINCIPAL RISKS<textarea value={profile.principal_risks} onChange={(event) => setProfile({ ...profile, principal_risks: event.target.value })} /></label>
              <label>THESIS-INVALIDATION CONDITIONS<textarea value={profile.invalidation_conditions} onChange={(event) => setProfile({ ...profile, invalidation_conditions: event.target.value })} /></label>
              <div className="form-grid">
                <label>MAXIMUM PORTFOLIO WEIGHT<input inputMode="decimal" placeholder="0.10 = 10%" value={profile.maximum_weight} onChange={(event) => setProfile({ ...profile, maximum_weight: event.target.value })} /></label>
                <label>LAST REVIEWED<input type="date" value={profile.last_reviewed_date} onChange={(event) => setProfile({ ...profile, last_reviewed_date: event.target.value })} /></label>
                <label>NEXT REVIEW<input type="date" value={profile.next_review_date} onChange={(event) => setProfile({ ...profile, next_review_date: event.target.value })} /></label>
              </div>
              <label>SOURCE LINKS · ONE PER LINE<textarea value={profile.source_links} onChange={(event) => setProfile({ ...profile, source_links: event.target.value })} /></label>
              <div className="form-actions"><button className="action primary" type="submit" disabled={busy}>SAVE THESIS</button></div>
            </form>
          </DataPanel>
          <DataPanel title="Review trigger" meta="REVIEW ONLY · NEVER AN ORDER">
            <form className="editor-form" onSubmit={saveTrigger}>
              <label>TRIGGER CONDITION<select aria-label="Trigger condition" value={triggerType} onChange={(event) => setTriggerType(event.target.value)}>{TRIGGER_TYPES.map((kind) => <option key={kind}>{kind}</option>)}</select></label>
              <div className="form-grid">
                <label>LOWER / BELOW VALUE<input inputMode="decimal" value={lower} onChange={(event) => setLower(event.target.value)} /></label>
                <label>UPPER / ABOVE VALUE<input inputMode="decimal" value={upper} onChange={(event) => setUpper(event.target.value)} /></label>
                <label>REVIEW / EARNINGS DATE<input type="date" value={triggerDate} onChange={(event) => setTriggerDate(event.target.value)} /></label>
                <label>EXPIRY DATE<input type="date" value={triggerExpiry} onChange={(event) => setTriggerExpiry(event.target.value)} /></label>
              </div>
              <label>REASON<textarea value={triggerReason} onChange={(event) => setTriggerReason(event.target.value)} /></label>
              <label>THESIS-RELATED NOTE<textarea value={triggerNote} onChange={(event) => setTriggerNote(event.target.value)} /></label>
              <div className="form-actions"><button className="action primary" type="submit" disabled={busy}>CREATE REVIEW TRIGGER</button></div>
            </form>
            <TriggerDetails entry={selected} />
          </DataPanel>
        </div>
      )}
      <DataPanel title="Decision history" meta="APPEND-ONLY LOCAL RECORDS">
        <div className="table-wrap"><table className="data-table"><thead><tr><th>Holding</th><th>Decision date</th><th>Previous</th><th>New decision</th><th>Reason</th><th>Claude disposition</th><th>Review due</th></tr></thead><tbody>
          {journal?.decision_history.length ? journal.decision_history.map((row) => <tr key={row.id}><td className="symbol">{row.symbol}</td><td>{dateOnly(row.decision_date)}</td><td>{decisionLabel(row.previous_decision)}</td><td>{decisionLabel(row.new_decision)}</td><td>{row.reason || "NO REASON RECORDED"}</td><td>{row.claude_disposition ?? "NOT APPLICABLE"}</td><td>{dateOnly(row.review_due_date)}</td></tr>) : <tr><td colSpan={7} className="unavailable-cell">NO DECISION HISTORY RECORDED</td></tr>}
        </tbody></table></div>
        <SourceTimestamp source="Local append-only decision journal" asOf={journal?.generated_at} status="NO AUTOMATIC BROKERAGE OR CLAUDE ACTION" />
      </DataPanel>
    </>
  );
}

function DecisionRow({ entry, selected, onSelect, onDecision }: { entry: JournalEntry; selected: boolean; onSelect: () => void; onDecision: (instrumentId: string, decision: DecisionName) => void }) {
  return <tr className={selected ? "selected-row" : undefined}><td><button className="symbol-link" type="button" onClick={onSelect}>{entry.holding.canonical_symbol}<small>{entry.holding.security_name}</small></button></td><td>{entry.profile?.portfolio_role ?? "NOT SET"}</td><td className="numeric">{entry.profile?.thesis_strength ? `${entry.profile.thesis_strength} / 5` : "NOT SET"}</td><td><select aria-label={`My decision for ${entry.holding.canonical_symbol}`} value={entry.decision?.decision ?? "WATCH"} onChange={(event) => onDecision(entry.holding.instrument_id, event.target.value as DecisionName)}>{DECISIONS.map((decision) => <option key={decision}>{decision}</option>)}</select></td><td>{entry.latest_ai_review?.suggestion ?? "NOT REVIEWED"}<small>{entry.latest_ai_review ? `Stored separately · ${entry.latest_ai_review.disposition}` : "Manual Claude workflow only"}</small></td><td>{dateOnly(entry.profile?.next_review_date ?? entry.decision?.review_due_date)}</td><td className={entry.active_trigger?.state === "TRIGGERED" ? "warning" : ""}>{entry.active_trigger ? `${entry.active_trigger.trigger_type} · ${entry.active_trigger.state}` : "NONE"}</td></tr>;
}

function TriggerDetails({ entry }: { entry: JournalEntry }) {
  const trigger = entry.active_trigger;
  if (!trigger) return <div className="trigger-details"><strong>NO ACTIVE TRIGGER</strong><p>Price levels are review triggers, never orders. Creating or triggering one never contacts Claude or a brokerage.</p></div>;
  return <div className="trigger-details"><strong>ACTIVE TRIGGER DETAILS</strong><div className="metric-list"><div className="metric-row"><span>Condition</span><strong>{trigger.trigger_type}</strong></div><div className="metric-row"><span>Observed value</span><strong>{trigger.observed_value ?? "NOT OBSERVED"}</strong></div><div className="metric-row"><span>Quote source / timestamp</span><strong>{trigger.quote_source ?? "NOT AVAILABLE"}<small>{timestamp(trigger.quote_timestamp)}</small></strong></div><div className="metric-row"><span>Reason</span><strong>{trigger.reason || "NO REASON RECORDED"}</strong></div><div className="metric-row"><span>Expiry</span><strong>{dateOnly(trigger.expires_at)}</strong></div><div className="metric-row"><span>State</span><strong className={trigger.state === "TRIGGERED" ? "warning" : "positive"}>{trigger.state}</strong></div></div><p>Triggered reviews freeze the current local portfolio and quote evidence. They never contact Claude or a brokerage.</p></div>;
}
