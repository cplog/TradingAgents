import { describe, expect, it } from "vitest";
import { derivePlanLevels, deriveTradingPlan, parseMdField } from "./tradingPlan";

describe("parseMdField", () => {
  it("strips FINAL TRANSACTION PROPOSAL trailer from position sizing", () => {
    const trader = [
      "**Action**: Buy",
      "",
      "**Position Sizing**: 5-7% of portfolio",
      "",
      "FINAL TRANSACTION PROPOSAL: **BUY**",
    ].join("\n");
    expect(parseMdField(trader, "Position Sizing")).toBe("5-7% of portfolio");
  });

  it("does not include trailer when sizing and proposal are on one line", () => {
    const text = "**Position Sizing**: 5-7% of portfolio FINAL TRANSACTION PROPOSAL: BUY";
    expect(parseMdField(text, "Position Sizing")).toBe("5-7% of portfolio");
  });
});

describe("deriveTradingPlan", () => {
  it("parses trader and PM fields without trailer pollution", () => {
    const reports = {
      trader_plan: [
        "**Action**: Buy",
        "**Entry Price**: 15.1",
        "**Stop Loss**: 14.8",
        "**Position Sizing**: 5-7% of portfolio",
        "",
        "FINAL TRANSACTION PROPOSAL: **BUY**",
      ].join("\n"),
      portfolio_decision: [
        "**Executive Summary**: Enter on pull-back toward 50-SMA.",
        "**Price Target**: 16.8",
        "**Time Horizon**: 3-4 weeks",
      ].join("\n"),
    };
    const plan = deriveTradingPlan(reports);
    expect(plan.positionSizing).toBe("5-7% of portfolio");
    expect(plan.traderAction).toBe("Buy");
    expect(plan.entry).toBe("15.1");
    expect(plan.stopLoss).toBe("14.8");
    expect(plan.priceTarget).toBe("16.8");
    expect(plan.timeHorizon).toBe("3-4 weeks");
  });

  it("fills levels from narrative when labeled fields are absent", () => {
    const reports = {
      portfolio_decision:
        "**Executive Summary**: Add near $12.20 with stop below $11.40 and price target $14.50.",
    };
    const levels = derivePlanLevels(reports, 12.57);
    expect(levels.entry).toBe(12.2);
    expect(levels.stop_loss).toBe(11.4);
    expect(levels.price_target).toBe(14.5);
    const plan = deriveTradingPlan(reports);
    expect(plan.entry).toBe("12.2");
    expect(plan.stopLoss).toBe("11.4");
    expect(plan.priceTarget).toBe("14.5");
  });
});
