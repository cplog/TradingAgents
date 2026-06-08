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

const UNICODE_SPACE_RE = /[\u00a0\u202f\u2009\u2007]/g;
const FINAL_PROPOSAL_START_RE =
  /^\*\*FINAL TRANSACTION PROPOSAL:\s*[^*]+\*\*\s*(?:\r?\n+|---\s*\r?\n+)?/i;
const INTERNAL_FIELD_RE = /\n*_Internal report field:[^\n]*\n*/gi;

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

/** Normalize LLM unicode spaces and trailing hard-break markers for stable GFM parsing. */
export function normalizeReportWhitespace(text: string): string {
  return text
    .replace(UNICODE_SPACE_RE, " ")
    .replace(/[ \t]+\r?\n/g, "\n")
    .replace(/\r\n/g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

/** Analyst nodes sometimes prepend a final proposal line; strip from non-decision sections. */
export function stripLeadingFinalTransactionProposal(text: string): string {
  return text.replace(FINAL_PROPOSAL_START_RE, "").trim();
}

export function stripInternalReportFields(text: string): string {
  return text.replace(INTERNAL_FIELD_RE, "\n").trim();
}

/** True when a section is only a stub (e.g. failed Kronos). */
export function isSectionPlaceholder(sectionKey: string, raw: string): boolean {
  const t = normalizeReportWhitespace(raw);
  if (!t) return true;
  if (sectionKey === "kronos") {
    return /^(\*\*Status:\*\*\s*empty|_Kronos forecast skipped)/i.test(t);
  }
  return false;
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

/** Clean section body before markdown render (no section title injection). */
export function sanitizeReportSectionBody(sectionKey: string, raw: string): string {
  let body = normalizeReportWhitespace(raw);
  if (!body) return "";
  if (sectionKey !== "trader_plan" && sectionKey !== "portfolio_decision") {
    body = stripLeadingFinalTransactionProposal(body);
  }
  body = stripInternalReportFields(body);
  if (sectionKey === "news") {
    body = collapseConsecutiveDuplicateBlocks(body, 180);
  }
  return body.trim();
}

export function prepareReportMarkdown(sectionKey: string, raw: string): string {
  const body = sanitizeReportSectionBody(sectionKey, raw);
  if (!body) return "";
  if (/^#{1,3}\s+\S/m.test(body)) {
    return body;
  }
  const title = REPORT_SECTION_LABELS[sectionKey] ?? sectionKey.replace(/_/g, " ");
  return `## ${title}\n\n${body}`;
}

export function reportSectionDomId(sectionKey: string): string {
  return `report-section-${sectionKey}`;
}

export type SanitizedReportMarkdownMeta = {
  ticker?: string;
  date?: string | null;
  rating?: string | null;
};

/** Build markdown matching what the UI renders (sanitized, ordered, stubs omitted). */
export function buildSanitizedReportMarkdown(
  reports: Record<string, string> | undefined,
  meta?: SanitizedReportMarkdownMeta,
): string {
  const keys = orderedReportSectionKeys(reports);
  const parts: string[] = [];

  if (meta?.ticker?.trim()) {
    parts.push(`# ${meta.ticker.trim()} agent report`);
    if (meta.date?.trim()) parts.push(`As of ${meta.date.trim()}`);
    if (meta.rating?.trim()) parts.push(`**Rating:** ${meta.rating.trim()}`);
    parts.push("");
  }

  for (const key of keys) {
    const raw = reports?.[key] ?? "";
    if (isSectionPlaceholder(key, raw)) continue;
    const section = prepareReportMarkdown(key, raw);
    if (section) parts.push(section, "");
  }

  return parts.join("\n").trimEnd() + (parts.length ? "\n" : "");
}
