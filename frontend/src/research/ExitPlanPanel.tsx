import { type FormEvent, useEffect, useState } from "react";
import { createExitPlan, decideExitPlan } from "../api";
import { dateOnly } from "../lib/format";
import type { ExitPlan } from "../types";

function levels(plan: ExitPlan): Array<[string, string]> {
  return [
    ["Target", plan.target_price ?? "—"],
    ["Stop", plan.stop_price ?? "—"],
    ["Review", plan.review_date ? dateOnly(plan.review_date) : "—"],
  ];
}

function tomorrow(): string {
  const next = new Date();
  next.setDate(next.getDate() + 1);
  return `${next.getFullYear()}-${String(next.getMonth() + 1).padStart(2, "0")}-${String(next.getDate()).padStart(2, "0")}`;
}

export function ExitPlanCard({
  plan,
  busy,
  onDecide,
  showSymbol = false,
  onOpen,
}: {
  plan: ExitPlan;
  busy: boolean;
  onDecide?: (plan: ExitPlan, decision: "accept" | "reject") => void;
  showSymbol?: boolean;
  onOpen?: (symbol: string) => void;
}) {
  const proposed = plan.status === "PROPOSED";
  return (
    <article className={`exit-card ${plan.status.toLowerCase()}`} aria-label={`${plan.symbol} exit plan, ${plan.status.toLowerCase()}`}>
      <header>
        {showSymbol && (onOpen
          ? <button type="button" className="symbol-link" onClick={() => onOpen(plan.symbol)}>{plan.symbol}</button>
          : <strong className="mono">{plan.symbol}</strong>)}
        <span className={`note-chip ${plan.proposed_by === "CLAUDE" ? "claude" : ""}`.trim()}>
          {plan.proposed_by === "CLAUDE" ? "Proposed by Claude" : "My plan"}
        </span>
        <span className="exit-status">{plan.status.toLowerCase()} · {dateOnly(plan.decided_at ?? plan.created_at)}</span>
      </header>
      <dl className="exit-levels">
        {levels(plan).map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}
      </dl>
      <p className="exit-reasoning">{plan.reasoning}</p>
      {plan.reference_price && (
        <small className="exit-reference">Proposed when the close was {plan.reference_price} ({dateOnly(plan.reference_date)})</small>
      )}
      {proposed && onDecide && (
        <div className="drawer-actions">
          <button type="button" className="action primary" disabled={busy} onClick={() => onDecide(plan, "accept")}>Accept</button>
          <button type="button" className="action" disabled={busy} onClick={() => onDecide(plan, "reject")}>Reject</button>
        </div>
      )}
    </article>
  );
}

export function ExitPlanPanel({
  symbol,
  plans,
  onChanged,
}: {
  symbol: string;
  plans: ExitPlan[];
  onChanged: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [writing, setWriting] = useState(false);
  const [target, setTarget] = useState("");
  const [stop, setStop] = useState("");
  const [review, setReview] = useState("");
  const [reasoning, setReasoning] = useState("");

  useEffect(() => {
    setWriting(false);
    setError(null);
  }, [symbol]);

  const proposals = plans.filter((plan) => plan.status === "PROPOSED");
  const active = plans.find((plan) => plan.status === "ACCEPTED") ?? null;
  const past = plans.filter((plan) => plan.status === "REJECTED" || plan.status === "SUPERSEDED");

  async function run(action: () => Promise<unknown>): Promise<boolean> {
    setBusy(true);
    setError(null);
    try {
      await action();
      onChanged();
      return true;
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "The exit plan could not be saved");
      return false;
    } finally {
      setBusy(false);
    }
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!reasoning.trim()) {
      setError("Write down why these levels matter.");
      return;
    }
    const saved = await run(() => createExitPlan(symbol, {
      target_price: target.trim() || null,
      stop_price: stop.trim() || null,
      review_date: review || null,
      reasoning,
    }));
    if (saved) {
      setWriting(false);
      setTarget("");
      setStop("");
      setReview("");
      setReasoning("");
    }
  }

  return (
    <>
      <p className="panel-note" style={{ margin: 0 }}>
        Accepting a plan creates review alerts for the target, stop and review date, and saves the reasoning as a note. It never places an order, and it doesn't change your decision.
      </p>
      {error && <div className="status-banner error" role="alert" style={{ margin: 0 }}>{error}</div>}

      <section className="exit-section" aria-label="Waiting for review">
        <h3>Waiting for review</h3>
        {proposals.length === 0
          ? <p className="exit-empty">No proposals. In Claude Desktop, run "Full stock analysis" and ask Claude to save an exit plan.</p>
          : proposals.map((plan) => <ExitPlanCard key={plan.id} plan={plan} busy={busy} onDecide={(target, decision) => void run(() => decideExitPlan(target.id, decision))} />)}
      </section>

      <section className="exit-section" aria-label="Active plan">
        <h3>Active plan</h3>
        {active ? <ExitPlanCard plan={active} busy={busy} /> : <p className="exit-empty">No accepted plan for {symbol}.</p>}
        {writing ? (
          <form className="exit-form" onSubmit={(event) => void submit(event)}>
            <div className="form-grid">
              <label>Target price<input aria-label="Exit plan target price" inputMode="decimal" value={target} onChange={(event) => setTarget(event.target.value)} /></label>
              <label>Stop price<input aria-label="Exit plan stop price" inputMode="decimal" value={stop} onChange={(event) => setStop(event.target.value)} /></label>
            </div>
            <label>Review date<input aria-label="Exit plan review date" type="date" min={tomorrow()} value={review} onChange={(event) => setReview(event.target.value)} /></label>
            <label>Reasoning<textarea aria-label="Exit plan reasoning" placeholder="Why these levels? What would make you change them?" value={reasoning} maxLength={10_000} onChange={(event) => setReasoning(event.target.value)} /></label>
            <div className="drawer-actions">
              <button type="submit" className="action primary" disabled={busy}>Save my plan</button>
              <button type="button" className="action" onClick={() => setWriting(false)}>Cancel</button>
            </div>
            <small className="exit-reference">Saving makes this the active plan and retires the current one.</small>
          </form>
        ) : (
          <button type="button" className="action" onClick={() => setWriting(true)}>{active ? "Replace with my own plan" : "Write my own plan"}</button>
        )}
      </section>

      {past.length > 0 && (
        <details className="exit-history">
          <summary>History · {past.length}</summary>
          {past.map((plan) => <ExitPlanCard key={plan.id} plan={plan} busy={busy} />)}
        </details>
      )}
      <div className="source-line" style={{ borderTop: 0, padding: 0 }}><span>Saved on this computer</span><span>Levels are checked against the daily close</span></div>
    </>
  );
}
