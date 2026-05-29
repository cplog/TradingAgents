/** Parse actionable levels from PM / trader markdown reports. */

export type TradingPlan = {
  executiveSummary: string | null;
  entry: string | null;
  stopLoss: string | null;
  priceTarget: string | null;
  positionSizing: string | null;
  timeHorizon: string | null;
  traderAction: string | null;
};

export type PlanLevels = {
  entry: number | null;
  stop_loss: number | null;
  price_target: number | null;
};

function escapeFieldLabel(label: string): string {
  return label.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/** Strip trader legacy trailer and normalize whitespace. */
export function cleanMdFieldValue(raw: string): string {
  const withoutTrailer = raw.replace(/\s*FINAL TRANSACTION PROPOSAL:[\s\S]*/i, "");
  return withoutTrailer
    .replace(/\*\*/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

/** Extract `**Label**: value` from markdown (single- or multi-line until next **Field**:). */
export function parseMdField(text: string, ...labels: string[]): string | null {
  if (!text.trim()) return null;
  for (const label of labels) {
    const re = new RegExp(
      `\\*\\*${escapeFieldLabel(label)}\\*\\*:\\s*([\\s\\S]*?)(?=\\n\\*\\*[A-Za-z][^*]*\\*\\*:|\\nFINAL TRANSACTION PROPOSAL:|$)`,
      "i",
    );
    const m = text.match(re);
    if (!m?.[1]) continue;
    const value = cleanMdFieldValue(m[1]);
    if (value) return value;
  }
  return null;
}

function parsePrice(value: string | null | undefined): number | null {
  if (!value) return null;
  const cleaned = value.replace(/,/g, "").trim();
  const n = Number(cleaned);
  if (Number.isFinite(n) && n > 0) return n;
  const m = cleaned.match(/(\d+(?:\.\d+)?)/);
  if (!m) return null;
  const parsed = Number(m[1]);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
}

function plausibleLevelPrice(value: number, reference: number | null | undefined): boolean {
  if (value <= 0 || value > 1_000_000) return false;
  if (reference != null && reference > 0) {
    const ratio = value / reference;
    if (ratio < 0.15 || ratio > 6) return false;
  }
  return true;
}

function pickNarrativePrice(matches: number[], reference: number | null | undefined): number | null {
  const candidates = matches.filter((m) => plausibleLevelPrice(m, reference));
  if (candidates.length === 0) return null;
  if (reference != null && reference > 0) {
    return candidates.reduce((best, x) =>
      Math.abs(x - reference) < Math.abs(best - reference) ? x : best,
    );
  }
  return candidates[0] ?? null;
}

function inferLevelsFromNarrative(text: string, reference?: number | null): PlanLevels {
  const entryMatches: number[] = [];
  const stopMatches: number[] = [];
  const targetMatches: number[] = [];

  const entryPatterns = [
    /(?:entry|buy(?:\s+zone)?|add(?:\s+near)?|accumulate(?:\s+(?:at|near|around))?)\s*(?:at|near|around|@|:)?\s*\$?\s*(\d+(?:\.\d+)?)/gi,
    /\bentry\s*:\s*\$?\s*(\d+(?:\.\d+)?)/gi,
    /pull-?back(?:\s+to)?\s*\$?\s*(\d+(?:\.\d+)?)/gi,
  ];
  const stopPatterns = [
    /(?:stop(?:\s*-?\s*loss)?|risk(?:\s+level)?)\s*(?:at|below|under|:)?\s*\$?\s*(\d+(?:\.\d+)?)/gi,
    /\bstop\s*:\s*\$?\s*(\d+(?:\.\d+)?)/gi,
  ];
  const targetPatterns = [
    /(?:price\s+target|target\s+price|upside\s+target|pt)\s*(?:at|of|to|:)?\s*\$?\s*(\d+(?:\.\d+)?)/gi,
    /\btarget\s*:\s*\$?\s*(\d+(?:\.\d+)?)/gi,
  ];

  for (const pat of entryPatterns) {
    for (const m of text.matchAll(pat)) entryMatches.push(Number(m[1]));
  }
  for (const pat of stopPatterns) {
    for (const m of text.matchAll(pat)) stopMatches.push(Number(m[1]));
  }
  for (const pat of targetPatterns) {
    for (const m of text.matchAll(pat)) targetMatches.push(Number(m[1]));
  }

  const triplet = text.match(
    /entry[^$\d]{0,40}\$?\s*(\d+(?:\.\d+)?)[^$\d]{0,40}stop[^$\d]{0,40}\$?\s*(\d+(?:\.\d+)?)[^$\d]{0,40}target[^$\d]{0,40}\$?\s*(\d+(?:\.\d+)?)/i,
  );
  if (triplet) {
    entryMatches.push(Number(triplet[1]));
    stopMatches.push(Number(triplet[2]));
    targetMatches.push(Number(triplet[3]));
  }

  const zone = text.match(
    /(?:between|range|zone)\s+\$?\s*(\d+(?:\.\d+)?)\s*(?:and|to|–|-)\s*\$?\s*(\d+(?:\.\d+)?)/i,
  );
  if (zone) {
    const lo = Number(zone[1]);
    const hi = Number(zone[2]);
    entryMatches.push((lo + hi) / 2);
  }

  return {
    entry: pickNarrativePrice(entryMatches, reference),
    stop_loss: pickNarrativePrice(stopMatches, reference),
    price_target: pickNarrativePrice(targetMatches, reference),
  };
}

function mergeLevels(...parts: Partial<PlanLevels>[]): PlanLevels {
  const out: PlanLevels = { entry: null, stop_loss: null, price_target: null };
  for (const part of parts) {
    if (out.entry == null && part.entry != null) out.entry = part.entry;
    if (out.stop_loss == null && part.stop_loss != null) out.stop_loss = part.stop_loss;
    if (out.price_target == null && part.price_target != null) out.price_target = part.price_target;
  }
  return out;
}

/** Numeric levels for live-vs-plan (mirrors backend derive_plan_levels). */
export function derivePlanLevels(
  reports: Record<string, string> | undefined,
  referencePrice?: number | null,
): PlanLevels {
  const pm = reports?.portfolio_decision ?? "";
  const trader = reports?.trader_plan ?? "";
  const research = reports?.research_plan ?? "";

  const labeled: PlanLevels = {
    entry:
      parsePrice(parseMdField(trader, "Entry Price") ?? parseMdField(pm, "Entry Price", "Entry")),
    stop_loss: parsePrice(parseMdField(trader, "Stop Loss") ?? parseMdField(pm, "Stop Loss")),
    price_target: parsePrice(
      parseMdField(pm, "Price Target", "Target Price") ??
        parseMdField(trader, "Price Target", "Target Price"),
    ),
  };

  const strategic = parseMdField(research, "Strategic Actions") ?? "";
  const execSummary = parseMdField(pm, "Executive Summary") ?? "";
  let narrative: PlanLevels = { entry: null, stop_loss: null, price_target: null };
  for (const block of [trader, pm, strategic, execSummary, research]) {
    if (!block.trim()) continue;
    narrative = mergeLevels(narrative, inferLevelsFromNarrative(block, referencePrice));
  }

  return mergeLevels(labeled, narrative);
}

function formatPrice(value: string | null): string | null {
  if (!value) return null;
  const n = Number(value.replace(/,/g, ""));
  if (Number.isFinite(n)) {
    return n.toLocaleString(undefined, { maximumFractionDigits: 2 });
  }
  return value;
}

export function deriveTradingPlan(reports: Record<string, string> | undefined): TradingPlan {
  const pm = reports?.portfolio_decision ?? "";
  const trader = reports?.trader_plan ?? "";

  const levels = derivePlanLevels(reports);
  const entryRaw =
    parseMdField(trader, "Entry Price") ??
    parseMdField(pm, "Entry Price", "Entry") ??
    (levels.entry != null ? String(levels.entry) : null);
  const stopRaw =
    parseMdField(trader, "Stop Loss") ??
    parseMdField(pm, "Stop Loss") ??
    (levels.stop_loss != null ? String(levels.stop_loss) : null);
  const targetRaw =
    parseMdField(pm, "Price Target", "Target Price") ??
    (levels.price_target != null ? String(levels.price_target) : null);

  return {
    executiveSummary: parseMdField(pm, "Executive Summary"),
    entry: formatPrice(entryRaw),
    stopLoss: formatPrice(stopRaw) ?? stopRaw,
    priceTarget: formatPrice(targetRaw),
    positionSizing: parseMdField(trader, "Position Sizing") ?? parseMdField(pm, "Position Sizing"),
    timeHorizon: parseMdField(pm, "Time Horizon"),
    traderAction: parseMdField(trader, "Action"),
  };
}

/** Rows to show in the trading plan grid (label + value), omitting empties. */
export function tradingPlanRows(plan: TradingPlan): { label: string; value: string }[] {
  const rows: { label: string; value: string }[] = [];
  if (plan.entry) rows.push({ label: "Entry / buy zone", value: plan.entry });
  if (plan.priceTarget) rows.push({ label: "Price target", value: plan.priceTarget });
  if (plan.stopLoss) rows.push({ label: "Stop / risk level", value: plan.stopLoss });
  if (plan.positionSizing) rows.push({ label: "Position size", value: plan.positionSizing });
  if (plan.timeHorizon) rows.push({ label: "Time horizon", value: plan.timeHorizon });
  if (plan.traderAction) rows.push({ label: "Trader action", value: plan.traderAction });
  return rows;
}
