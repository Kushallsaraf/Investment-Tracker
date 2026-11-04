import { type FormEvent, useEffect, useState } from "react";
import { addNote, deleteNote, saveSymbolDecision, updateNote } from "../api";
import { DataPanel } from "../components/ui";
import { dateOnly, decisionLabel, timestamp } from "../lib/format";
import type { DecisionName, Note, ReviewTrigger, SymbolJournal } from "../types";

const DECISIONS: DecisionName[] = ["WATCH", "HOLD", "CONSIDER_ADD", "CONSIDER_REDUCE", "EXIT_CANDIDATE"];
function triggerText(trigger: ReviewTrigger): string {
  switch (trigger.trigger_type) {
    case "PRICE_ABOVE": return `Review above ${trigger.upper_value}`;
    case "PRICE_BELOW": return `Review below ${trigger.lower_value}`;
    case "CONSIDER_ADD_RANGE": return `Consider adding ${trigger.lower_value}–${trigger.upper_value}`;
    case "CONSIDER_REDUCE_RANGE": return `Consider reducing ${trigger.lower_value}–${trigger.upper_value}`;
    case "DATE": return `Review on ${dateOnly(trigger.trigger_date)}`;
    case "AFTER_EARNINGS": return `Review after earnings ${dateOnly(trigger.trigger_date)}`;
    default: return "Thesis note";
  }
}

function isJournal(value: unknown): value is SymbolJournal {
  return typeof value === "object" && value !== null && "notes" in value;
}

function today(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
}

export function NotesPanel({
  symbol,
  journal,
  selectedDate,
  onChanged,
}: {
  symbol: string;
  journal: SymbolJournal | null;
  selectedDate: string | null;
  onChanged: (journal?: SymbolJournal) => void;
}) {
  const [body, setBody] = useState("");
  const [pinnedDate, setPinnedDate] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setBody("");
    setPinnedDate("");
    setError(null);
  }, [symbol]);

  useEffect(() => {
    if (selectedDate) setPinnedDate(selectedDate);
  }, [selectedDate]);

  async function run(action: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      const result = await action();
      onChanged(isJournal(result) ? result : undefined);
      return true;
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "The note could not be saved");
      return false;
    } finally {
      setBusy(false);
    }
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!body.trim()) {
      setError("Write a note first.");
      return;
    }
    const saved = await run(async () => { await addNote(symbol, body, pinnedDate || null); });
    if (saved) {
      setBody("");
      setPinnedDate("");
    }
  }

  const decision = journal?.decision?.decision ?? "WATCH";
  const openTriggers = journal?.triggers ?? [];
  return (
    <DataPanel
      title={`Notes · ${symbol}`}
      className="notes-panel"
      actions={(
        <label className="decision-select">
          <span>My decision</span>
          <select
            aria-label={`My decision for ${symbol}`}
            value={decision}
            disabled={busy || !journal}
            onChange={(event) => void run(() => saveSymbolDecision(symbol, event.target.value as DecisionName, "Updated from Research"))}
          >
            {DECISIONS.map((option) => <option key={option} value={option}>{decisionLabel(option)}</option>)}
          </select>
        </label>
      )}
    >
      <form className="note-form" onSubmit={(event) => void submit(event)}>
        <textarea aria-label={`New note for ${symbol}`} placeholder="What are you watching for, and why?" value={body} maxLength={10_000} onChange={(event) => { setBody(event.target.value); setError(null); }} />
        <div className="note-form-row">
          <label>Pin to date<input aria-label="Pin note to date" type="date" value={pinnedDate} max={today()} onChange={(event) => setPinnedDate(event.target.value)} /></label>
          {pinnedDate && <button className="action" type="button" onClick={() => setPinnedDate("")}>Unpin</button>}
          <button className="action primary" type="submit" disabled={busy}>Add note</button>
        </div>
        <small>Click a candle to pick its date. Pinned notes appear as markers on the chart.</small>
      </form>
      {error && <div className="panel-warning" role="alert">{error}</div>}
      {openTriggers.length > 0 && (
        <ul className="trigger-list">
          {openTriggers.map((trigger) => (
            <li key={trigger.id} className={trigger.state === "TRIGGERED" ? "warning" : ""}>
              {triggerText(trigger)} · {trigger.state}
            </li>
          ))}
        </ul>
      )}
      <ul className="note-list">
        {!journal && <li className="panel-note">Loading notes…</li>}
        {journal?.notes.length === 0 && <li className="panel-note">No notes for {symbol} yet.</li>}
        {journal?.notes.map((note) => <NoteItem key={note.id} note={note} busy={busy} onRun={run} />)}
      </ul>
      <div className="source-line"><span>Saved on this computer</span><span>DECISION {decisionLabel(decision)}{journal?.decision ? ` · ${dateOnly(journal.decision.decision_date)}` : " · DEFAULT"}</span></div>
    </DataPanel>
  );
}

function NoteItem({ note, busy, onRun }: { note: Note; busy: boolean; onRun: (action: () => Promise<unknown>) => Promise<boolean> }) {
  const [editing, setEditing] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [body, setBody] = useState(note.body);
  const [pinned, setPinned] = useState(note.pinned_date ?? "");

  async function save(event: FormEvent) {
    event.preventDefault();
    if (await onRun(async () => { await updateNote(note.id, body, pinned || null); })) setEditing(false);
  }

  if (editing) {
    return (
      <li className="note-item">
        <form className="note-form" onSubmit={(event) => void save(event)}>
          <textarea aria-label="Edit note" value={body} maxLength={10_000} onChange={(event) => setBody(event.target.value)} />
          <div className="note-form-row">
            <label>Pin to date<input aria-label="Edit pinned date" type="date" value={pinned} max={today()} onChange={(event) => setPinned(event.target.value)} /></label>
            <button className="action" type="button" onClick={() => { setEditing(false); setBody(note.body); setPinned(note.pinned_date ?? ""); }}>Cancel</button>
            <button className="action primary" type="submit" disabled={busy}>Save</button>
          </div>
        </form>
      </li>
    );
  }
  return (
    <li className="note-item">
      <div className="note-meta">
        <span title={timestamp(note.created_at)}>{dateOnly(note.created_at)}</span>
        {note.pinned_date && <span className="note-chip">PINNED {dateOnly(note.pinned_date).toUpperCase()}</span>}
        {note.author === "CLAUDE" && <span className="note-chip claude">BY CLAUDE</span>}
        <span className="note-actions">
          <button type="button" className="link-button" onClick={() => setEditing(true)}>Edit</button>
          {confirming ? (
            <>
              <button type="button" className="link-button danger" disabled={busy} onClick={() => void onRun(() => deleteNote(note.id))}>Confirm delete</button>
              <button type="button" className="link-button" onClick={() => setConfirming(false)}>Keep</button>
            </>
          ) : (
            <button type="button" className="link-button" aria-label={`Delete note from ${dateOnly(note.created_at)}`} onClick={() => setConfirming(true)}>Delete</button>
          )}
        </span>
      </div>
      <p>{note.body}</p>
    </li>
  );
}
