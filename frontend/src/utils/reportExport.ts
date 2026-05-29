/**
 * Build a self-contained HTML export of an agent report.
 *
 * The export bakes the rendered report DOM (h1..h6, p, table, ul/ol, etc.)
 * into a single HTML document with inlined CSS so it can be opened offline,
 * mailed, or printed without depending on the app's stylesheet bundle.
 *
 * We capture from live DOM (via `reportBodyHtml`) rather than re-running
 * markdown rendering server-side. That avoids adding `marked` / `remark` as
 * runtime deps and guarantees the exported HTML matches what the user just
 * read on screen, including the section ids and custom `markdown-table-wrap`
 * components.
 */

import type { JobLiveContext } from "./livePlanContext";
import { formatLivePrice, isInvalidatedStatus } from "./livePlanContext";

export type StandaloneReportInput = {
  ticker: string;
  rating?: string | null;
  date?: string | null;
  confidencePct?: number | null;
  /** Plain-English rating line (e.g. "Highest conviction bullish view"). */
  ratingPlain?: string | null;
  /** Posture line (e.g. "Open or add a full position when risk limits allow"). */
  ratingPosture?: string | null;
  /** Desk instruction derived from rating tier. */
  actionNow?: string | null;
  /** PM executive summary paragraph. */
  executiveSummary?: string | null;
  /** Entry / target / stop / sizing grid rows. */
  levelRows?: ReadonlyArray<readonly [label: string, value: string]>;
  liveContext?: JobLiveContext | null;
  whyNow: ReadonlyArray<string>;
  invalidation?: string | null;
  /** Outer HTML of the rendered `.dashboard-report-markdown` element. */
  reportBodyHtml: string;
  /** Visual export template for standalone HTML. */
  template?: "classic" | "weekly_report";
  /** ISO timestamp; defaults to `new Date().toISOString()`. */
  generatedAt?: string;
};

const HTML_ESCAPE: Record<string, string> = {
  "&": "&amp;",
  "<": "&lt;",
  ">": "&gt;",
  '"': "&quot;",
  "'": "&#39;",
};

