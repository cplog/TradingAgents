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

export type StandaloneReportInput = {
  ticker: string;
  rating?: string | null;
  date?: string | null;
  confidencePct?: number | null;
  decisionRows: ReadonlyArray<readonly [label: string, value: string]>;
  whyNow: ReadonlyArray<string>;
  invalidation?: string | null;
  /** Outer HTML of the rendered `.dashboard-report-markdown` element. */
  reportBodyHtml: string;
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
  }
`;

export function buildStandaloneReportHtml(input: StandaloneReportInput): string {
  const {
    ticker,
    rating,
    date,
    confidencePct,
    decisionRows,
    whyNow,
    invalidation,
    reportBodyHtml,
    generatedAt = new Date().toISOString(),
  } = input;

  const title = `${ticker} — Agent report`;
  const ratingLine = rating ? escapeHtml(rating) : "—";
  const metaParts: string[] = [`<span><strong>${escapeHtml(ticker)}</strong></span>`];
  if (date) metaParts.push(`<span>As of ${escapeHtml(date)}</span>`);
  if (confidencePct != null) {
    metaParts.push(`<span>Confidence (heuristic): ${confidencePct}%</span>`);
  }
  metaParts.push(`<span>Exported ${escapeHtml(generatedAt)}</span>`);

  const decisionDl = decisionRows
    .map(
      ([label, value]) =>
        `<div><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(value)}</dd></div>`,
    )
    .join("");

  const whyNowList = whyNow.length
    ? `<ul>${whyNow.map((s) => `<li>${escapeHtml(s)}</li>`).join("")}</ul>`
    : `<p style="color:var(--muted);margin:0">No concise reason lines found in the generated report.</p>`;

  const invalidationBlock = invalidation
    ? `<section class="card"><h2>Invalidation</h2><p>${escapeHtml(invalidation)}</p></section>`
    : "";

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
  <header class="hero">
    <p class="eyebrow">Agent report — research artifact, not financial advice</p>
    <h1>${ratingLine}</h1>
    <div class="meta">${metaParts.join("")}</div>
  </header>

  <section class="card" aria-label="At a glance">
    <h2>At a glance</h2>
    <dl class="decision">${decisionDl}</dl>
  </section>

  <section class="card" aria-label="Why now">
    <h2>Why now</h2>
    ${whyNowList}
  </section>

  ${invalidationBlock}

  <section class="card" aria-label="Full report">
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
