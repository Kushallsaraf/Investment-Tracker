import { type ChangeEvent, type FormEvent, useEffect, useState } from "react";
import { dateOnly } from "../lib/format";
import type { AIReview, ClaudePrompt, JournalPayload, Portfolio, ReviewPack, ReviewPrivacy } from "../types";
import { DataPanel, EmptyState, SourceTimestamp, ViewHeader } from "../components/ui";

const SUGGESTIONS = ["CONSIDER_BUY", "HOLD", "CONSIDER_REDUCE", "CONSIDER_EXIT", "INSUFFICIENT_DATA"];

export function ResearchPage({
  portfolio,
  journal,
  prompts,
  reviews,
  privacy,
  onPrivacy,
  pack,
  busy,
  onPack,
  onReview,
}: {
  portfolio: Portfolio | null;
  journal: JournalPayload | null;
  prompts: ClaudePrompt[];
  reviews: AIReview[];
  privacy: ReviewPrivacy;
  onPrivacy: (privacy: ReviewPrivacy) => void;
  pack: ReviewPack | null;
  busy: boolean;
  onPack: (instrumentId: string, promptId: string, triggerId: string | null, save: boolean) => void;
  onReview: (review: Record<string, unknown>) => void;
}) {
  const [instrumentId, setInstrumentId] = useState("");
  const [promptId, setPromptId] = useState("");
  const [reviewDate, setReviewDate] = useState(new Date().toISOString().slice(0, 10));
  const [evidenceDate, setEvidenceDate] = useState("");
  const [suggestion, setSuggestion] = useState("INSUFFICIENT_DATA");
  const [disposition, setDisposition] = useState("CONSIDERING");
  const [model, setModel] = useState("");
  const [markdown, setMarkdown] = useState("");
  const [explanation, setExplanation] = useState("");
  const [bullCase, setBullCase] = useState("");
  const [bearCase, setBearCase] = useState("");
  const [risks, setRisks] = useState("");
  const [missing, setMissing] = useState("");
  const [conditions, setConditions] = useState("");
  const [links, setLinks] = useState("");

  useEffect(() => {
    if (!instrumentId && portfolio?.holdings[0]) setInstrumentId(portfolio.holdings[0].instrument_id);
    if (!promptId && prompts[0]) setPromptId(prompts[0].id);
  }, [instrumentId, portfolio, promptId, prompts]);

  const activeTrigger = journal?.triggers.find((row) => row.instrument_id === instrumentId && ["ACTIVE", "TRIGGERED"].includes(row.state));

  function uploadMarkdown(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    if (!file.name.toLowerCase().endsWith(".md") && file.type !== "text/markdown" && file.type !== "text/plain") {
      event.target.value = "";
      return;
    }
    void file.text().then(setMarkdown);
  }

  function submitReview(event: FormEvent) {
    event.preventDefault();
    if (!instrumentId || !markdown.trim()) return;
    onReview({
      instrument_id: instrumentId,
      review_date: reviewDate,
      evidence_as_of: evidenceDate || null,
      suggestion,
      disposition,
      claude_model: model || null,
      original_markdown: markdown,
      explanation,
      bull_case: bullCase,
      bear_case: bearCase,
      principal_risks: risks,
      missing_information: missing,
      change_conditions: conditions,
      source_links: links.split("\n").map((line) => line.trim()).filter(Boolean),
    });
  }

  return (
    <>
      <ViewHeader title="Research" subtitle="Prepare structured evidence for manual Claude review · no Claude API connection" asOf={pack?.generated_at} />
      <div className="two-panel-row research-grid">
        <DataPanel title="Claude review pack preview" actions={<button className="action primary" type="button" disabled={!instrumentId || !promptId || busy} onClick={() => onPack(instrumentId, promptId, activeTrigger?.id ?? null, true)}>EXPORT MARKDOWN</button>}>
          <div className="research-controls">
            <label>HOLDING<select aria-label="Research holding" value={instrumentId} onChange={(event) => setInstrumentId(event.target.value)}><option value="">SELECT A HOLDING</option>{portfolio?.holdings.map((row) => <option key={row.instrument_id} value={row.instrument_id}>{row.canonical_symbol} · {row.security_name}</option>)}</select></label>
            <label>REUSABLE LOCAL PROMPT<select aria-label="Reusable Claude prompt" value={promptId} onChange={(event) => setPromptId(event.target.value)}><option value="">SELECT A PROMPT</option>{prompts.map((prompt) => <option key={prompt.id} value={prompt.id}>{prompt.name}</option>)}</select></label>
            <fieldset><legend>PRIVACY</legend>
              <label><input type="checkbox" checked={privacy.weights_only} onChange={(event) => onPrivacy({ ...privacy, weights_only: event.target.checked })} />Weights-only mode</label>
              <label><input type="checkbox" checked={!privacy.include_quantities} disabled={privacy.weights_only} onChange={(event) => onPrivacy({ ...privacy, include_quantities: !event.target.checked })} />Exclude quantities</label>
              <label><input type="checkbox" checked={!privacy.include_dollar_values} disabled={privacy.weights_only} onChange={(event) => onPrivacy({ ...privacy, include_dollar_values: !event.target.checked })} />Exclude dollar values</label>
              <label><input type="checkbox" checked={!privacy.include_account_type} onChange={(event) => onPrivacy({ ...privacy, include_account_type: !event.target.checked })} />Exclude account type</label>
            </fieldset>
            <button className="action" type="button" disabled={!instrumentId || !promptId || busy} onClick={() => onPack(instrumentId, promptId, activeTrigger?.id ?? null, false)}>PREVIEW EXACT MARKDOWN</button>
          </div>
          <section aria-label="Claude review pack Markdown preview"><pre className="markdown-preview">{pack?.markdown ?? "Select a holding and prompt, then preview the exact sanitized Markdown. No information is sent to Claude."}</pre></section>
          <SourceTimestamp source="Local portfolio, decision journal and verified evidence" asOf={pack?.generated_at} status="MANUAL EXPORT ONLY" />
        </DataPanel>
        <DataPanel title="Saved AI reviews" meta="STORED SEPARATELY FROM MY DECISION">
          <div className="review-list">
            {reviews.length ? reviews.map((review) => <article key={review.id}><strong>{review.symbol} · {dateOnly(review.review_date)}</strong><span>{review.suggestion} · {review.disposition}</span><small>{review.claude_model || "MODEL NOT RECORDED"} · evidence {dateOnly(review.evidence_as_of)}</small></article>) : <EmptyState title="NO AI REVIEWS">Paste or upload a manual Claude response below.</EmptyState>}
          </div>
          <form className="editor-form ai-import" onSubmit={submitReview}>
            <div className="form-grid">
              <label>REVIEW DATE<input type="date" value={reviewDate} onChange={(event) => setReviewDate(event.target.value)} required /></label>
              <label>EVIDENCE AS-OF<input type="date" value={evidenceDate} onChange={(event) => setEvidenceDate(event.target.value)} /></label>
              <label>SUGGESTED ACTION<select aria-label="Claude suggested action" value={suggestion} onChange={(event) => setSuggestion(event.target.value)}>{SUGGESTIONS.map((value) => <option key={value}>{value}</option>)}</select></label>
              <label>MY RESPONSE<select aria-label="Claude suggestion disposition" value={disposition} onChange={(event) => setDisposition(event.target.value)}><option>CONSIDERING</option><option>ACCEPTED</option><option>REJECTED</option></select></label>
              <label>CLAUDE MODEL<input value={model} placeholder="Optional" onChange={(event) => setModel(event.target.value)} /></label>
              <label>UPLOAD MARKDOWN<input aria-label="Upload Claude Markdown response" type="file" accept=".md,text/markdown,text/plain" onChange={uploadMarkdown} /></label>
            </div>
            <label>ORIGINAL MARKDOWN<textarea className="large" required value={markdown} onChange={(event) => setMarkdown(event.target.value)} /></label>
            <label>EXPLANATION<textarea value={explanation} onChange={(event) => setExplanation(event.target.value)} /></label>
            <div className="form-grid"><label>BULL CASE<textarea value={bullCase} onChange={(event) => setBullCase(event.target.value)} /></label><label>BEAR CASE<textarea value={bearCase} onChange={(event) => setBearCase(event.target.value)} /></label></div>
            <label>PRINCIPAL RISKS<textarea value={risks} onChange={(event) => setRisks(event.target.value)} /></label>
            <label>MISSING INFORMATION<textarea value={missing} onChange={(event) => setMissing(event.target.value)} /></label>
            <label>CONDITIONS THAT WOULD CHANGE THE SUGGESTION<textarea value={conditions} onChange={(event) => setConditions(event.target.value)} /></label>
            <label>SOURCE LINKS · ONE PER LINE<textarea value={links} onChange={(event) => setLinks(event.target.value)} /></label>
            <p className="form-note">Free-form text is not interpreted as a binding action. Review the structured fields yourself before saving.</p>
            <div className="form-actions"><button className="action primary" type="submit" disabled={!instrumentId || !markdown.trim() || busy}>SAVE AI REVIEW</button></div>
          </form>
          <SourceTimestamp source="Manual Claude response import" asOf={reviews[0]?.created_at} status="NON-BINDING RESEARCH" />
        </DataPanel>
      </div>
    </>
  );
}
