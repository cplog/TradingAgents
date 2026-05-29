import { describe, expect, it } from "vitest";
import {
  isSectionPlaceholder,
  normalizeReportWhitespace,
  sanitizeReportSectionBody,
  stripLeadingFinalTransactionProposal,
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
});
