import { describe, expect, it } from "vitest";
import { buildStandaloneReportHtml } from "./reportExport";

describe("buildStandaloneReportHtml", () => {
  it("inlines decision brief fields and the rendered report body", () => {
    const html = buildStandaloneReportHtml({
      ticker: "NVDA",
      rating: "Buy",
      date: "2026-05-19",
      confidencePct: 92,
      ratingPlain: "Highest conviction bullish view",
      ratingPosture: "Open or add a full position when risk limits allow",
      actionNow: "Add or open position",
      executiveSummary: "Enter on pull-back toward the 50-SMA at $15.00-$15.20.",
      levelRows: [
        ["Entry / buy zone", "15.1"],
        ["Price target", "16.8"],
        ["Stop / risk level", "14.8"],
        ["Position size", "5-7% of portfolio"],
        ["Time horizon", "3-4 weeks"],
        ["Trader action", "Buy"],
      ],
      whyNow: ["Earnings beat", "Channel checks strong"],
      invalidation: "Daily close below $850 invalidates thesis.",
      reportBodyHtml: '<h2 id="market">Market</h2><p>Sample paragraph.</p>',
      generatedAt: "2026-05-20T00:00:00.000Z",
      liveContext: {
        quote: {
          ticker: "NVDA",
          price: 13.1,
          currency: "USD",
          fetched_at: "2026-05-29T00:00:00Z",
        },
        report_close: 15.0,
        trade_date: "2026-05-19",
        levels: { entry: 15.1, stop_loss: 14.8, price_target: 16.8 },
        comparison: {
          status: "below_stop",
          guidance: "The tactical setup from this run is invalidated.",
          live_price: 13.1,
          entry: 15.1,
          stop_loss: 14.8,
          price_target: 16.8,
        },
      },
    });
    expect(html).toMatch(/^<!doctype html>/);
    expect(html).toContain("<title>NVDA — Agent report</title>");
    expect(html).toContain("Buy");
    expect(html).toContain("Highest conviction bullish view");
    expect(html).toContain("Add or open position");
    expect(html).toContain("Conviction (heuristic): 92%");
    expect(html).toContain("Enter on pull-back toward the 50-SMA");
    expect(html).toContain("Entry / buy zone");
    expect(html).toContain("5-7% of portfolio");
    expect(html).not.toContain("FINAL TRANSACTION PROPOSAL");
    expect(html).toContain("Live now");
    expect(html).toContain("invalidated");
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
      actionNow: '"hacky" & <evil>',
      levelRows: [["Bad", "<img src=x onerror=1>"]],
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

  it("omits optional blocks when missing", () => {
    const html = buildStandaloneReportHtml({
      ticker: "ZZZ",
      rating: null,
      date: null,
      confidencePct: null,
      whyNow: [],
      invalidation: null,
      reportBodyHtml: "<p>body</p>",
      generatedAt: "2026-05-20T00:00:00.000Z",
    });
    expect(html).not.toContain("As of");
    expect(html).not.toContain("Conviction (heuristic)");
    expect(html).not.toMatch(/<h2>Why now<\/h2>/);
    expect(html).not.toMatch(/<h2>Invalidation<\/h2>/);
    expect(html).not.toContain("class=\"levels\"");
  });
});
