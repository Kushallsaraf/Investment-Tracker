import { type FormEvent, type ReactNode, useEffect, useRef, useState } from "react";
import { addNote, getAnalystFacts, getAnalystStatus, streamAnalyst } from "../api";
import { timestamp } from "../lib/format";
import type { AnalystFacts, AnalystStatus, ChatTurn } from "../types";

// Conversations survive closing the drawer, for the rest of the browser session.
const threads = new Map<string, ChatTurn[]>();

/** Just enough Markdown for model answers: bullets and **bold**. */
function renderAnswer(text: string): ReactNode {
  const blocks: ReactNode[] = [];
  let bullets: string[] = [];
  const inline = (line: string, key: string) =>
    line.split(/(\*\*[^*]+\*\*)/g).map((part, index) =>
      part.startsWith("**") && part.endsWith("**") ? <strong key={`${key}-${index}`}>{part.slice(2, -2)}</strong> : part,
    );
  const flush = () => {
    if (bullets.length) blocks.push(<ul key={`list-${blocks.length}`}>{bullets.map((line, index) => <li key={index}>{inline(line, `b${blocks.length}-${index}`)}</li>)}</ul>);
    bullets = [];
  };
  for (const raw of text.split("\n")) {
    const line = raw.trim();
    const bullet = /^([-*•]|\d+\.)\s+(.*)$/.exec(line);
    if (bullet) {
      bullets.push(bullet[2]);
      continue;
    }
    flush();
    if (line) blocks.push(<p key={`p-${blocks.length}`}>{inline(line.replace(/^#+\s*/, ""), `p${blocks.length}`)}</p>);
  }
  flush();
  return blocks;
}

export function AnalystPanel({ symbol, onNoteSaved }: { symbol: string; onNoteSaved: () => void }) {
  const [status, setStatus] = useState<AnalystStatus | null>(null);
  const [turns, setTurns] = useState<ChatTurn[]>(() => threads.get(symbol) ?? []);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [facts, setFacts] = useState<AnalystFacts | null>(null);
  const [saved, setSaved] = useState<number | null>(null);
  const abort = useRef<AbortController | null>(null);
  const bottom = useRef<HTMLDivElement>(null);

  useEffect(() => {
    getAnalystStatus().then(setStatus).catch((cause) => setError(cause instanceof Error ? cause.message : "AI status unavailable"));
    return () => abort.current?.abort();
  }, []);

  useEffect(() => {
    threads.set(symbol, turns);
    bottom.current?.scrollIntoView?.({ block: "nearest" });
  }, [symbol, turns]);

  async function ask(question: string) {
    const text = question.trim();
    if (!text || busy) return;
    const history: ChatTurn[] = [...turns, { role: "user", content: text }];
    setTurns([...history, { role: "assistant", content: "" }]);
    setDraft("");
    setError(null);
    setBusy(true);
    const controller = new AbortController();
    abort.current = controller;
    try {
      await streamAnalyst(symbol, history, (piece) => {
        setTurns((current) => {
          const next = [...current];
          const last = next[next.length - 1];
          next[next.length - 1] = { ...last, content: last.content + piece };
          return next;
        });
      }, controller.signal);
    } catch (cause) {
      if (controller.signal.aborted) {
        setTurns((current) => {
          const next = [...current];
          const last = next[next.length - 1];
          next[next.length - 1] = { ...last, content: `${last.content}\n\n[Stopped]`.trim() };
          return next;
        });
      } else {
        setError(cause instanceof Error ? cause.message : "The AI analyst could not answer");
        setTurns(history.slice(0, -1));
        setDraft(text);
      }
    } finally {
      setBusy(false);
      abort.current = null;
    }
  }

  async function save(index: number) {
    const answer = turns[index];
    const question = turns[index - 1]?.content ?? "";
    try {
      await addNote(symbol, `AI analyst (${status?.model ?? "local model"}), asked "${question}":\n\n${answer.content}`, null);
      setSaved(index);
      onNoteSaved();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "The note could not be saved");
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    void ask(draft);
  }

  const ready = status?.ready ?? false;
  return (
    <div className="analyst">
      <div className="analyst-status">
        {status ? (
          ready
            ? <span><i className="ok-dot" aria-hidden="true" />{status.model} · {status.local ? "runs on this computer" : status.provider}</span>
            : <span className="warning">Not available · {status.reason}</span>
        ) : <span>Checking the AI model…</span>}
        <button
          type="button"
          className="link-button"
          onClick={() => {
            if (facts) setFacts(null);
            else getAnalystFacts(symbol).then(setFacts).catch((cause) => setError(cause instanceof Error ? cause.message : "Facts unavailable"));
          }}
        >
          {facts ? "Hide what the AI sees" : "What the AI sees"}
        </button>
      </div>

      {facts && (
        <section className="analyst-facts" aria-label="Facts given to the AI">
          {facts.sections.map((section) => (
            <div key={section.title}>
              <strong>{section.title}</strong>
              {section.lines.map((line) => <p key={line}>{line}</p>)}
            </div>
          ))}
          <small>Built {timestamp(facts.generated_at)}. The AI is told to use only these facts.</small>
        </section>
      )}

      {turns.length === 0 && (
        <p className="panel-note" style={{ margin: 0 }}>
          Ask about {symbol} in plain English. Answers explain the numbers this app has already calculated and cite them. The AI never sets prices, targets or signals, and never tells you to buy or sell.
        </p>
      )}

      <div className="analyst-thread" aria-live="polite">
        {turns.map((turn, index) => (
          <div key={`${index}-${turn.role}`} className={`analyst-turn ${turn.role}`}>
            {turn.role === "user" ? (
              <p>{turn.content}</p>
            ) : (
              <>
                <div className="analyst-answer">
                  {turn.content ? renderAnswer(turn.content) : <p className="analyst-wait">Reading the facts… a local model can take 10–20 seconds to start.</p>}
                </div>
                {turn.content && !(busy && index === turns.length - 1) && (
                  <div className="analyst-tools">
                    <button type="button" className="link-button" disabled={saved === index} onClick={() => void save(index)}>
                      {saved === index ? "Saved to notes" : "Save to notes"}
                    </button>
                  </div>
                )}
              </>
            )}
          </div>
        ))}
        <div ref={bottom} />
      </div>

      {error && <div className="status-banner error" role="alert" style={{ margin: 0 }}>{error}</div>}

      <fieldset className="analyst-prompts" aria-label="Suggested questions">
        {status?.quick_prompts.map((prompt) => (
          <button key={prompt.key} type="button" className="analyst-chip" disabled={!ready || busy} onClick={() => void ask(prompt.prompt)}>
            {prompt.label}
          </button>
        ))}
      </fieldset>

      <form className="analyst-form" onSubmit={submit}>
        <textarea
          aria-label={`Ask about ${symbol}`}
          placeholder={`Ask about ${symbol}…`}
          value={draft}
          maxLength={2000}
          disabled={!ready}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              void ask(draft);
            }
          }}
        />
        <div className="drawer-actions">
          {busy
            ? <button type="button" className="action" onClick={() => abort.current?.abort()}>Stop</button>
            : <button type="submit" className="action primary" disabled={!ready || !draft.trim()}>Ask</button>}
          {turns.length > 0 && !busy && <button type="button" className="action" onClick={() => { setTurns([]); setSaved(null); }}>New conversation</button>}
        </div>
      </form>
      <p className="exit-reference" style={{ margin: 0 }}>AI-generated from the facts above. It can be wrong; check the numbers it cites. Not investment advice.</p>
    </div>
  );
}
