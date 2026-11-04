import { dateOnly } from "../lib/format";
import { ExitPlanCard } from "../research/ExitPlanPanel";
import type { ExitPlan, JournalPayload } from "../types";

/** Triggered alerts and exit-plan proposals waiting for the investor, shown above the decision journal. */
export function ReviewQueue({
  alerts,
  proposals,
  busy,
  onDecide,
  onOpen,
}: {
  alerts: JournalPayload["alerts"];
  proposals: ExitPlan[];
  busy: boolean;
  onDecide: (plan: ExitPlan, decision: "accept" | "reject") => void;
  onOpen: (symbol: string) => void;
}) {
  return (
    <section className="review-queue" aria-label="Review queue">
      <h3>Alerts · {alerts.length}</h3>
      {alerts.length === 0 && <p className="exit-empty">No review triggers are due.</p>}
      {alerts.map((alert) => (
        <article className="alert-item" key={alert.id}>
          <strong>{alert.message}</strong>
          {alert.exit_plan_reasoning && <p>Original reasoning: {alert.exit_plan_reasoning}</p>}
          <small>{alert.symbol} · {dateOnly(alert.created_at)}</small>
        </article>
      ))}
      <h3>Exit plans waiting for review · {proposals.length}</h3>
      {proposals.length === 0 && <p className="exit-empty">No proposals from Claude.</p>}
      {proposals.map((plan) => <ExitPlanCard key={plan.id} plan={plan} busy={busy} showSymbol onOpen={onOpen} onDecide={onDecide} />)}
    </section>
  );
}
