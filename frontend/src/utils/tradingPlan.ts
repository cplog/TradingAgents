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

function escapeFieldLabel(label: string): string {
  return label.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/** Extract `**Label**: value` from markdown (single- or multi-line until next **Field**:). */
export function parseMdField(text: string, ...labels: string[]): string | null {
  if (!text.trim()) return null;
  for (const label of labels) {
    const re = new RegExp(
      `\\*\\*${escapeFieldLabel(label)}\\*\\*:\\s*([\\s\\S]*?)(?=\\n\\*\\*[A-Za-z][^*]*\\*\\*:|$)`,
      "i",
    );
    const m = text.match(re);
    if (!m?.[1]) continue;
    const value = m[1]
      .replace(/\*\*/g, "")
      .replace(/\s+/g, " ")
      .trim();
    if (value) return value;
  }
  return null;
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

  const entryRaw =
    parseMdField(trader, "Entry Price") ?? parseMdField(pm, "Entry Price", "Entry");
  const stopRaw = parseMdField(trader, "Stop Loss") ?? parseMdField(pm, "Stop Loss");
  const targetRaw = parseMdField(pm, "Price Target", "Target Price");

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
