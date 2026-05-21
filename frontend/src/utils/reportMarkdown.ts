/** Helpers for History / run-detail report rendering. */

export const REPORT_SECTION_LABELS: Record<string, string> = {
  market: "Market",
  social: "Social / sentiment",
  news: "News / macro",
  fundamentals: "Fundamentals",
  hot_money: "Hot money",
  policy: "Policy",
  lockup: "Lockup",
  kronos: "Kronos forecast",
  research_plan: "Research plan",
  trader_plan: "Trader proposal",
  portfolio_decision: "Portfolio decision",
};

const REPORT_KEYS_ORDER = [
  "market",
  "social",
  "news",
  "fundamentals",
  "hot_money",
  "policy",
  "lockup",
  "kronos",
  "research_plan",
  "trader_plan",
  "portfolio_decision",
] as const;

/** Ordered section keys that exist and are non-empty; unknown keys last, sorted. */
export function orderedReportSectionKeys(reports: Record<string, string> | undefined): string[] {
  if (!reports || typeof reports !== "object") return [];
  const present = Object.entries(reports)
    .filter(([, v]) => typeof v === "string" && v.trim().length > 0)
    .map(([k]) => k);
  const ordered = REPORT_KEYS_ORDER.filter((k) => present.includes(k));
  const rest = present.filter((k) => !ordered.includes(k)).sort();
  return [...ordered, ...rest];
}

/**
 * Collapse consecutive duplicate paragraphs (split on blank lines).
 * Reduces LLM output that repeats the same markdown table or block.
 */
export function collapseConsecutiveDuplicateBlocks(text: string, minLen = 160): string {
  if (!text.trim()) return text;
  const parts = text.split(/\n{2,}/);
  const kept: string[] = [];
  for (const part of parts) {
    const t = part.trim();
    if (!t) continue;
    const lastTrim = kept.length ? kept[kept.length - 1].trim() : "";
    if (t.length >= minLen && t === lastTrim) continue;
    kept.push(part);
  }
  return kept.join("\n\n");
}

export function prepareReportMarkdown(sectionKey: string, raw: string): string {
  let body = raw.trim();
  if (!body) return "";
  if (sectionKey === "news") {
    body = collapseConsecutiveDuplicateBlocks(body, 180);
  }
  // Agent reports usually open with their own heading; avoid duplicating "Market" etc.
  if (/^#{1,3}\s+\S/m.test(body)) {
    return body;
  }
  const title = REPORT_SECTION_LABELS[sectionKey] ?? sectionKey.replace(/_/g, " ");
  return `## ${title}\n\n${body}`;
}
