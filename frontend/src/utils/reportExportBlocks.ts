/**
 * Pure HTML fragment builders for standalone report export (no React).
 */

import type { JobResultPayload, RunProvenance } from "../api";
import type { DimensionsCommentary, StockDimensions } from "../dimensions-types";
import { ratingTone } from "./historyDisplay";
import type { JobLiveContext } from "./livePlanContext";
import { formatLivePrice, isInvalidatedStatus } from "./livePlanContext";
import { REPORT_SECTION_LABELS } from "./reportMarkdown";
import { formatLlmLabel } from "./runProvenance";

const HTML_ESCAPE: Record<string, string> = {
  "&": "&amp;",
  "<": "&lt;",
  ">": "&gt;",
  '"': "&quot;",
  "'": "&#39;",
};

export function escapeExportHtml(s: string): string {
  return s.replace(/[&<>"']/g, (c) => HTML_ESCAPE[c] ?? c);
}

export type ReportSectionLink = { id: string; label: string };

export function reportSectionsFromKeys(keys: string[]): ReportSectionLink[] {
  return keys.map((key) => ({
    id: `report-section-${key}`,
    label: REPORT_SECTION_LABELS[key] ?? key.replace(/_/g, " "),
  }));
}

export function extractReportSectionsFromHtml(reportBodyHtml: string): ReportSectionLink[] {
  const sections: ReportSectionLink[] = [];
  const seen = new Set<string>();

  const sectionRe =
    /<section\b[^>]*\bid\s*=\s*["']([^"']+)["'][^>]*>[\s\S]*?<h2\b[^>]*class\s*=\s*["'][^"']*report-section__title[^"']*["'][^>]*>([\s\S]*?)<\/h2>/gi;
  let m: RegExpExecArray | null = sectionRe.exec(reportBodyHtml);
  while (m) {
    const id = (m[1] ?? "").trim();
    const label = stripTags(m[2] ?? "");
    if (id && label && !seen.has(id)) {
      seen.add(id);
      sections.push({ id, label });
    }
    m = sectionRe.exec(reportBodyHtml);
  }

  const h2Re = /<h2\b([^>]*)>([\s\S]*?)<\/h2>/gi;
  m = h2Re.exec(reportBodyHtml);
  while (m) {
    const attrs = m[1] ?? "";
    const label = stripTags(m[2] ?? "");
    const idMatch = /\bid\s*=\s*["']([^"']+)["']/i.exec(attrs);
    const id = (idMatch?.[1] ?? "").trim();
    if (id && label && !seen.has(id)) {
      seen.add(id);
      sections.push({ id, label });
    }
    m = h2Re.exec(reportBodyHtml);
  }
  return sections;
}

function stripTags(s: string): string {
  return s.replace(/<[^>]*>/g, "").replace(/\s+/g, " ").trim();
}

const FACTOR_LABEL: Record<string, string> = {
  value: "Value",
  growth: "Growth",
  quality: "Quality",
  momentum: "Momentum",
  low_risk: "Low Risk",
  sentiment: "Sentiment",
};

const FLAG_LABEL: Record<string, string> = {
  missing_pe_ttm: "Missing P/E TTM",
  missing_peg: "Missing PEG",
  missing_eps_growth_yoy: "Missing EPS growth (YoY)",
  peer_percentiles_cache_miss: "Peer cache miss",
  peer_percentiles_unavailable: "No peer percentiles",
};

const PEER_SCOPE_LABEL: Record<string, string> = {
  local: "Local peers",
  local_sector: "Local sector peers",
  global_fallback: "Global fallback peers",
  unavailable: "No peer scope",
};

function liveStatusLabel(status: string): string {
  switch (status) {
    case "below_stop":
      return "Setup invalidated";
    case "below_entry":
      return "Below entry zone";
    case "in_entry_zone":
      return "Near entry zone";
    case "above_entry":
      return "Above entry";
    case "above_target":
      return "At/above target";
    case "quote_unavailable":
      return "Live quote unavailable";
    case "no_levels":
      return "No plan levels";
    default:
      return "Live vs plan";
  }
}

function liveStatusClass(status: string): string {
  if (status === "below_stop") return "live-vs-plan--invalidated";
  if (status === "below_entry" || status === "quote_unavailable" || status === "no_levels") {
    return "live-vs-plan--caution";
  }
  if (status === "in_entry_zone") return "live-vs-plan--ok";
  return "live-vs-plan--neutral";
}

function prettyFactor(key: string): string {
  return FACTOR_LABEL[key] ?? key;
}

function prettyFlag(key: string): string {
  if (key.startsWith("pillar_scoring_unavailable")) {
    return "Dimensional scoring unavailable (LLM provider / region)";
  }
  return FLAG_LABEL[key] ?? key.replace(/_/g, " ");
}

function confidenceToneClass(pct: number | null): string {
  if (pct == null) return "none";
  if (pct >= 70) return "strong";
  if (pct >= 50) return "balanced";
  return "weak";
}

const COVERAGE_STATUS_LABEL: Record<string, string> = {
  ok: "OK",
  empty: "Empty",
  failed: "Failed",
  skipped: "Skipped",
};

export function renderProvenanceHtml(provenance: RunProvenance | null | undefined): string {
  if (!provenance) {
    return `<section class="card card--meta" id="provenance" aria-label="Run provenance">
      <h2>Run setup</h2>
      <p class="muted">No model or data-source snapshot for this run.</p>
    </section>`;
  }
  const warnings = provenance.bias_warnings ?? [];
  const analysts =
    provenance.analysts_selected?.length
      ? escapeExportHtml(provenance.analysts_selected.join(", "))
      : provenance.analysts_total
        ? `${provenance.analysts_total} selected`
        : "—";
  const analystStats =
    provenance.analysts_ok != null && provenance.analysts_total
      ? ` · ${provenance.analysts_ok} ok${provenance.analysts_empty ? ` · ${provenance.analysts_empty} empty` : ""}`
      : "";
  const warningsBlock =
    warnings.length > 0
      ? `<ul class="warn-list">${warnings.map((w) => `<li>${escapeExportHtml(w)}</li>`).join("")}</ul>`
      : "";

  return `<section class="card card--meta" id="provenance" aria-label="Run provenance">
    <h2>Run setup</h2>
    <dl class="meta-grid">
      <div><dt>LLM</dt><dd>${escapeExportHtml(formatLlmLabel(provenance))}</dd></div>
      <div><dt>Data routing</dt><dd>${escapeExportHtml(provenance.data_routing ?? "—")}</dd></div>
      <div><dt>Analysts</dt><dd>${analysts}${escapeExportHtml(analystStats)}</dd></div>
      <div><dt>Source diversity</dt><dd>${provenance.source_pillars ?? 0}/4 pillars · ${provenance.vendor_count ?? 0} vendor${(provenance.vendor_count ?? 0) === 1 ? "" : "s"}</dd></div>
    </dl>
    ${warningsBlock}
  </section>`;
}

export function renderAnalystCoverageHtml(
  coverage: JobResultPayload["analyst_coverage"] | null | undefined,
): string {
  if (!coverage || Object.keys(coverage).length === 0) return "";
  const rows = Object.entries(coverage)
    .map(([key, row]) => {
      const status = COVERAGE_STATUS_LABEL[row.status] ?? row.status;
      const detail = row.detail ? escapeExportHtml(row.detail) : "";
      const chars = row.chars != null ? `${row.chars.toLocaleString()} chars` : "";
      return `<tr>
        <th scope="row">${escapeExportHtml(REPORT_SECTION_LABELS[key] ?? key)}</th>
        <td><span class="badge badge--${escapeExportHtml(row.status)}">${escapeExportHtml(status)}</span></td>
        <td>${chars}</td>
        <td class="muted">${detail}</td>
      </tr>`;
    })
    .join("");

  return `<section class="card card--meta" id="analyst-coverage" aria-label="Analyst coverage">
    <h2>Analyst coverage</h2>
    <div class="table-scroll">
      <table class="data-table">
        <thead><tr><th>Analyst</th><th>Status</th><th>Output</th><th>Detail</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
  </section>`;
}

export function renderDimensionsHtml(
  dimensions: StockDimensions | null | undefined,
  commentary: DimensionsCommentary | null | undefined,
): string {
  if (!dimensions) return "";

  const factors = (["value", "growth", "quality", "momentum", "low_risk", "sentiment"] as const)
    .map((key) => {
      const f = dimensions.factor_scores[key];
      const score = f?.score != null ? Math.round(f.score) : "—";
      return `<div class="factor-chip"><span class="factor-chip__label">${FACTOR_LABEL[key]}</span><span class="factor-chip__score">${score}</span></div>`;
    })
    .join("");

  const commentaryBlock = commentary?.summary
    ? `<div class="dimensions-commentary">
        <p class="dimensions-commentary__alignment">PM alignment: <strong>${escapeExportHtml(commentary.alignment)}</strong></p>
        <p>${escapeExportHtml(commentary.summary)}</p>
        ${
          commentary.supporting_dimensions?.length
            ? `<p class="muted"><strong>Supporting:</strong> ${commentary.supporting_dimensions.map(escapeExportHtml).join(", ")}</p>`
            : ""
        }
        ${
          commentary.conflicting_dimensions?.length
            ? `<p class="muted"><strong>Conflicting:</strong> ${commentary.conflicting_dimensions.map(escapeExportHtml).join(", ")}</p>`
            : ""
        }
      </div>`
    : "";

  const flags =
    dimensions.data_quality_flags?.length
      ? `<p class="muted">Data flags: ${dimensions.data_quality_flags.map(escapeExportHtml).join(", ")}</p>`
      : "";

  return `<section class="card" id="dimensional-study" aria-label="Dimensional study">
    <h2>Dimensional study</h2>
    <p class="muted">Standardized pillar and factor scores from market data and analyst reports (v${escapeExportHtml(dimensions.dimensions_version)}${dimensions.peer_scope ? ` · ${escapeExportHtml(dimensions.peer_scope)} peers` : ""}).</p>
    <div class="factor-grid">${factors}</div>
    ${commentaryBlock}
    ${flags}
  </section>`;
}

export type ConfidenceExportBlock = {
  rawTierPct: number | null;
  breakdown?: {
    tier?: number;
    coherence_penalty?: number;
    data_quality_penalty?: number;
    peer_penalty?: number;
  } | null;
  supporting: { key: string; score: number }[];
  conflicting: { key: string; score: number }[];
  weakData: string[];
  peerScope: string | null;
};

export function renderLiveVsPlanHtml(
  context: JobLiveContext,
  tradeDate?: string | null,
): string {
  const { quote, comparison, report_close: reportClose, levels, run_time_quote: runTimeQuote } =
    context;
  const tone = liveStatusClass(comparison.status);
  const suggestRefresh = comparison.suggest_refresh === true;

  const reportDateBlock =
    tradeDate && reportClose != null
      ? `<div><dt>Report date close</dt><dd class="mono">${escapeExportHtml(formatLivePrice(reportClose, quote.currency))} · ${escapeExportHtml(tradeDate)}</dd></div>`
      : tradeDate
        ? `<div><dt>Report as of</dt><dd>${escapeExportHtml(tradeDate)}</dd></div>`
        : "";

  const runTimeBlock =
    runTimeQuote?.price != null
      ? `<div><dt>At run time</dt><dd class="mono">${escapeExportHtml(
          formatLivePrice(runTimeQuote.price, runTimeQuote.currency ?? quote.currency),
        )}</dd></div>`
      : "";

  const levelBits: string[] = [];
  if (levels.entry != null) {
    levelBits.push(
      `<div><dt>Planned entry</dt><dd class="mono">${levels.entry.toLocaleString(undefined, { maximumFractionDigits: 2 })}</dd></div>`,
    );
  }
  if (levels.stop_loss != null) {
    levelBits.push(
      `<div><dt>Stop</dt><dd class="mono">${levels.stop_loss.toLocaleString(undefined, { maximumFractionDigits: 2 })}</dd></div>`,
    );
  }
  if (levels.price_target != null) {
    levelBits.push(
      `<div><dt>Target</dt><dd class="mono">${levels.price_target.toLocaleString(undefined, { maximumFractionDigits: 2 })}</dd></div>`,
    );
  }

  const historicalBlock = isInvalidatedStatus(comparison.status)
    ? `<p class="live-vs-plan__historical">Historical rating unchanged — this warning reflects <strong>current price vs this run&apos;s levels</strong>.${
        suggestRefresh
          ? " Refresh analysis with today&apos;s date before acting."
          : " Analysis already used the live quote at run time; do not use these levels as-is."
      }</p>`
    : context.historical_rating_note
      ? `<p class="live-vs-plan__historical">${escapeExportHtml(context.historical_rating_note)}</p>`
      : "";

  return `<section class="live-vs-plan ${tone}" id="live-plan" aria-label="Live price versus report plan">
    <span class="live-vs-plan__badge">${escapeExportHtml(liveStatusLabel(comparison.status))}</span>
    <dl class="live-vs-plan__grid">
      <div><dt>Live now</dt><dd class="mono">${escapeExportHtml(formatLivePrice(quote.price, quote.currency))}</dd></div>
      ${runTimeBlock}
      ${reportDateBlock}
      ${levelBits.join("")}
    </dl>
    <p class="live-vs-plan__guidance">${escapeExportHtml(comparison.guidance)}</p>
    ${historicalBlock}
  </section>`;
}

export type DecisionBriefExportInput = {
  ticker: string;
  rating?: string | null;
  date?: string | null;
  generatedAt: string;
  confidencePct?: number | null;
  ratingPlain?: string | null;
  ratingPosture?: string | null;
  actionNow?: string | null;
  executiveSummary?: string | null;
  livePracticalNote?: string | null;
  levelRows?: ReadonlyArray<readonly [label: string, value: string]>;
  liveContext?: JobLiveContext | null;
  calibration?: ConfidenceExportBlock | null;
};

export function renderDecisionBriefHtml(input: DecisionBriefExportInput): string {
  const {
    ticker,
    rating,
    date,
    generatedAt,
    confidencePct = null,
    ratingPlain,
    ratingPosture,
    actionNow,
    executiveSummary,
    livePracticalNote,
    levelRows = [],
    liveContext = null,
    calibration = null,
  } = input;

  const tone = ratingTone(rating);
  const ratingText = rating?.trim() || "—";
  const confTone = confidenceToneClass(confidencePct);
  const breakdown = calibration?.breakdown ?? null;
  const rawTierPct = calibration?.rawTierPct ?? null;
  const supporting = calibration?.supporting ?? [];
  const conflicting = calibration?.conflicting ?? [];
  const weakData = calibration?.weakData ?? [];
  const peerScope = calibration?.peerScope ?? null;
  const hasCalibration = Boolean(
    calibration && (supporting.length || conflicting.length || weakData.length || breakdown),
  );

  const confidenceTitle = breakdown
    ? `Tier ${Math.round((breakdown.tier ?? 0) * 100)}% · −${Math.round((breakdown.coherence_penalty ?? 0) * 100)}pt factor conflicts · −${Math.round((breakdown.data_quality_penalty ?? 0) * 100)}pt data gaps · −${Math.round((breakdown.peer_penalty ?? 0) * 100)}pt peer scope`
    : "";

  const confidenceLine =
    confidencePct != null
      ? `<p class="decision-brief__confidence decision-brief__confidence--${confTone}"${
          confidenceTitle ? ` title="${escapeExportHtml(confidenceTitle)}"` : ""
        }>Calibrated conviction: <strong>${confidencePct}%</strong>${
          rawTierPct != null && rawTierPct !== confidencePct
            ? `<span class="decision-brief__confidence-raw"> · rating tier alone ${rawTierPct}%</span>`
            : ""
        }</p>`
      : "";

  const calibrationBlock = hasCalibration
    ? `<div class="decision-brief__inputs" aria-label="Decision inputs">
        ${
          supporting.length
            ? `<div class="decision-brief__input-row decision-brief__input-row--good">
                <span class="decision-brief__input-label">Supports the call</span>
                <ul>${supporting
                  .map(
                    (f) =>
                      `<li>${escapeExportHtml(prettyFactor(f.key))} <span class="mono">${Math.round(f.score)}</span></li>`,
                  )
                  .join("")}</ul>
              </div>`
            : ""
        }
        ${
          conflicting.length
            ? `<div class="decision-brief__input-row decision-brief__input-row--warn">
                <span class="decision-brief__input-label">Conflicts with the call</span>
                <ul>${conflicting
                  .map(
                    (f) =>
                      `<li>${escapeExportHtml(prettyFactor(f.key))} <span class="mono">${Math.round(f.score)}</span></li>`,
                  )
                  .join("")}</ul>
              </div>`
            : ""
        }
        ${
          weakData.length || peerScope
            ? `<div class="decision-brief__input-row decision-brief__input-row--flag">
                <span class="decision-brief__input-label">Data caveats</span>
                <ul>
                  ${weakData.map((f) => `<li>${escapeExportHtml(prettyFlag(f))}</li>`).join("")}
                  ${
                    peerScope && peerScope !== "local" && peerScope !== "local_sector"
                      ? `<li>${escapeExportHtml(PEER_SCOPE_LABEL[peerScope] ?? peerScope)}</li>`
                      : ""
                  }
                </ul>
              </div>`
            : ""
        }
      </div>`
    : "";

  const liveNoteBlock =
    livePracticalNote?.trim()
      ? `<div class="decision-brief__live-note${
          liveContext && isInvalidatedStatus(liveContext.comparison.status)
            ? " decision-brief__live-note--warn"
            : ""
        }" role="note">
          <span class="decision-brief__live-note-label">Live check</span>
          <p>${escapeExportHtml(livePracticalNote.trim())}</p>
        </div>`
      : "";

  const levelsBlock =
    levelRows.length > 0
      ? `<dl class="decision-brief__levels">${levelRows
          .map(
            ([label, value]) =>
              `<div class="decision-brief__level"><dt>${escapeExportHtml(label)}</dt><dd>${escapeExportHtml(value)}</dd></div>`,
          )
          .join("")}</dl>`
      : "";

  const metaParts = [`<span><strong>${escapeExportHtml(ticker)}</strong></span>`];
  if (date) metaParts.push(`<span>As of ${escapeExportHtml(date)}</span>`);
  metaParts.push(`<span>Exported ${escapeExportHtml(generatedAt)}</span>`);

  return `<section class="decision-brief" id="decision" aria-label="Final decision">
    <p class="decision-brief__eyebrow">Agent report — research artifact, not financial advice</p>
    ${liveContext ? renderLiveVsPlanHtml(liveContext, date) : ""}
    <div class="decision-brief__head">
      <div class="decision-brief__rating decision-brief__rating--${tone}">${escapeExportHtml(ratingText)}</div>
      <div class="decision-brief__head-copy">
        ${
          liveContext && isInvalidatedStatus(liveContext.comparison.status)
            ? `<p class="decision-brief__historical-rating">Historical rating from completed run</p>`
            : ""
        }
        ${ratingPlain ? `<p class="decision-brief__plain">${escapeExportHtml(ratingPlain)}</p>` : ""}
        ${ratingPosture ? `<p class="decision-brief__posture">${escapeExportHtml(ratingPosture)}</p>` : ""}
        ${confidenceLine}
      </div>
    </div>
    ${calibrationBlock}
    ${
      actionNow?.trim()
        ? `<div class="decision-brief__action">
            <span class="decision-brief__action-label">What to do</span>
            <span class="decision-brief__action-value">${escapeExportHtml(actionNow.trim())}</span>
          </div>`
        : ""
    }
    ${liveNoteBlock}
    ${
      executiveSummary?.trim()
        ? `<p class="decision-brief__summary">${escapeExportHtml(executiveSummary.trim())}</p>`
        : ""
    }
    ${levelsBlock}
    <div class="decision-brief__meta">${metaParts.join("")}</div>
  </section>`;
}
