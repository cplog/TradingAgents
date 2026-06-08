/**
 * Build a self-contained HTML export of an agent report.
 *
 * Captures rendered report DOM plus structured metadata (dimensions, provenance,
 * analyst coverage) so the export stays complete as the product adds features.
 */

import type { JobResultPayload, RunProvenance } from "../api";
import type { DimensionsCommentary, StockDimensions } from "../dimensions-types";
import type { JobLiveContext } from "./livePlanContext";
import {
  escapeExportHtml,
  extractReportSectionsFromHtml,
  type ReportSectionLink,
  renderAnalystCoverageHtml,
  renderDecisionBriefHtml,
  renderDimensionsHtml,
  renderProvenanceHtml,
  type ConfidenceExportBlock,
} from "./reportExportBlocks";
import { EXPORT_TOKENS, exportCssRoot } from "../theme/exportTokens";

export type StandaloneReportInput = {
  ticker: string;
  rating?: string | null;
  date?: string | null;
  confidencePct?: number | null;
  ratingPlain?: string | null;
  ratingPosture?: string | null;
  actionNow?: string | null;
  executiveSummary?: string | null;
  livePracticalNote?: string | null;
  levelRows?: ReadonlyArray<readonly [label: string, value: string]>;
  liveContext?: JobLiveContext | null;
  whyNow: ReadonlyArray<string>;
  invalidation?: string | null;
  /** Outer HTML of the rendered `.dashboard-report-markdown` element. */
  reportBodyHtml: string;
  /** Optional visual evidence block (OHLCV / Kronos SVGs). */
  supplementaryHtml?: string;
  /** Explicit section list for navigation (preferred over DOM scrape). */
  reportSections?: ReportSectionLink[];
  provenance?: RunProvenance | null;
  dimensions?: StockDimensions | null;
  dimensionsCommentary?: DimensionsCommentary | null;
  analystCoverage?: JobResultPayload["analyst_coverage"];
  confidenceDetail?: ConfidenceExportBlock | null;
  template?: "classic" | "weekly_report";
  generatedAt?: string;
};

/** Strip inline styles that reference app CSS variables (invalid in standalone HTML). */
function normalizeReportBodyHtml(html: string): string {
  return html.replace(/\sstyle="([^"]*)"/gi, (_match, style: string) =>
    /var\s*\(/.test(style) ? "" : _match,
  );
}

