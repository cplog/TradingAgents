import { useEffect, useRef, useState } from "react";
import { getDimensionsByTicker } from "../api";
import type { StockDimensions } from "../dimensions-types";
import type { HistoryTableRow } from "../utils/historyDisplay";

const FACTOR_KEYS = [
  "value",
  "growth",
  "quality",
  "momentum",
  "low_risk",
  "sentiment",
] as const;

const MAX_TICKERS = 24;
const MAX_CONCURRENT = 2;
const START_DELAY_MS = 400;

function rowNeedsPreview(row: HistoryTableRow): boolean {
  if (!row.ticker) return false;
  return !FACTOR_KEYS.some((k) => {
    const v = row.factor_scores?.[k];
    return typeof v === "number" && Number.isFinite(v);
  });
}

/**
 * Lazy, throttled factor previews for the history table.
 * Defers work after paint and caps concurrent /api/dimensions calls.
 */
export function useThumbDimensions(
  rows: HistoryTableRow[],
  enabled: boolean,
): Record<string, StockDimensions | null | undefined> {
  const [thumbDims, setThumbDims] = useState<
    Record<string, StockDimensions | null | undefined>
  >({});
  const queuedRef = useRef<string[]>([]);
  const scheduledRef = useRef<Set<string>>(new Set());
  const inFlightRef = useRef(0);
  const cancelledRef = useRef(false);

  useEffect(() => {
    if (!enabled || !rows.length) return;

    cancelledRef.current = false;
    const seen = new Set<string>();
    const tickers: string[] = [];
    for (const row of rows) {
      if (!rowNeedsPreview(row)) continue;
      const t = row.ticker!.trim().toUpperCase();
      if (!t || seen.has(t) || scheduledRef.current.has(t)) continue;
      seen.add(t);
      tickers.push(t);
      if (tickers.length >= MAX_TICKERS) break;
    }
    if (!tickers.length) return;

    queuedRef.current = tickers;

    function pump(): void {
      if (cancelledRef.current) return;
      while (inFlightRef.current < MAX_CONCURRENT && queuedRef.current.length > 0) {
        const ticker = queuedRef.current.shift()!;
        inFlightRef.current += 1;
        void getDimensionsByTicker(ticker)
          .then((d) => {
            if (cancelledRef.current) return;
            setThumbDims((prev) => ({ ...prev, [ticker]: d }));
          })
          .catch(() => {
            if (cancelledRef.current) return;
            setThumbDims((prev) => ({ ...prev, [ticker]: null }));
          })
          .finally(() => {
            inFlightRef.current -= 1;
            if (!cancelledRef.current) pump();
          });
      }
    }

    const delayId = window.setTimeout(() => {
      for (const t of tickers) scheduledRef.current.add(t);
      pump();
    }, START_DELAY_MS);

    return () => {
      cancelledRef.current = true;
      window.clearTimeout(delayId);
      queuedRef.current = [];
    };
  }, [rows, enabled]);

  return thumbDims;
}
