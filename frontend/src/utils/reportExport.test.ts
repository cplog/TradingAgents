import { describe, expect, it, vi } from "vitest";
import { buildStandaloneReportHtml, printStandaloneReport } from "./reportExport";

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
    expect(html).toContain("<title>NVDA Agent report</title>");
    expect(html).toContain("Buy");
    expect(html).toContain("Highest conviction bullish view");
    expect(html).toContain("Add or open position");
    expect(html).toContain("Calibrated conviction: <strong>92%</strong>");
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
    expect(html).toContain("export-page");
    expect(html).toContain("Jump to section");
  });

  it("includes dimensions, provenance, and section nav from structured input", () => {
    const html = buildStandaloneReportHtml({
      ticker: "MNSO",
      rating: "Underweight",
      date: "2026-06-04",
      confidencePct: 55,
      whyNow: [],
      invalidation: null,
      reportBodyHtml:
        '<section id="report-section-market" class="report-section"><h2 class="report-section__title">Market</h2><p>Body</p></section>',
      reportSections: [{ id: "report-section-market", label: "Market" }],
      provenance: {
        llm_provider: "deepseek",
        llm_deep: "deepseek-v4-pro",
        llm_quick: "deepseek-v4-flash",
        data_routing: "yfinance, finnhub",
        analysts_selected: ["market", "policy"],
        analysts_ok: 2,
        analysts_total: 2,
        source_pillars: 3,
        vendor_count: 2,
      },
      dimensions: {
        ticker: "MNSO",
        as_of_date: "2026-06-04",
        dimensions_version: "1",
        peer_scope: "local",
        source: "full_run",
        data_quality_flags: [],
        facts: { as_of_date: "2026-06-04", currency: "USD" },
        pillar_scores: {
          market: {
            trend: { score: 40, rationale: "" },
            momentum: { score: 35, rationale: "" },
            volatility_risk: { score: 50, rationale: "" },
            setup_quality: { score: 45, rationale: "" },
          },
          sentiment: {
            retail_sentiment: { score: 50, rationale: "" },
            social_buzz: { score: 50, rationale: "" },
            consensus_quality: { score: 50, rationale: "" },
            narrative_strength: { score: 50, rationale: "" },
          },
          news: {
            catalyst_strength: { score: 50, rationale: "" },
            macro_alignment: { score: 50, rationale: "" },
            headline_quality: { score: 50, rationale: "" },
            surprise_risk: { score: 50, rationale: "" },
          },
          fundamentals: {
            valuation: { score: 70, rationale: "" },
            growth: { score: 65, rationale: "" },
            profitability: { score: 55, rationale: "" },
            balance_sheet_strength: { score: 60, rationale: "" },
          },
        },
        factor_scores: {
          value: { score: 72, inputs: {} },
          growth: { score: 68, inputs: {} },
          quality: { score: 54, inputs: {} },
          momentum: { score: 25, inputs: {} },
          low_risk: { score: 25, inputs: {} },
          sentiment: { score: 35, inputs: {} },
        },
      },
      analystCoverage: {
        market: { status: "ok", chars: 1200 },
        policy: { status: "ok", chars: 800 },
      },
    });
    expect(html).toContain('id="dimensional-study"');
    expect(html).toContain('id="provenance"');
    expect(html).toContain('id="analyst-coverage"');
    expect(html).toContain('href="#report-section-market"');
    expect(html).toContain("Market</a>");
  });

  it("avoids side-accent borders and em dash copy in exported report chrome", () => {
    const html = buildStandaloneReportHtml({
      ticker: "NVDA",
      rating: "Buy",
      date: "2026-05-19",
      confidencePct: 92,
      whyNow: [],
      invalidation: null,
      reportBodyHtml:
        '<section id="report-section-market" class="report-section"><h2 class="report-section__title">Market</h2><blockquote>Quoted context.</blockquote></section>',
      reportSections: [{ id: "report-section-market", label: "Market" }],
      generatedAt: "2026-05-20T00:00:00.000Z",
    });

    const sideAccent = ["border", "left"].join("-");
    expect(html).not.toContain(`${sideAccent}: 4px solid var(--accent)`);
    expect(html).not.toContain(`${sideAccent}: 3px solid var(--accent)`);
    expect(html).not.toContain(`\u2014 Agent report`);
    expect(html).not.toContain(`Save as PDF there \u2014`);
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

  it("printStandaloneReport opens blob URL in a new window", () => {
    const open = vi.fn(() => ({
      addEventListener: vi.fn(),
      focus: vi.fn(),
      print: vi.fn(),
      close: vi.fn(),
      onafterprint: null,
    }));
    const createObjectURL = vi.fn(() => "blob:test");
    const revokeObjectURL = vi.fn();
    vi.stubGlobal("open", open);
    vi.stubGlobal("URL", {
      createObjectURL,
      revokeObjectURL,
    });

    printStandaloneReport("<!doctype html><html><body>ok</body></html>");

    expect(open).toHaveBeenCalledWith("blob:test", "_blank", "noopener,noreferrer");
    expect(createObjectURL).toHaveBeenCalled();
  });

  it("renders calibrated conviction, live strip, and factor inputs like the run UI", () => {
    const html = buildStandaloneReportHtml({
      ticker: "NET",
      rating: "Underweight",
      date: "2026-06-05",
      confidencePct: 0,
      ratingPlain: "Cautious; lean bearish",
      ratingPosture: "Trim exposure or avoid new buys",
      actionNow: "Trim or avoid new buys",
      livePracticalNote:
        "Live price (268.64) is above the planned entry (227.50). Wait for a pull-back into the entry zone or a confirmed breakout per the plan.",
      whyNow: [],
      invalidation: null,
      reportBodyHtml: "<p>body</p>",
      generatedAt: "2026-06-05T12:00:00.000Z",
      liveContext: {
        quote: { ticker: "NET", price: 268.64, currency: "USD", fetched_at: "2026-06-05T12:00:00Z" },
        run_time_quote: { price: 268.64, currency: "USD" },
        trade_date: "2026-06-05",
        levels: { entry: 227.5, stop_loss: 208, price_target: 295 },
        comparison: {
          status: "above_entry",
          guidance:
            "Live price (268.64) is above the planned entry (227.50). Wait for a pull-back into the entry zone or a confirmed breakout per the plan.",
          live_price: 268.64,
          entry: 227.5,
          stop_loss: 208,
          price_target: 295,
        },
        historical_rating_note:
          "Analysis used live quote 268.64 at run time. Rating is unchanged; guidance compares today's price to this run's levels.",
      },
      confidenceDetail: {
        rawTierPct: 35,
        breakdown: {
          tier: 0.35,
          coherence_penalty: 0.24,
          data_quality_penalty: 0.2,
          peer_penalty: 0.1,
        },
        supporting: [
          { key: "value", score: 0 },
          { key: "quality", score: 25 },
          { key: "low_risk", score: 25 },
        ],
        conflicting: [
          { key: "growth", score: 100 },
          { key: "momentum", score: 75 },
          { key: "sentiment", score: 60 },
        ],
        weakData: [
          "missing_pe_ttm",
          "missing_eps_growth_yoy",
          "peer_percentiles_cache_miss",
          "peer_percentiles_unavailable",
        ],
        peerScope: "unavailable",
      },
    });

    expect(html).toContain("Above entry");
    expect(html).toContain("At run time");
    expect(html).toContain("Report as of");
    expect(html).toContain("Calibrated conviction: <strong>0%</strong>");
    expect(html).toContain("rating tier alone 35%");
    expect(html).toContain("Supports the call");
    expect(html).toContain("Conflicts with the call");
    expect(html).toContain("Data caveats");
    expect(html).toContain("Missing P/E TTM");
    expect(html).toContain("No peer scope");
    expect(html).toContain("Live check");
    expect(html).toContain("Analysis used live quote 268.64 at run time");
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
    expect(html).not.toContain("Calibrated conviction");
    expect(html).not.toMatch(/<h2>Why now<\/h2>/);
    expect(html).not.toMatch(/<h2>Invalidation<\/h2>/);
    expect(html).not.toContain("class=\"levels\"");
  });
});
