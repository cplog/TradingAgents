import { describe, expect, it } from "vitest";
import {
  isSectionPlaceholder,
  normalizeReportWhitespace,
  sanitizeReportSectionBody,
  stripLeadingFinalTransactionProposal,
  buildSanitizedReportMarkdown,
} from "./reportMarkdown";

describe("reportMarkdown", () => {
  it("normalizes unicode spaces", () => {
    expect(normalizeReportWhitespace("May\u202f16\u202f–\u202f23")).toBe("May 16 – 23");
  });

  it("strips leading FINAL TRANSACTION PROPOSAL from analyst sections", () => {
    const raw =
      "**FINAL TRANSACTION PROPOSAL:\u00a0HOLD**  \n\n---\n\n## Signal\n\nBody text.";
    expect(stripLeadingFinalTransactionProposal(raw)).toBe("## Signal\n\nBody text.");
  });

  it("keeps proposal in trader section when not at start-only strip", () => {
    const raw = "**Action**: Hold\n\nFINAL TRANSACTION PROPOSAL: **HOLD**";
    expect(sanitizeReportSectionBody("trader_plan", raw)).toContain("FINAL TRANSACTION PROPOSAL");
  });

  it("removes internal report field lines", () => {
    const raw = "Visible text.\n\n_Internal report field:_ `kronos_report`";
    expect(sanitizeReportSectionBody("kronos", raw)).toBe("Visible text.");
  });

  it("detects empty Kronos stub as placeholder", () => {
    const raw =
      "**Status:** empty — no report text was captured for the **Kronos** analyst.";
    expect(isSectionPlaceholder("kronos", raw)).toBe(true);
  });

  it("buildSanitizedReportMarkdown omits stubs and internal fields", () => {
    const md = buildSanitizedReportMarkdown(
      {
        market: "**FINAL TRANSACTION PROPOSAL: HOLD**\n\n## Signal\n\nTrend up.",
        kronos: "**Status:** empty — no report text was captured for the **Kronos** analyst.",
        fundamentals: "Revenue +20%.\n\n_Internal report field:_ `foo`",
      },
      { ticker: "SOFI", date: "2026-06-07", rating: "Overweight" },
    );
    expect(md).toContain("# SOFI agent report");
    expect(md).toContain("**Rating:** Overweight");
    expect(md).toContain("## Signal");
    expect(md).toContain("Trend up.");
    expect(md).toContain("## Fundamentals");
    expect(md).not.toContain("FINAL TRANSACTION PROPOSAL");
    expect(md).not.toContain("_Internal report field");
    expect(md).not.toContain("Kronos");
  });
});
