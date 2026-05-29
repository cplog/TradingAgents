import { useEffect } from "react";

const BASE = "TradingAgents";

/** Set document.title to `${title} · TradingAgents`, restore on unmount. */
export function useDocumentTitle(title: string | null | undefined): void {
  useEffect(() => {
    const prev = document.title;
    const clean = (title ?? "").trim();
    document.title = clean ? `${clean} · ${BASE}` : BASE;
    return () => {
      document.title = prev;
    };
  }, [title]);
}
