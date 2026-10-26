import { type FormEvent, useEffect, useRef, useState } from "react";

const IS_MAC =
  typeof navigator !== "undefined" &&
  /Mac|iPhone|iPad/.test(navigator.platform);

export function CommandBar({
  onSubmit,
}: {
  onSubmit: (symbol: string) => void;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [value, setValue] = useState("");

  useEffect(() => {
    function focus(event: KeyboardEvent) {
      const target = event.target as HTMLElement | null;
      const editing =
        target?.isContentEditable ||
        ["INPUT", "SELECT", "TEXTAREA"].includes(target?.tagName ?? "");
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        input.current?.focus();
        input.current?.select();
      } else if (event.key === "/" && !editing) {
        event.preventDefault();
        input.current?.focus();
      }
    }
    window.addEventListener("keydown", focus);
    return () => window.removeEventListener("keydown", focus);
  }, []);

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!value.trim()) return;
    onSubmit(value);
    setValue("");
    input.current?.blur();
  }

  return (
    <search className="command-search">
      <form className="command-bar" onSubmit={submit}>
        <span aria-hidden="true">›</span>
        <input
          ref={input}
          aria-label="Ticker search"
          placeholder="Ticker, e.g. AAPL or VOO"
          value={value}
          maxLength={12}
          autoComplete="off"
          spellCheck={false}
          onChange={(event) => setValue(event.target.value.toUpperCase())}
          onKeyDown={(event) => {
            if (event.key === "Escape") {
              setValue("");
              input.current?.blur();
            }
          }}
        />
        <kbd>{IS_MAC ? "⌘K" : "Ctrl K"}</kbd>
      </form>
    </search>
  );
}
