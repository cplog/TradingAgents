import { memo, useMemo, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import type { DecisionSummary } from "../utils/decisionSummary";
import { RATING_GUIDE, RATING_TIERS_ORDER, normalizeRatingTier } from "../utils/ratingGuide";
import { ratingTone } from "../utils/historyDisplay";
import { deriveTradingPlan, tradingPlanRows } from "../utils/tradingPlan";
import type { JobLiveContext } from "../utils/livePlanContext";
import { isInvalidatedStatus } from "../utils/livePlanContext";
import { reportSectionDomId } from "../utils/reportMarkdown";
import { LiveVsPlanStrip } from "./LiveVsPlanStrip";

export type ConfidenceCalibration = {
  rawTierPct: number | null;
  breakdown?: {
    tier?: number;
    coherence_penalty?: number;
    data_quality_penalty?: number;
    peer_penalty?: number;
  } | null;
  inputs?: {
    supporting_factors?: { key: string; score: number }[];
    conflicting_factors?: { key: string; score: number }[];
    weak_data?: string[];
    peer_scope?: string | null;
  } | null;
};

type Props = {
  rating: string | null | undefined;
  confidencePct: number | null;
  summary: DecisionSummary;
  reports: Record<string, string> | undefined;
  calibration?: ConfidenceCalibration | null;
  liveContext?: JobLiveContext | null;
  liveContextLoading?: boolean;
  liveContextError?: string | null;
  tradeDate?: string | null;
};

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

function prettyFactor(key: string): string {
  return FACTOR_LABEL[key] ?? key;
}

function prettyFlag(key: string): string {
  if (key.startsWith("pillar_scoring_unavailable")) {
    return "Dimensional scoring unavailable (LLM provider / region)";
  }
  return FLAG_LABEL[key] ?? key.replace(/_/g, " ");
}

function confidenceTone(pct: number | null): "strong" | "balanced" | "weak" | "none" {
  if (pct == null) return "none";
  if (pct >= 70) return "strong";
  if (pct >= 50) return "balanced";
  return "weak";
}

export const DecisionBrief = memo(function DecisionBrief({
  rating,
  confidencePct,
  summary,
  reports,
  calibration,
  liveContext,
  liveContextLoading,
  liveContextError,
  tradeDate,
}: Props) {
  const [guideOpen, setGuideOpen] = useState(false);
  const tier = normalizeRatingTier(rating);
  const tone = ratingTone(rating);
  const plan = useMemo(() => deriveTradingPlan(reports), [reports]);
  const levelRows = useMemo(() => tradingPlanRows(plan), [plan]);
  const pmAnchor = `#${reportSectionDomId("portfolio_decision")}`;

  const supporting = calibration?.inputs?.supporting_factors ?? [];
  const conflicting = calibration?.inputs?.conflicting_factors ?? [];
  const weakData = calibration?.inputs?.weak_data ?? [];
  const peerScope = calibration?.inputs?.peer_scope ?? null;
  const breakdown = calibration?.breakdown ?? null;
  const rawTierPct = calibration?.rawTierPct ?? null;
  const hasCalibration = Boolean(
    calibration && (supporting.length || conflicting.length || weakData.length || breakdown),
  );
  const confTone = confidenceTone(confidencePct);

  return (
    <section className="decision-brief" aria-label="Final decision">
      {liveContext ? (
        <LiveVsPlanStrip
          context={liveContext}
          tradeDate={tradeDate}
          loading={liveContextLoading}
          error={liveContextError}
        />
      ) : null}

      <div className="decision-brief__head">
        <div className={`decision-brief__rating decision-brief__rating--${tone}`}>
          {rating?.trim() || "—"}
        </div>
        <div className="decision-brief__head-copy">
          {liveContext && isInvalidatedStatus(liveContext.comparison.status) ? (
            <p className="decision-brief__historical-rating">Historical rating from completed run</p>
          ) : null}
          {summary.ratingPlain && <p className="decision-brief__plain">{summary.ratingPlain}</p>}
          {summary.ratingPosture && (
            <p className="decision-brief__posture">{summary.ratingPosture}</p>
          )}
          {confidencePct != null && (
            <p
              className={`decision-brief__confidence decision-brief__confidence--${confTone}`}
              title={
                breakdown
                  ? `Tier ${Math.round((breakdown.tier ?? 0) * 100)}% · ` +
                    `−${Math.round((breakdown.coherence_penalty ?? 0) * 100)}pt factor conflicts · ` +
                    `−${Math.round((breakdown.data_quality_penalty ?? 0) * 100)}pt data gaps · ` +
                    `−${Math.round((breakdown.peer_penalty ?? 0) * 100)}pt peer scope`
                  : undefined
              }
            >
              Calibrated conviction: <strong>{confidencePct}%</strong>
              {rawTierPct != null && rawTierPct !== confidencePct ? (
                <span className="decision-brief__confidence-raw">
                  {" "}· rating tier alone {rawTierPct}%
                </span>
              ) : null}
            </p>
          )}
        </div>
      </div>

      {hasCalibration ? (
        <div className="decision-brief__inputs" aria-label="Decision inputs">
          {supporting.length > 0 ? (
            <div className="decision-brief__input-row decision-brief__input-row--good">
              <span className="decision-brief__input-label">Supports the call</span>
              <ul>
                {supporting.map((f) => (
                  <li key={f.key}>
                    {prettyFactor(f.key)} <span className="mono">{Math.round(f.score)}</span>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
          {conflicting.length > 0 ? (
            <div className="decision-brief__input-row decision-brief__input-row--warn">
              <span className="decision-brief__input-label">Conflicts with the call</span>
              <ul>
                {conflicting.map((f) => (
                  <li key={f.key}>
                    {prettyFactor(f.key)} <span className="mono">{Math.round(f.score)}</span>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
          {(weakData.length > 0 || peerScope) ? (
            <div className="decision-brief__input-row decision-brief__input-row--flag">
              <span className="decision-brief__input-label">Data caveats</span>
              <ul>
                {weakData.map((f) => (
                  <li key={f}>{prettyFlag(f)}</li>
                ))}
                {peerScope && peerScope !== "local" && peerScope !== "local_sector" ? (
                  <li>{PEER_SCOPE_LABEL[peerScope] ?? peerScope}</li>
                ) : null}
              </ul>
            </div>
          ) : null}
        </div>
      ) : null}

      <div className="decision-brief__action">
        <span className="decision-brief__action-label">What to do</span>
        <span className="decision-brief__action-value">{summary.actionNow}</span>
      </div>

      {summary.livePracticalNote ? (
        <div
          className={`decision-brief__live-note${
            liveContext && isInvalidatedStatus(liveContext.comparison.status)
              ? " decision-brief__live-note--warn"
              : ""
          }`}
          role="note"
        >
          <span className="decision-brief__live-note-label">Live check</span>
          <p>{summary.livePracticalNote}</p>
        </div>
      ) : null}

      {summary.executiveSummary && (
        <p className="decision-brief__summary">{summary.executiveSummary}</p>
      )}

      {levelRows.length > 0 && (
        <dl className="decision-brief__levels">
          {levelRows.map(({ label, value }) => (
            <div key={label} className="decision-brief__level">
              <dt>{label}</dt>
              <dd>{value}</dd>
            </div>
          ))}
        </dl>
      )}

      <div className="decision-brief__footer">
        <a className="decision-brief__link" href={pmAnchor}>
          Full portfolio decision ↓
        </a>
        <button
          type="button"
          className="decision-brief__guide-toggle"
          aria-expanded={guideOpen}
          onClick={() => setGuideOpen((v) => !v)}
        >
          {guideOpen ? "Hide rating scale" : "What do Buy / Overweight / Hold mean?"}
        </button>
      </div>

      <AnimatePresence>
        {guideOpen && (
          <motion.ul
            className="decision-brief__guide"
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto", transition: { duration: 0.2, ease: [0.25, 1, 0.5, 1] } }}
            exit={{ opacity: 0, height: 0, transition: { duration: 0.15, ease: [0.25, 1, 0.5, 1] } }}
          >
          {RATING_TIERS_ORDER.map((t) => (
            <li key={t} className={tier === t ? "decision-brief__guide-item--current" : undefined}>
              <strong>{t}</strong>
              <span>{RATING_GUIDE[t].plain}</span>
              <span className="decision-brief__guide-posture">{RATING_GUIDE[t].posture}</span>
            </li>
          ))}
          </motion.ul>
        )}
      </AnimatePresence>
      </section>
  );
});
