import type { PillarScore, PillarScores } from "../../dimensions-types";

const SCORE_COLORS = [
  "var(--color-danger)",
  "#f59e0b",
  "var(--color-amber-readout)",
  "var(--color-phosphor-dim)",
  "var(--color-phosphor)",
];

function Cell({ label, score }: { label: string; score: PillarScore }) {
  const color = SCORE_COLORS[score.score - 1] ?? "var(--color-ash-gray)";
  return (
    <button type="button" className="pillar-cell" title={score.rationale}>
      <div className="pillar-cell__label">{label}</div>
      <div className="pillar-cell__score" style={{ color }}>
        {score.score}/5
      </div>
    </button>
  );
}

export interface PillarGridProps {
  pillars: PillarScores;
}

const PILLAR_GROUPS: Array<[string, keyof PillarScores, string[]]> = [
  ["Market", "market", ["trend", "momentum", "volatility_risk", "setup_quality"]],
  [
    "Sentiment",
    "sentiment",
    ["retail_sentiment", "social_buzz", "consensus_quality", "narrative_strength"],
  ],
  ["News", "news", ["catalyst_strength", "macro_alignment", "headline_quality", "surprise_risk"]],
  [
    "Fundamentals",
    "fundamentals",
    ["valuation", "growth", "profitability", "balance_sheet_strength"],
  ],
];

export function PillarGrid({ pillars }: PillarGridProps) {
  return (
    <div className="pillar-grid">
      {PILLAR_GROUPS.map(([title, key, dims]) => (
        <div key={key} className="pillar-grid__group">
          <h4 className="pillar-grid__title">{title}</h4>
          <div className="pillar-grid__cells">
            {dims.map((d) => (
              <Cell
                key={d}
                label={d.replace(/_/g, " ")}
                score={(pillars[key] as Record<string, PillarScore>)[d]}
              />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