const EMBEDDED_CSS = `
  ${exportCssRoot()}
  *, *::before, *::after { box-sizing: border-box; }
  html { scroll-behavior: smooth; }
  html, body {
    width: 100%;
    margin: 0;
    background: var(--soft);
  }
  body {
    font-family: "Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    background:
      radial-gradient(circle at 18% 10%, rgba(244, 184, 136, 0.12), transparent 28rem),
      radial-gradient(circle at 82% 4%, rgba(123, 164, 127, 0.06), transparent 24rem),
      var(--soft);
    font-size: 16px;
    color: var(--ink);
    line-height: 1.65;
    -webkit-font-smoothing: antialiased;
    text-rendering: optimizeLegibility;
  }
  .export-page {
    width: 100%;
    max-width: var(--content-max);
    margin: 0 auto;
    padding: 24px var(--page-pad) 72px;
  }
  .export-toc {
    position: sticky;
    top: 0;
    z-index: 5;
    margin: 0 0 20px;
    padding: 12px 14px;
    background: var(--surface);
    border: 1px solid var(--rule);
    border-radius: 12px;
  }
  .export-toc__label {
    margin: 0 0 10px;
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--muted);
    font-weight: 700;
  }
  .export-toc__links {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin: 0;
    padding: 0;
    list-style: none;
  }
  .export-toc__links a {
    display: inline-block;
    text-decoration: none;
    color: var(--muted);
    font-size: 12px;
    font-weight: 600;
    border: 1px solid var(--rule);
    border-radius: 999px;
    padding: 6px 12px;
    background: var(--surface);
    line-height: 1.3;
    white-space: nowrap;
  }
  .export-toc__links a:hover {
    color: var(--ink);
    border-color: ${EXPORT_TOKENS.phosphorBorder};
    background: ${EXPORT_TOKENS.phosphorGlow};
  }
  .decision-brief,
  section.card,
  .report-stack {
    width: 100%;
  }
  .decision-brief {
    display: grid;
    gap: 16px;
    background: var(--surface);
    border: 1px solid var(--rule);
    border-radius: 14px;
    padding: clamp(18px, 3vw, 28px);
    margin-bottom: 20px;
  }
  .decision-brief__eyebrow {
    margin: 0;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--muted);
    font-weight: 600;
  }
  .decision-brief__head {
    display: grid;
    grid-template-columns: auto minmax(0, 1fr);
    gap: 16px;
    align-items: start;
  }
  .decision-brief__rating {
    font-size: clamp(1.75rem, 4vw, 2.25rem);
    font-weight: 700;
    letter-spacing: -0.03em;
    line-height: 1.1;
    padding: 8px 12px;
    border-radius: 8px;
    border: 1px solid var(--rule);
    background: var(--soft);
  }
  .decision-brief__rating--positive {
    color: var(--accent);
    border-color: ${EXPORT_TOKENS.phosphorBorder};
    background: ${EXPORT_TOKENS.phosphorGlow};
  }
  .decision-brief__rating--negative {
    color: var(--fail);
    border-color: ${EXPORT_TOKENS.dangerBorder};
    background: ${EXPORT_TOKENS.dangerSurface};
  }
  .decision-brief__rating--neutral { color: var(--ink); }
  .decision-brief__head-copy { display: grid; gap: 4px; min-width: 0; }
  .decision-brief__plain {
    margin: 0;
    font-size: 17px;
    font-weight: 600;
  }
  .decision-brief__posture {
    margin: 0;
    font-size: 14px;
    color: var(--muted);
    line-height: 1.45;
  }
  .decision-brief__historical-rating {
    margin: 0;
    font-size: 12px;
    color: var(--muted);
    font-weight: 600;
  }
  .decision-brief__confidence {
    margin: 4px 0 0;
    font-size: 13px;
    color: var(--muted);
  }
  .decision-brief__confidence strong { color: var(--ink); }
  .decision-brief__confidence--strong strong { color: var(--ok); }
  .decision-brief__confidence--balanced strong { color: var(--warn); }
  .decision-brief__confidence--weak strong { color: var(--fail); }
  .decision-brief__confidence-raw { opacity: 0.7; }
  .decision-brief__inputs {
    display: grid;
    gap: 8px;
    padding: 12px;
    border: 1px solid var(--rule);
    border-radius: 8px;
    background: var(--soft);
  }
  .decision-brief__input-row {
    display: grid;
    grid-template-columns: minmax(140px, 0.25fr) 1fr;
    gap: 12px;
    align-items: baseline;
    font-size: 13px;
  }
  .decision-brief__input-label {
    font-weight: 600;
    letter-spacing: 0.02em;
    text-transform: uppercase;
    font-size: 11px;
    color: var(--muted);
  }
  .decision-brief__input-row ul {
    margin: 0;
    padding: 0;
    list-style: none;
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }
  .decision-brief__input-row li {
    padding: 2px 8px;
    border-radius: 6px;
    border: 1px solid var(--rule);
    background: var(--surface);
  }
  .decision-brief__input-row--good li { border-color: ${EXPORT_TOKENS.sageBorder}; color: var(--ok); }
  .decision-brief__input-row--warn li { border-color: ${EXPORT_TOKENS.warnBorder}; color: var(--warn); }
  .decision-brief__input-row--flag li { border-color: ${EXPORT_TOKENS.dangerBorder}; color: var(--fail); }
  .decision-brief__action {
    display: flex;
    flex-wrap: wrap;
    align-items: baseline;
    gap: 8px;
    padding: 12px 16px;
    border-radius: 8px;
    background: var(--soft);
    border: 1px solid var(--rule);
  }
  .decision-brief__action-label {
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--muted);
  }
  .decision-brief__action-value {
    font-size: 15px;
    font-weight: 650;
  }
  .decision-brief__live-note {
    padding: 10px 12px;
    border-radius: 8px;
    border: 1px solid var(--rule);
    background: var(--soft);
    font-size: 14px;
  }
  .decision-brief__live-note--warn {
    border-color: ${EXPORT_TOKENS.dangerBorder};
    background: ${EXPORT_TOKENS.dangerSurface};
  }
  .decision-brief__live-note-label {
    display: block;
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--muted);
    margin-bottom: 4px;
  }
  .decision-brief__live-note p { margin: 0; }
  .decision-brief__summary {
    margin: 0;
    font-size: 15px;
    line-height: 1.6;
    max-width: 72ch;
  }
  .decision-brief__levels {
    margin: 0;
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(min(100%, 11rem), 1fr));
    gap: 8px;
  }
  .decision-brief__level {
    display: grid;
    gap: 4px;
    padding: 8px 12px;
    border-radius: 8px;
    border: 1px solid var(--rule);
    background: var(--soft);
  }
  .decision-brief__level dt {
    margin: 0;
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    color: var(--muted);
  }
  .decision-brief__level dd {
    margin: 0;
    font-size: 15px;
    font-weight: 600;
    word-break: break-word;
  }
  .decision-brief__meta {
    color: var(--muted);
    font-size: 14px;
    display: flex;
    gap: 14px 18px;
    flex-wrap: wrap;
  }
  .decision-brief__meta strong { color: var(--ink); }
  .mono { font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; }
  .feature-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(min(100%, 17rem), 1fr));
    gap: 16px;
    margin-bottom: 16px;
  }
  .feature-grid .card--meta { margin: 0; }
  .live-vs-plan {
    margin: 0;
    padding: 14px 16px;
    border-radius: 10px;
    border: 1px solid var(--rule);
    background: var(--soft);
  }
  .live-vs-plan--invalidated {
    border-color: ${EXPORT_TOKENS.dangerBorder};
    background: ${EXPORT_TOKENS.dangerSurface};
  }
  .live-vs-plan--caution {
    border-color: ${EXPORT_TOKENS.warnBorder};
    background: ${EXPORT_TOKENS.warnSurface};
  }
  .live-vs-plan--ok {
    border-color: ${EXPORT_TOKENS.sageBorder};
    background: rgba(123, 164, 127, 0.1);
  }
  .live-vs-plan--neutral { border-color: var(--rule); background: var(--soft); }
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
  .live-vs-plan__grid dd { margin: 0; font-weight: 700; }
  .live-vs-plan__guidance { margin: 0; font-size: 14px; }
  .live-vs-plan__historical {
    margin: 10px 0 0;
    font-size: 12px;
    color: var(--muted);
  }
  section.card {
    background: var(--surface);
    border: 1px solid var(--rule);
    border-radius: 12px;
    padding: 18px 22px;
    margin-bottom: 16px;
  }
  section.card h2 {
    margin: 0 0 12px;
    font-size: 13px;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 0.06em;
    font-weight: 700;
  }
  section.card h3 {
    margin: 12px 0 6px;
    font-size: 13px;
    color: var(--ink);
  }
  .muted { color: var(--muted); font-size: 14px; }
  dl.meta-grid {
    margin: 0;
    display: grid;
    gap: 10px;
  }
  @media (min-width: 520px) {
    dl.meta-grid { grid-template-columns: 1fr 1fr; }
  }
  dl.meta-grid dt {
    margin: 0;
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--muted);
    font-weight: 600;
  }
  dl.meta-grid dd { margin: 2px 0 0; font-size: 14px; font-weight: 600; }
  ul.warn-list {
    margin: 12px 0 0;
    padding-left: 1.2em;
    color: var(--warn);
    font-size: 13px;
  }
  .table-scroll { overflow-x: auto; -webkit-overflow-scrolling: touch; }
  table.data-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
    min-width: 28rem;
  }
  table.data-table th, table.data-table td {
    padding: 8px 10px;
    border: 1px solid var(--rule);
    text-align: left;
    vertical-align: top;
  }
  table.data-table th { background: var(--soft); font-weight: 600; }
  .badge {
    display: inline-block;
    font-size: 11px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    padding: 2px 8px;
    border-radius: 999px;
    background: var(--soft);
  }
  .badge--ok { color: var(--ok); }
  .badge--failed { color: var(--fail); }
  .badge--empty { color: var(--muted); }
  .factor-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(6.5rem, 1fr));
    gap: 8px;
    margin: 12px 0;
  }
  .factor-chip {
    border: 1px solid var(--rule);
    border-radius: 8px;
    padding: 8px 10px;
    text-align: center;
    background: var(--soft);
  }
  .factor-chip__label {
    display: block;
    font-size: 10px;
    text-transform: uppercase;
    color: var(--muted);
    letter-spacing: 0.04em;
  }
  .factor-chip__score {
    display: block;
    font-size: 18px;
    font-weight: 700;
    margin-top: 2px;
  }
  .dimensions-commentary {
    margin-top: 12px;
    padding-top: 12px;
    border-top: 1px solid var(--rule);
    font-size: 14px;
  }
  .confidence-cols {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(12rem, 1fr));
    gap: 12px;
    margin-top: 10px;
  }
  .confidence-cols ul { margin: 4px 0 0; padding-left: 1.2em; font-size: 13px; }
  .supplementary {
    width: 100%;
    margin-bottom: 16px;
  }
  .supplementary svg { display: block; width: 100%; max-width: 100%; height: auto; }
  .supplementary .evidence-placeholders__grid {
    width: 100%;
    grid-template-columns: repeat(auto-fit, minmax(min(100%, 280px), 1fr));
  }
  .evidence-placeholders__grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(min(100%, 16rem), 1fr));
    gap: 12px;
  }
  .evidence-placeholders__card {
    border: 1px solid var(--rule);
    border-radius: 10px;
    padding: 12px 14px;
    background: var(--soft);
  }
  .evidence-placeholders__title {
    margin: 0 0 8px;
    font-size: 13px;
    font-weight: 700;
  }
  .report-stack {
    width: 100%;
    background: var(--surface);
    border: 1px solid var(--rule);
    border-radius: 14px;
    padding: 20px clamp(16px, 3vw, 28px) 28px;
  }
  .report-stack > h2 {
    margin: 0 0 16px;
    font-size: 13px;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 0.06em;
  }
  .report-body,
  .report-body .markdown-body,
  .report-body .dashboard-report-markdown {
    width: 100%;
    max-width: none;
    display: block;
  }
  .report-body .report-section {
    width: 100%;
    padding: 24px 0;
    border-bottom: 1px solid var(--rule);
    scroll-margin-top: 4rem;
  }
  .report-body .report-section:last-child { border-bottom: 0; padding-bottom: 0; }
  .report-body .report-section--first { padding-top: 0; }
  .report-body .report-section__title {
    margin: 0 0 16px;
    padding: 0 0 10px;
    font-size: clamp(1.15rem, 2.2vw, 1.4rem);
    font-weight: 700;
    color: var(--ink);
    text-transform: none;
    letter-spacing: -0.01em;
    border-bottom: 1px solid var(--rule);
    line-height: 1.3;
  }
  .report-body .report-section__markdown {
    width: 100%;
    font-size: 15px;
    line-height: 1.65;
    color: var(--ink);
  }
  .report-body h1 {
    font-size: 1.5rem;
    margin: 1.4em 0 0.6em;
    font-weight: 700;
    line-height: 1.25;
  }
  .report-body h2:not(.report-section__title) {
    font-size: 1.25rem;
    margin: 1.6em 0 0.55em;
    padding-bottom: 0.35em;
    border-bottom: 1px solid var(--rule);
    font-weight: 650;
    line-height: 1.3;
  }
  .report-body h3 {
    font-size: 1.1rem;
    margin: 1.35em 0 0.45em;
    font-weight: 650;
  }
  .report-body h4 {
    font-size: 1rem;
    margin: 1.1em 0 0.4em;
    color: var(--muted);
    font-weight: 600;
  }
  .report-body p {
    margin: 0 0 1em;
    max-width: 78ch;
  }
  .report-body ul,
  .report-body ol {
    margin: 0 0 1em;
    padding-left: 1.5em;
    max-width: 78ch;
  }
  .report-body li {
    margin: 0.35em 0;
    padding-left: 0.15em;
  }
  .report-body li > ul,
  .report-body li > ol {
    margin-top: 0.35em;
    margin-bottom: 0.35em;
  }
  .report-body strong { font-weight: 650; color: var(--ink); }
  .report-body .markdown-table-wrap {
    display: block;
    width: 100%;
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
    margin: 12px 0 18px;
    border: 1px solid var(--rule);
    border-radius: 8px;
    background: var(--surface);
  }
  .report-body table {
    width: 100%;
    min-width: 100%;
    border-collapse: collapse;
    font-size: 14px;
    line-height: 1.45;
    table-layout: auto;
  }
  .report-body .markdown-table-wrap table {
    width: 100%;
    min-width: 32rem;
    margin: 0;
  }
  .report-body th,
  .report-body td {
    padding: 10px 14px;
    border: 1px solid var(--rule);
    text-align: left;
    vertical-align: top;
    word-break: break-word;
    overflow-wrap: anywhere;
  }
  .report-body th {
    background: var(--soft);
    font-weight: 650;
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 0.03em;
    color: var(--muted);
  }
  .report-body tr:nth-child(even) td { background: ${EXPORT_TOKENS.tableStripe}; }
  .report-body code {
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
    background: var(--soft);
    padding: 0.12em 0.4em;
    border-radius: 4px;
    font-size: 0.88em;
  }
  .report-body pre {
    width: 100%;
    background: var(--soft);
    padding: 14px 16px;
    border-radius: 8px;
    overflow-x: auto;
    font-size: 13px;
    line-height: 1.5;
    border: 1px solid var(--rule);
  }
  .report-body pre code { background: transparent; padding: 0; }
  .report-body blockquote {
    margin: 0 0 1em;
    padding: 8px 16px;
    border: 1px solid var(--rule);
    color: var(--muted);
    background: var(--soft);
    border-radius: 8px;
    max-width: 78ch;
  }
  .report-body hr {
    border: 0;
    border-top: 1px solid var(--rule);
    margin: 28px 0;
  }
  .report-body a { color: var(--accent); text-decoration: underline; }
  .report-body img { max-width: 100%; height: auto; }
  footer {
    margin-top: 32px;
    padding-top: 16px;
    border-top: 1px solid var(--rule);
    color: var(--muted);
    font-size: 12px;
    text-align: center;
  }
  @media (min-width: 900px) {
    .feature-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    dl.levels { grid-template-columns: repeat(3, minmax(0, 1fr)); }
  }
  @media print {
    @page { size: auto; margin: 14mm 16mm; }
    html, body {
      background: #fff !important;
      width: 100% !important;
      height: auto !important;
      overflow: visible !important;
    }
    .export-page {
      max-width: none !important;
      width: 100% !important;
      padding: 0 !important;
      margin: 0 !important;
    }
    .export-toc { display: none !important; }
    .hero,
    section.card,
    .report-stack,
    .live-vs-plan,
    .feature-grid > * {
      box-shadow: none !important;
      break-inside: avoid-page;
      page-break-inside: avoid;
    }
    .report-body .report-section {
      break-inside: auto;
      page-break-inside: auto;
    }
    .report-body .report-section__title,
    .report-body h2,
    .report-body h3 {
      break-after: avoid-page;
      page-break-after: avoid;
    }
    .report-body p,
    .report-body ul,
    .report-body ol,
    .report-body blockquote {
      max-width: none !important;
    }
    .report-body .markdown-table-wrap {
      overflow: visible !important;
      border: none;
    }
    .report-body table {
      width: 100% !important;
      min-width: 0 !important;
    }
    .report-body,
    .report-body * {
      overflow: visible !important;
      max-height: none !important;
    }
    a[href^="#"] { text-decoration: none; color: inherit; }
  }
`;

