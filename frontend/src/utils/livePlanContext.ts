/** Live quote vs persisted trading-plan levels (mirrors API JobLiveContextResponse). */

export type PlanStatus =
  | "quote_unavailable"
  | "no_levels"
  | "below_stop"
  | "above_target"
  | "below_entry"
  | "in_entry_zone"
  | "above_entry"
  | "neutral";

export type LiveQuoteSnapshot = {
  ticker: string;
  price?: number | null;
  currency?: string | null;
  fetched_at: string;
  source?: string;
  error?: string | null;
};

export type PlanLevelsSnapshot = {
  entry?: number | null;
  stop_loss?: number | null;
  price_target?: number | null;
};

export type PlanComparisonSnapshot = {
  status: PlanStatus;
  guidance: string;
  live_price?: number | null;
  entry?: number | null;
  stop_loss?: number | null;
  price_target?: number | null;
  delta_vs_entry_pct?: number | null;
  delta_vs_stop_pct?: number | null;
  delta_vs_target_pct?: number | null;
  run_time_price?: number | null;
  suggest_refresh?: boolean | null;
};

export type JobLiveContext = {
  quote: LiveQuoteSnapshot;
  report_close?: number | null;
  trade_date?: string | null;
  levels: PlanLevelsSnapshot;
  comparison: PlanComparisonSnapshot;
  run_time_quote?: LiveQuoteSnapshot | null;
  levels_anchored_at_run?: boolean | null;
  historical_rating_note?: string;
};

export function isInvalidatedStatus(status: PlanStatus): boolean {
  return status === "below_stop";
}

export function isCautionStatus(status: PlanStatus): boolean {
  return status === "below_entry" || status === "quote_unavailable" || status === "no_levels";
}

export function formatLivePrice(price: number | null | undefined, currency?: string | null): string {
  if (price == null || !Number.isFinite(price)) return "—";
  const formatted = price.toLocaleString(undefined, { maximumFractionDigits: 2 });
  return currency?.trim() ? `${formatted} ${currency.trim()}` : formatted;
}

export function livePracticalNote(ctx: JobLiveContext | null | undefined): string | null {
  if (!ctx?.comparison?.guidance) return null;
  return ctx.comparison.guidance;
}
