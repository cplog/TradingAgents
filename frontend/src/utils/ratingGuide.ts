/** Five-tier portfolio rating used by the Portfolio Manager. */

export type RatingTier = "Buy" | "Overweight" | "Hold" | "Underweight" | "Sell";

export type RatingGuideEntry = {
  /** One-line meaning for traders scanning a run. */
  plain: string;
  /** What the desk would typically do. */
  posture: string;
};

export const RATING_GUIDE: Record<RatingTier, RatingGuideEntry> = {
  Buy: {
    plain: "Highest conviction bullish view",
    posture: "Open or add a full position when risk limits allow",
  },
  Overweight: {
    plain: "Bullish, but sized with care",
    posture: "Build gradually; often wait for a pullback before adding",
  },
  Hold: {
    plain: "Neutral; no strong edge to add or cut",
    posture: "Maintain current size; only add if your plan says so on a dip",
  },
  Underweight: {
    plain: "Cautious; lean bearish",
    posture: "Trim exposure or avoid new buys",
  },
  Sell: {
    plain: "Bearish conviction",
    posture: "Reduce or exit the position",
  },
};

export const RATING_TIERS_ORDER: RatingTier[] = [
  "Buy",
  "Overweight",
  "Hold",
  "Underweight",
  "Sell",
];

/** Normalize API / LLM rating strings to a known tier, or null. */
export function normalizeRatingTier(rating: string | null | undefined): RatingTier | null {
  if (!rating?.trim()) return null;
  const r = rating.trim();
  for (const tier of RATING_TIERS_ORDER) {
    if (r.toLowerCase() === tier.toLowerCase()) return tier;
  }
  if (/strong\s+buy/i.test(r)) return "Buy";
  if (/overweight/i.test(r)) return "Overweight";
  if (/underweight/i.test(r)) return "Underweight";
  if (/sell/i.test(r)) return "Sell";
  if (/hold/i.test(r)) return "Hold";
  if (/buy/i.test(r)) return "Buy";
  return null;
}

export function ratingGuideFor(rating: string | null | undefined): RatingGuideEntry | null {
  const tier = normalizeRatingTier(rating);
  return tier ? RATING_GUIDE[tier] : null;
}
