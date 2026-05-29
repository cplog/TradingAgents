import { useMemo, useState } from "react";
import type { DecisionSummary } from "../utils/decisionSummary";
import { RATING_GUIDE, RATING_TIERS_ORDER, normalizeRatingTier } from "../utils/ratingGuide";
import { ratingTone } from "../utils/historyDisplay";
import { deriveTradingPlan, tradingPlanRows } from "../utils/tradingPlan";
import { reportSectionDomId } from "../utils/reportMarkdown";

type Props = {
  rating: string | null | undefined;
  confidencePct: number | null;
  summary: DecisionSummary;
  reports: Record<string, string> | undefined;
};

export function DecisionBrief({ rating, confidencePct, summary, reports }: Props) {
  const [guideOpen, setGuideOpen] = useState(false);
  const tier = normalizeRatingTier(rating);
  const tone = ratingTone(rating);
  const plan = useMemo(() => deriveTradingPlan(reports), [reports]);
  const levelRows = useMemo(() => tradingPlanRows(plan), [plan]);
  const pmAnchor = `#${reportSectionDomId("portfolio_decision")}`;

  return (
    <section className="decision-brief" aria-label="Final decision">
      <div className="decision-brief__head">
        <div className={`decision-brief__rating decision-brief__rating--${tone}`}>
          {rating?.trim() || "—"}
        </div>
        <div className="decision-brief__head-copy">
          {summary.ratingPlain && <p className="decision-brief__plain">{summary.ratingPlain}</p>}
          {summary.ratingPosture && (
            <p className="decision-brief__posture">{summary.ratingPosture}</p>
          )}
          {confidencePct != null && (
            <p className="decision-brief__confidence">
              Conviction (heuristic): {confidencePct}% — from rating tier, not model certainty
            </p>
          )}
        </div>
      </div>

      <div className="decision-brief__action">
        <span className="decision-brief__action-label">What to do</span>
        <span className="decision-brief__action-value">{summary.actionNow}</span>
      </div>

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

      {guideOpen && (
        <ul className="decision-brief__guide">
          {RATING_TIERS_ORDER.map((t) => (
            <li key={t} className={tier === t ? "decision-brief__guide-item--current" : undefined}>
              <strong>{t}</strong>
              <span>{RATING_GUIDE[t].plain}</span>
              <span className="decision-brief__guide-posture">{RATING_GUIDE[t].posture}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
