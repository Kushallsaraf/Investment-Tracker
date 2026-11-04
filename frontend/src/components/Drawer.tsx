import { type PropsWithChildren, useEffect, useId, useRef } from "react";

/** Right-side panel for detail that would otherwise crowd the page. Escape or the backdrop closes it. */
export function Drawer({
  open,
  eyebrow,
  title,
  subtitle,
  wide = false,
  onClose,
  children,
}: PropsWithChildren<{
  open: boolean;
  eyebrow?: string;
  title: string;
  subtitle?: string;
  wide?: boolean;
  onClose: () => void;
}>) {
  const titleId = useId();
  const closeButton = useRef<HTMLButtonElement>(null);
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  useEffect(() => {
    if (!open) return;
    const returnTo = document.activeElement as HTMLElement | null;
    closeButton.current?.focus();
    function onKey(event: KeyboardEvent) {
      // A confirmation dialog on top of the drawer handles its own Escape.
      if (event.key === "Escape" && !document.querySelector(".dialog-backdrop")) onCloseRef.current();
    }
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      returnTo?.focus?.();
    };
  }, [open]);

  if (!open) return null;
  return (
    <div className="drawer-layer">
      <button type="button" className="drawer-scrim" aria-label="Close panel" tabIndex={-1} onClick={onClose} />
      <div className={`drawer ${wide ? "wide" : ""}`.trim()} role="dialog" aria-modal="true" aria-labelledby={titleId}>
        <div className="drawer-head">
          <div>
            {eyebrow && <span className="drawer-eyebrow">{eyebrow}</span>}
            <h2 id={titleId}>{title}</h2>
            {subtitle && <p>{subtitle}</p>}
          </div>
          <button ref={closeButton} type="button" className="drawer-close" aria-label="Close" onClick={onClose}>×</button>
        </div>
        <div className="drawer-body">{children}</div>
      </div>
    </div>
  );
}
