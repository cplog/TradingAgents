import { normalizeRatingTier, ratingGuideFor } from "./ratingGuide";
import { deriveTradingPlan } from "./tradingPlan";

export type DecisionSummary = {
  /** Short desk instruction derived from the 5-tier rating. */
  actionNow: string;
  ratingPlain: string | null;
  ratingPosture: string | null;
  executiveSummary: string | null;
  confidencePct: number | null;
  confidenceLabel: string;
  fomoLabel: "Low" | "Medium" | "High";
  whyNow: string[];
  invalidation: string;
  horizon: string;
};

function cleanLine(raw: string): string {
  return raw
    .replace(/\*\*/g, "")
    .replace(/^[-*]\s+/, "")
    .replace(/^#+\s+/, "")
    .replace(/\s+/g, " ")
    .trim();
}

function firstMeaningfulLines(text: string, limit = 3): string[] {
  const out: string[] = [];
  for (const line of text.split("\n")) {
    const cleaned = cleanLine(line);
    if (!cleaned) continue;
    if (cleaned.length < 28) continue;
    if (/^(rating|executive summary|investment thesis|final transaction proposal)/i.test(cleaned)) {
      continue;
    }
    if (out.includes(cleaned)) continue;
    out.push(cleaned);
    if (out.length >= limit) break;
  }
  return out;
}

function actionFromRating(rating: string | null | undefined): string {
  const tier = normalizeRatingTier(rating);
  switch (tier) {
    case "Buy":
      return "Add or open position";
    case "Overweight":
      return "Build on dips";
    case "Hold":
      return "Hold; wait for a better setup";
    case "Underweight":
      return "Trim or avoid new buys";
    case "Sell":
      return "Reduce or exit";
    default:
      return "Review full report";
  }
}

export function deriveDecisionSummary(
  reports: Record<string, string> | undefined,
  rating: string | null | undefined,
  confidence: number | null | undefined,
): DecisionSummary {
  const guide = ratingGuideFor(rating);
  const actionNow = actionFromRating(rating);
  const plan = deriveTradingPlan(reports);

  const confidencePct =
    confidence != null && Number.isFinite(confidence)
      ? Math.max(0, Math.min(100, Math.round(confidence * 100)))
      : null;
  const confidenceLabel =
    confidencePct == null
      ? "Not enough signal"
      : confidencePct >= 75
        ? "High conviction"
        : confidencePct >= 55
          ? "Balanced conviction"
          : "Low conviction";

  const socialText = (reports?.social || "").toLowerCase();
  const newsText = (reports?.news || "").toLowerCase();
  const hypeTerms = ["hype", "mania", "fomo", "euphoric", "parabolic", "squeeze"];
  const hypeHits = hypeTerms.reduce(
    (count, term) => count + (socialText.includes(term) || newsText.includes(term) ? 1 : 0),
    0,
  );
  const tier = normalizeRatingTier(rating);
  const isBullishAction = tier === "Buy" || tier === "Overweight";
  const fomoLabel: DecisionSummary["fomoLabel"] =
    hypeHits >= 2 || (isBullishAction && (confidencePct ?? 0) < 60)
      ? "High"
      : hypeHits >= 1
        ? "Medium"
        : "Low";

  const whyNowSource =
    reports?.portfolio_decision || reports?.research_plan || reports?.market || "";
  const whyNow = firstMeaningfulLines(whyNowSource, 3);

  const traderPlan = reports?.trader_plan || "";
  const stopLossLine = traderPlan
    .split("\n")
    .map(cleanLine)
    .find((line) => /^stop loss:/i.test(line));
  const invalidation = stopLossLine
    ? stopLossLine.replace(/^stop loss:\s*/i, "")
    : "If thesis evidence weakens across fundamentals or trend confirmation, step back.";

  const pmText = reports?.portfolio_decision || "";
  const horizonMatch = pmText.match(/\*\*Time Horizon\*\*:\s*([^\n]+)/i);
  const horizon = plan.timeHorizon ?? horizonMatch?.[1]?.trim() ?? "3-6 months";

  return {
    actionNow,
    ratingPlain: guide?.plain ?? null,
    ratingPosture: guide?.posture ?? null,
    executiveSummary: plan.executiveSummary,
    confidencePct,
    confidenceLabel,
    fomoLabel,
    whyNow,
    invalidation,
    horizon,
  };
}