function escapeHtml(s: string): string {
  return s.replace(/[&<>"']/g, (c) => HTML_ESCAPE[c] ?? c);
}

function stripTags(s: string): string {
  return s.replace(/<[^>]*>/g, "").replace(/\s+/g, " ").trim();
}

type ReportSectionLink = { id: string; label: string };

function extractReportSections(reportBodyHtml: string): ReportSectionLink[] {
  const sections: ReportSectionLink[] = [];
  const seen = new Set<string>();
  const re = /<h2\b([^>]*)>([\s\S]*?)<\/h2>/gi;
  let m: RegExpExecArray | null = re.exec(reportBodyHtml);
  while (m) {
    const attrs = m[1] ?? "";
    const text = stripTags(m[2] ?? "");
    const idMatch = /\bid\s*=\s*["']([^"']+)["']/i.exec(attrs);
    const id = (idMatch?.[1] ?? "").trim();
    if (id && text && !seen.has(id)) {
      seen.add(id);
      sections.push({ id, label: text });
    }
    m = re.exec(reportBodyHtml);
  }
  return sections;
}

const EMBEDDED_CSS = `
  :root {
    color-scheme: light;
    --ink: #1f2933;
    --muted: #647585;
    --rule: #d8dee3;
    --accent: #1f6feb;
    --surface: #ffffff;
    --soft: #f6f8fa;
  }
  * { box-sizing: border-box; }
  html, body { background: var(--soft); }
  body {
    margin: 0;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    color: var(--ink);
    line-height: 1.6;
    -webkit-font-smoothing: antialiased;
  }
  main {
    max-width: 56rem;
    margin: 0 auto;
    padding: 32px 24px 64px;
  }
  .hero {
    background: var(--surface);
    border: 1px solid var(--rule);
    border-radius: 12px;
    padding: 24px 28px;
    margin-bottom: 24px;
  }
  .hero .eyebrow {
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--muted);
    font-weight: 600;
    margin: 0 0 10px;
  }
  .hero h1 {
    margin: 0 0 6px;
    font-size: 28px;
    font-weight: 700;
    letter-spacing: -0.01em;
  }
  .hero .meta {
    color: var(--muted);
    font-size: 14px;
    display: flex;
    gap: 18px;
    flex-wrap: wrap;
  }
  .hero .meta strong { color: var(--ink); }
  .filter-strip {
    position: sticky;
    top: 0;
    z-index: 3;
    margin: -8px 0 18px;
    padding: 10px;
    border: 1px solid var(--rule);
    border-radius: 10px;
    background: color-mix(in oklab, var(--surface) 90%, #eef3ff);
    display: flex;
    gap: 8px;
    overflow-x: auto;
    white-space: nowrap;
  }
  .filter-strip a {
    text-decoration: none;
    color: var(--muted);
    font-size: 12px;
    font-weight: 600;
    border: 1px solid var(--rule);
    border-radius: 999px;
    padding: 6px 10px;
    background: var(--surface);
  }
  .filter-strip a:hover { color: var(--ink); border-color: #bfd0ea; }
  dl.decision {
    margin: 0;
    border: 1px solid var(--rule);
    border-radius: 12px;
    overflow: hidden;
    background: var(--surface);
  }
  dl.decision > div {
    display: grid;
    grid-template-columns: 11rem 1fr;
    border-bottom: 1px solid var(--rule);
  }
  dl.decision > div:last-child { border-bottom: 0; }
  dl.decision dt {
    background: var(--soft);
    padding: 12px 16px;
    margin: 0;
    font-size: 13px;
    color: var(--muted);
    font-weight: 500;
  }
  dl.decision dd {
    margin: 0;
    padding: 12px 16px;
    font-weight: 600;
  }
  .decision-brief-plain {
    margin: 8px 0 0;
    font-size: 17px;
    font-weight: 600;
    color: var(--ink);
  }
  .decision-brief-posture {
    margin: 4px 0 0;
    color: var(--muted);
    font-size: 14px;
  }
  .decision-brief-confidence {
    margin: 8px 0 0;
    color: var(--muted);
    font-size: 13px;
  }
  .action-bar {
    display: flex;
    flex-wrap: wrap;
    align-items: baseline;
    gap: 10px 14px;
    margin-top: 16px;
    padding: 12px 16px;
    background: var(--soft);
    border-radius: 8px;
    border: 1px solid var(--rule);
  }
  .action-bar__label {
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--muted);
    font-weight: 600;
  }
  .action-bar__value {
    font-weight: 700;
    font-size: 15px;
  }
  .executive-summary {
    margin: 16px 0 0;
    font-size: 15px;
    line-height: 1.55;
  }
  dl.levels {
    margin: 16px 0 0;
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(9.5rem, 1fr));
    gap: 10px;
  }
  dl.levels > div {
    border: 1px solid var(--rule);
    border-radius: 8px;
    padding: 10px 12px;
    background: var(--surface);
  }
  dl.levels dt {
    margin: 0 0 4px;
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--muted);
    font-weight: 600;
  }
  dl.levels dd {
    margin: 0;
    font-weight: 700;
    font-size: 14px;
    word-break: break-word;
  }
  .live-vs-plan {
    margin-bottom: 16px;
    padding: 14px 16px;
    border-radius: 10px;
    border: 1px solid var(--rule);
    background: var(--soft);
  }
  .live-vs-plan--invalidated {
    border-color: #fca5a5;
    background: #fef2f2;
  }
  .live-vs-plan--caution {
    border-color: #fcd34d;
    background: #fffbeb;
  }
  .live-vs-plan__badge {
    display: inline-block;
    font-size: 11px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-bottom: 8px;
  }
  .live-vs-plan__grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(8rem, 1fr));
    gap: 8px;
    margin: 0 0 10px;
  }
  .live-vs-plan__grid dt {
    margin: 0;
    font-size: 10px;
    text-transform: uppercase;
    color: var(--muted);
  }
  .live-vs-plan__grid dd {
    margin: 0;
    font-weight: 700;
  }
  .live-vs-plan__guidance {
    margin: 0;
    font-size: 14px;
    line-height: 1.5;
  }
  .live-vs-plan__historical {
    margin: 10px 0 0;
    font-size: 12px;
    color: var(--muted);
  }
  section.card {
    background: var(--surface);
    border: 1px solid var(--rule);
    border-radius: 12px;
    padding: 20px 24px;
    margin-top: 20px;
  }
  section.card h2 {
    margin-top: 0;
    font-size: 18px;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 0.06em;
  }
  .report-body h1 { font-size: 24px; margin-top: 0; }
  .report-body h2 {
    font-size: 20px;
    border-left: 4px solid var(--accent);
    padding-left: 12px;
    margin-top: 36px;
  }
  .report-body h3 { font-size: 16px; margin-top: 28px; }
  .report-body h4 { font-size: 14px; margin-top: 22px; color: var(--muted); }
  .report-body p { margin: 0 0 12px; }
  .report-body ul, .report-body ol { padding-left: 1.5em; margin: 0 0 14px; }
  .report-body li + li { margin-top: 4px; }
  .report-body table {
    width: 100%;
    border-collapse: collapse;
    font-size: 13.5px;
    margin: 8px 0 16px;
  }
  .report-body th, .report-body td {
    padding: 8px 12px;
    border: 1px solid var(--rule);
    text-align: left;
    vertical-align: top;
  }
  .report-body th { background: var(--soft); font-weight: 600; }
  .report-body code {
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    background: var(--soft);
    padding: 0.1em 0.35em;
    border-radius: 4px;
    font-size: 0.9em;
  }
  .report-body pre {
    background: var(--soft);
    padding: 14px 16px;
    border-radius: 8px;
    overflow-x: auto;
    font-size: 12.5px;
  }
  .report-body blockquote {
    margin: 0 0 14px;
    padding: 6px 16px;
    border-left: 3px solid var(--rule);
    color: var(--muted);
  }
  .report-body hr { border: 0; border-top: 1px solid var(--rule); margin: 28px 0; }
  footer {
    margin-top: 32px;
    color: var(--muted);
    font-size: 12px;
    text-align: center;
  }
  @media print {
    html, body { background: #fff; }
    main { max-width: none; padding: 0; }
    .hero, dl.decision, section.card { box-shadow: none; }
    section.card, .hero { page-break-inside: avoid; }
    .filter-strip { display: none; }
  }
`;

export function buildStandaloneReportHtml(input: StandaloneReportInput): string {
  const {
    ticker,
    rating,
    date,
    confidencePct,
    ratingPlain,
    ratingPosture,
    actionNow,
    executiveSummary,
    levelRows = [],
    liveContext = null,
    whyNow,
    invalidation,
    reportBodyHtml,
    template = "weekly_report",
    generatedAt = new Date().toISOString(),
  } = input;

  const title = `${ticker} — Agent report`;
  const ratingLine = rating ? escapeHtml(rating) : "—";
  const metaParts: string[] = [`<span><strong>${escapeHtml(ticker)}</strong></span>`];
  if (date) metaParts.push(`<span>As of ${escapeHtml(date)}</span>`);
  metaParts.push(`<span>Exported ${escapeHtml(generatedAt)}</span>`);

  const ratingPlainBlock = ratingPlain
    ? `<p class="decision-brief-plain">${escapeHtml(ratingPlain)}</p>`
    : "";
  const ratingPostureBlock = ratingPosture
    ? `<p class="decision-brief-posture">${escapeHtml(ratingPosture)}</p>`
    : "";
  const confidenceBlock =
    confidencePct != null
      ? `<p class="decision-brief-confidence">Conviction (heuristic): ${confidencePct}% — from rating tier, not model certainty</p>`
      : "";

  const actionBlock =
    actionNow?.trim()
      ? `<div class="action-bar"><span class="action-bar__label">What to do</span><span class="action-bar__value">${escapeHtml(actionNow.trim())}</span></div>`
      : "";

  const summaryBlock = executiveSummary?.trim()
    ? `<p class="executive-summary">${escapeHtml(executiveSummary.trim())}</p>`
    : "";

  const levelsBlock =
    levelRows.length > 0
      ? `<dl class="levels">${levelRows
          .map(
            ([label, value]) =>
              `<div><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(value)}</dd></div>`,
          )
          .join("")}</dl>`
      : "";

  const whyNowList = whyNow.length
    ? `<ul>${whyNow.map((s) => `<li>${escapeHtml(s)}</li>`).join("")}</ul>`
    : "";

  const whyNowBlock = whyNowList
    ? `<section class="card" aria-label="Why now"><h2>Why now</h2>${whyNowList}</section>`
    : "";

  const invalidationBlock = invalidation
    ? `<section class="card"><h2>Invalidation</h2><p>${escapeHtml(invalidation)}</p></section>`
    : "";

  const navSections: ReportSectionLink[] = [
    { id: "decision", label: "Decision" },
    ...(whyNow.length ? [{ id: "why-now", label: "Why now" }] : []),
    ...(invalidation ? [{ id: "invalidation", label: "Invalidation" }] : []),
    { id: "full-report", label: "Full report" },
    ...extractReportSections(reportBodyHtml).slice(0, 8),
  ];
  const filterStrip =
    template === "weekly_report" && navSections.length > 1
      ? `<nav class="filter-strip" aria-label="Quick jump">${navSections
          .map(
            (s) =>
              `<a href="#${escapeHtml(s.id)}">${escapeHtml(s.label)}</a>`,
          )
          .join("")}</nav>`
      : "";

  let liveBlock = "";
  if (liveContext) {
    const { quote, comparison, report_close: reportClose, levels } = liveContext;
    const liveClass = isInvalidatedStatus(comparison.status)
      ? "live-vs-plan live-vs-plan--invalidated"
      : "live-vs-plan";
    const levelBits: string[] = [];
    if (levels.entry != null) {
      levelBits.push(`<div><dt>Planned entry</dt><dd>${levels.entry}</dd></div>`);
    }
    if (levels.stop_loss != null) {
      levelBits.push(`<div><dt>Stop</dt><dd>${levels.stop_loss}</dd></div>`);
    }
    if (levels.price_target != null) {
      levelBits.push(`<div><dt>Target</dt><dd>${levels.price_target}</dd></div>`);
    }
    const reportCloseBlock =
      reportClose != null && date
        ? `<div><dt>Report date close</dt><dd>${reportClose} · ${escapeHtml(date)}</dd></div>`
        : "";
    liveBlock = `<section class="${liveClass}" aria-label="Live price versus report plan">
      <span class="live-vs-plan__badge">${escapeHtml(comparison.status.replace(/_/g, " "))}</span>
      <dl class="live-vs-plan__grid">
        <div><dt>Live now</dt><dd>${escapeHtml(formatLivePrice(quote.price, quote.currency))}</dd></div>
        ${reportCloseBlock}
        ${levelBits.join("")}
      </dl>
      <p class="live-vs-plan__guidance">${escapeHtml(comparison.guidance)}</p>
      ${
        isInvalidatedStatus(comparison.status)
          ? `<p class="live-vs-plan__historical">Historical rating unchanged — this warning reflects current price vs this run&apos;s levels.${
              comparison.suggest_refresh
                ? " Refresh analysis with today&apos;s date before acting."
                : " Analysis already used the live quote at run time; do not use these levels as-is."
            }</p>`
          : ""
      }
    </section>`;
  }

  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>${escapeHtml(title)}</title>
<style>${EMBEDDED_CSS}</style>
</head>
<body>
<main>
  ${filterStrip}
  <header class="hero" id="decision">
    <p class="eyebrow">Agent report — research artifact, not financial advice</p>
    ${liveBlock}
    <h1>${ratingLine}</h1>
    ${ratingPlainBlock}
    ${ratingPostureBlock}
    ${confidenceBlock}
    <div class="meta">${metaParts.join("")}</div>
    ${actionBlock}
    ${summaryBlock}
    ${levelsBlock}
  </header>

  ${
    whyNowBlock
      ? whyNowBlock.replace(
          '<section class="card" aria-label="Why now">',
          '<section class="card" id="why-now" aria-label="Why now">',
        )
      : ""
  }

  ${
    invalidationBlock
      ? invalidationBlock.replace(
          '<section class="card">',
          '<section class="card" id="invalidation">',
        )
      : ""
  }

  <section class="card" id="full-report" aria-label="Full report">
    <h2>Full report</h2>
    <div class="report-body">${reportBodyHtml}</div>
  </section>

  <footer>${escapeHtml(`Generated ${generatedAt} · ${ticker}`)}</footer>
</main>
</body>
</html>`;
}

/** Trigger a browser download of `html` as `filename`. No-op outside a DOM. */
export function downloadStandaloneReport(filename: string, html: string): void {
  if (typeof document === "undefined") return;
  const blob = new Blob([html], { type: "text/html;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/** Trigger a browser download of a PNG data URL. No-op outside a DOM. */
export function downloadPng(filename: string, dataUrl: string): void {
  if (typeof document === "undefined") return;
  const a = document.createElement("a");
  a.href = dataUrl;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
}
