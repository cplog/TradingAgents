/** Central path builders — use everywhere instead of string templates. */

export function dashboardPath(opts?: { ticker?: string }): string {
  if (!opts?.ticker?.trim()) return "/dashboard";
  return `/dashboard?ticker=${encodeURIComponent(opts.ticker.trim())}`;
}

export function runsPath(jobId: string): string {
  return `/runs/${encodeURIComponent(jobId.trim())}`;
}

export function stocksPath(ticker: string): string {
  return `/stocks/${encodeURIComponent(ticker.trim().toUpperCase())}`;
}

export const paths = {
  dashboard: "/dashboard",
  history: "/history",
  historyStats: "/history/stats",
  batch: "/batch",
  screener: "/screener",
  sectors: "/sectors",
  news: "/news",
  watchlists: "/watchlists",
  system: "/system",
  admin: "/admin",
} as const;

/** True when pathname is under the runs workflow (index, detail, or stock drill-down). */
export function isRunsWorkflowPath(pathname: string): boolean {
  return (
    pathname === paths.history ||
    pathname.startsWith("/runs/") ||
    pathname.startsWith("/stocks/")
  );
}
