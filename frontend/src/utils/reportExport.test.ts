import { describe, expect, it } from "vitest";
import { buildStandaloneReportHtml } from "./reportExport";

describe("buildStandaloneReportHtml", () => {
  it("inlines the rendered report body and decision summary into one document", () => {
    const html = buildStandaloneReportHtml({
      ticker: "NVDA",
      rating: "Strong Buy",
      date: "2026-05-19",
      confidencePct: 78,
      decisionRows: [
        ["What to do now", "Buy now"],
        ["Conviction", "78% · High conviction"],
        ["FOMO risk", "Low"],
        ["Time horizon", "3–6 months"],
      ],
      whyNow: ["Earnings beat", "Channel checks strong"],
      invalidation: "Daily close below $850 invalidates thesis.",
      reportBodyHtml: '<h2 id="market">Market</h2><p>Sample paragraph.</p>',
      generatedAt: "2026-05-20T00:00:00.000Z",
    });
    expect(html.startsWith("<!doctype html>")).toBe(true);
    expect(html).toContain("<title>NVDA — Agent report</title>");
    expect(html).toContain("Strong Buy");
    expect(html).toContain("2026-05-19");
    expect(html).toContain("Confidence (heuristic): 78%");
    expect(html).toContain("Buy now");
    expect(html).toContain("Earnings beat");
    expect(html).toContain("Daily close below $850 invalidates thesis.");
    expect(html).toContain('<h2 id="market">Market</h2>');
    expect(html).toContain("@media print");
  });

  it("escapes HTML in user-controlled fields but preserves report-body markup", () => {
    const html = buildStandaloneReportHtml({
      ticker: "AAA",
      rating: "<script>alert(1)</script>",
      date: null,
      confidencePct: null,
      decisionRows: [["Bad", '"hacky" & <evil>']],
      whyNow: ["<img src=x onerror=1>"],
      invalidation: null,
      reportBodyHtml: "<p><strong>kept</strong></p>",
      generatedAt: "2026-05-20T00:00:00.000Z",
    });
    expect(html).not.toContain("<script>alert(1)</script>");
    expect(html).toContain("&lt;script&gt;alert(1)&lt;/script&gt;");
    expect(html).toContain("&quot;hacky&quot; &amp; &lt;evil&gt;");
    expect(html).toContain("&lt;img src=x onerror=1&gt;");
    expect(html).toContain("<p><strong>kept</strong></p>");
  });

  it("omits confidence and date when missing, omits invalidation section when null", () => {
    const html = buildStandaloneReportHtml({
      ticker: "ZZZ",
      rating: null,
      date: null,
      confidencePct: null,
      decisionRows: [["What to do now", "Watchlist"]],
      whyNow: [],
      invalidation: null,
      reportBodyHtml: "<p>body</p>",
      generatedAt: "2026-05-20T00:00:00.000Z",
    });
    expect(html).not.toContain("As of");
    expect(html).not.toContain("Confidence");
    expect(html).not.toMatch(/<h2>Invalidation<\/h2>/);
    expect(html).toContain("No concise reason lines found");
  });
});