function buildNavSections(input: StandaloneReportInput): ReportSectionLink[] {
  const fromDom =
    input.reportSections?.length
      ? input.reportSections
      : extractReportSectionsFromHtml(input.reportBodyHtml);

  const core: ReportSectionLink[] = [{ id: "decision", label: "Decision" }];
  if (input.liveContext) core.push({ id: "live-plan", label: "Live vs plan" });
  if (input.provenance) core.push({ id: "provenance", label: "Run setup" });
  if (input.analystCoverage && Object.keys(input.analystCoverage).length > 0) {
    core.push({ id: "analyst-coverage", label: "Analyst coverage" });
  }
  if (input.dimensions) core.push({ id: "dimensional-study", label: "Dimensions" });
  if (input.supplementaryHtml?.trim()) core.push({ id: "visual-evidence", label: "Visuals" });
  if (input.whyNow.length) core.push({ id: "why-now", label: "Why now" });
  if (input.invalidation) core.push({ id: "invalidation", label: "Invalidation" });
  core.push({ id: "agent-reports", label: "Agent reports" });
  return [...core, ...fromDom.filter((s) => !core.some((c) => c.id === s.id))];
}

function renderToc(sections: ReportSectionLink[]): string {
  const links = sections
    .map(
      (s) =>
        `<li><a href="#${escapeExportHtml(s.id)}">${escapeExportHtml(s.label)}</a></li>`,
    )
    .join("");
  return `<nav class="export-toc" aria-label="Contents">
    <p class="export-toc__label">Jump to section</p>
    <ul class="export-toc__links">${links}</ul>
  </nav>`;
}

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
    livePracticalNote,
    levelRows = [],
    liveContext = null,
    whyNow,
    invalidation,
    reportBodyHtml,
    supplementaryHtml = "",
    provenance = null,
    dimensions = null,
    dimensionsCommentary = null,
    analystCoverage = null,
    confidenceDetail = null,
    template = "weekly_report",
    generatedAt = new Date().toISOString(),
  } = input;

  const title = `${ticker} Agent report`;

  const navSections = template === "weekly_report" ? buildNavSections(input) : [];
  const tocBlock = navSections.length > 1 ? renderToc(navSections) : "";
  const normalizedBody = normalizeReportBodyHtml(reportBodyHtml);

  const decisionBriefHtml = renderDecisionBriefHtml({
    ticker,
    rating,
    date,
    generatedAt,
    confidencePct,
    ratingPlain,
    ratingPosture,
    actionNow,
    executiveSummary,
    livePracticalNote,
    levelRows,
    liveContext,
    calibration: confidenceDetail,
  });

  const metaCards: string[] = [];
  if (provenance) metaCards.push(renderProvenanceHtml(provenance));
  const coverageHtml = renderAnalystCoverageHtml(analystCoverage);
  if (coverageHtml) metaCards.push(coverageHtml);

  const featureGrid =
    metaCards.length > 0 ? `<div class="feature-grid">${metaCards.join("")}</div>` : "";

  const dimensionsHtml = renderDimensionsHtml(dimensions, dimensionsCommentary);

  const supplementaryBlock = supplementaryHtml.trim()
    ? `<section class="card supplementary" id="visual-evidence" aria-label="Visual evidence">${supplementaryHtml}</section>`
    : "";

  const whyNowList = whyNow.length
    ? `<ul>${whyNow.map((s) => `<li>${escapeExportHtml(s)}</li>`).join("")}</ul>`
    : "";
  const whyNowBlock = whyNowList
    ? `<section class="card" id="why-now" aria-label="Why now"><h2>Why now</h2>${whyNowList}</section>`
    : "";
  const invalidationBlock = invalidation
    ? `<section class="card" id="invalidation"><h2>Invalidation</h2><p>${escapeExportHtml(invalidation)}</p></section>`
    : "";

  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>${escapeExportHtml(title)}</title>
