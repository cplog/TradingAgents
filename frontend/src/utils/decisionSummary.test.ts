import { describe, expect, it } from "vitest";
import { deriveDecisionSummary } from "./decisionSummary";
import { normalizeRatingTier } from "./ratingGuide";
import { deriveTradingPlan, parseMdField } from "./tradingPlan";

describe("ratingGuide", () => {
  it("normalizes tier strings", () => {
    expect(normalizeRatingTier("Hold")).toBe("Hold");
    expect(normalizeRatingTier("overweight")).toBe("Overweight");
  });
});

describe("tradingPlan", () => {
  it("parses PM executive summary and levels", () => {
    const pm = [
      "**Rating**: Hold",
      "",
      "**Executive Summary**: Maintain exposure; add only on a 4-6% pullback toward $1,380-$1,420.",
      "",
      "**Investment Thesis**: Long thesis here.",
      "",
      "**Price Target**: 1650",
      "",
      "**Time Horizon**: 3-6 months",
    ].join("\n");
    const trader = [
      "**Action**: Hold",
      "",
      "**Reasoning**: No edge to chase.",
      "",
      "**Stop Loss**: 13% from entry",
    ].join("\n");

    const plan = deriveTradingPlan({ portfolio_decision: pm, trader_plan: trader });
    expect(plan.executiveSummary).toContain("pullback");
    expect(plan.priceTarget).toBe("1,650");
    expect(plan.stopLoss).toBe("13% from entry");
    expect(plan.timeHorizon).toBe("3-6 months");
  });

  it("parseMdField stops at next bold label", () => {
    const text = "**Executive Summary**: Line one.\n\n**Investment Thesis**: More text.";
    expect(parseMdField(text, "Executive Summary")).toBe("Line one.");
  });
});

describe("decisionSummary", () => {
  it("maps Overweight to build-on-dips, not buy-now", () => {
    const s = deriveDecisionSummary(
      { portfolio_decision: "**Rating**: Overweight\n\n**Executive Summary**: Scale in." },
      "Overweight",
      0.6,
    );
    expect(s.actionNow).toBe("Build on dips");
    expect(s.ratingPlain).toContain("Bullish");
  });

  it("surfaces executive summary at top level", () => {
    const s = deriveDecisionSummary(
      {
        portfolio_decision:
          "**Rating**: Hold\n\n**Executive Summary**: Wait for $180 before adding.",
      },
      "Hold",
      0.55,
    );
    expect(s.executiveSummary).toContain("$180");
    expect(s.actionNow).toBe("Hold; wait for a better setup");
  });
});