<style>${EMBEDDED_CSS}</style>
</head>
<body>
<div class="export-page">
  ${tocBlock}
  ${decisionBriefHtml}

    ${featureGrid}
    ${dimensionsHtml}
    ${supplementaryBlock}
    ${whyNowBlock}
    ${invalidationBlock}

    <div class="report-stack" id="agent-reports">
      <h2>Agent reports</h2>
      <div class="report-body">${normalizedBody}</div>
    </div>

    <footer>${escapeExportHtml(`Generated ${generatedAt} · ${ticker}`)}</footer>
</div>
</body>
</html>`;
}

/**
 * Open standalone report HTML in a new tab and run the browser print dialog.
 * Save as PDF there; avoids printing the TradingAgents app shell.
 */
export function printStandaloneReport(html: string): void {
  if (typeof window === "undefined" || typeof document === "undefined") return;

  const blob = new Blob([html], { type: "text/html;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const printWin = window.open(url, "_blank", "noopener,noreferrer");

  if (!printWin) {
    URL.revokeObjectURL(url);
    return;
  }

  const cleanup = () => {
    URL.revokeObjectURL(url);
    try {
      printWin.close();
    } catch {
      /* ignore */
    }
  };

  const runPrint = () => {
    printWin.focus();
    printWin.print();
    printWin.onafterprint = cleanup;
    window.setTimeout(cleanup, 120_000);
  };

  printWin.addEventListener("load", runPrint, { once: true });
}

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

export function downloadPng(filename: string, dataUrl: string): void {
  if (typeof document === "undefined") return;
  const a = document.createElement("a");
  a.href = dataUrl;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
}
