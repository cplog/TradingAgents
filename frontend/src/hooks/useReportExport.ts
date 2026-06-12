import { useCallback, useMemo, type RefObject } from "react";
import type { JobResultPayload, RunProvenance } from "../api";
import type { DimensionsCommentary, StockDimensions } from "../dimensions-types";
import { deriveDecisionSummary } from "../utils/decisionSummary";
import { deriveTradingPlan, tradingPlanRows } from "../utils/tradingPlan";
import type { JobLiveContext } from "../utils/livePlanContext";
import { orderedReportSectionKeys, buildSanitizedReportMarkdown } from "../utils/reportMarkdown";
import { reportSectionsFromKeys } from "../utils/reportExportBlocks";
import {
  buildStandaloneReportHtml,
  downloadStandaloneReport,
  downloadPng,
  printStandaloneReport,
} from "../utils/reportExport";

export type UseReportExportOptions = {
  reportBodyRef: RefObject<HTMLDivElement | null>;
  /** Visual evidence cards (OHLCV / Kronos) rendered above agent reports. */
  supplementaryRef?: RefObject<HTMLElement | null>;
  pngTargetRef?: RefObject<HTMLElement | null>;
  ticker: string;
  rating?: string | null;
  date?: string | null;
  confidence?: number | null;
  reports?: Record<string, string>;
  liveContext?: JobLiveContext | null;
  provenance?: RunProvenance | null;
  dimensions?: StockDimensions | null;
  dimensionsCommentary?: DimensionsCommentary | null;
  result?: JobResultPayload | null;
  canExportHtml?: boolean;
};

export function useReportExport({
  reportBodyRef,
  supplementaryRef,
  pngTargetRef,
  ticker,
  rating,
  date,
  confidence,
  reports,
  liveContext,
  provenance = null,
  dimensions = null,
  dimensionsCommentary = null,
  result = null,
  canExportHtml = true,
}: UseReportExportOptions) {
  const decisionSummary = useMemo(
    () => deriveDecisionSummary(reports, rating, confidence, liveContext),
    [reports, rating, confidence, liveContext],
  );

  const levelRows = useMemo(() => {
    const plan = deriveTradingPlan(reports);
    return tradingPlanRows(plan).map((r) => [r.label, r.value] as const);
  }, [reports]);

  const reportSections = useMemo(
    () => reportSectionsFromKeys(orderedReportSectionKeys(reports)),
    [reports],
  );

  const confidenceDetail = useMemo(() => {
    if (!result?.confidence_inputs && result?.confidence_raw_tier == null) return null;
    return {
      rawTierPct:
        result?.confidence_raw_tier != null ? Math.round(result.confidence_raw_tier * 100) : null,
      breakdown: result?.confidence_breakdown ?? null,
      supporting: result?.confidence_inputs?.supporting_factors ?? [],
      conflicting: result?.confidence_inputs?.conflicting_factors ?? [],
      weakData: result?.confidence_inputs?.weak_data ?? [],
      peerScope: result?.confidence_inputs?.peer_scope ?? null,
    };
  }, [result]);

  const exportBasename = useCallback(() => {
    const tickerSlug =
      ticker
        .toString()
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, "-")
        .replace(/^-+|-+$/g, "") || "report";
    const dateSlug = (date ?? new Date().toISOString().slice(0, 10)).replace(/[^0-9-]/g, "");
    return `agent-report-${tickerSlug}-${dateSlug}`;
  }, [ticker, date]);

  const handleExportMarkdown = useCallback(() => {
    if (!reports || !canExportHtml) return;
    const md = buildSanitizedReportMarkdown(reports, {
      ticker,
      date: date ?? null,
      rating: rating ?? null,
    });
    if (!md.trim()) return;
    const blob = new Blob([md], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${exportBasename()}.md`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }, [reports, canExportHtml, ticker, date, rating, exportBasename]);

  const buildExportHtml = useCallback((): string | null => {
    const body = reportBodyRef.current;
    if (!body || !canExportHtml) return null;
    const supplementaryHtml = supplementaryRef?.current?.innerHTML ?? "";
    return buildStandaloneReportHtml({
      ticker,
      rating: rating ?? null,
      date: date ?? null,
      confidencePct: decisionSummary.confidencePct,
      ratingPlain: decisionSummary.ratingPlain,
      ratingPosture: decisionSummary.ratingPosture,
      actionNow: decisionSummary.actionNow,
      executiveSummary: decisionSummary.executiveSummary,
      livePracticalNote: decisionSummary.livePracticalNote,
      levelRows,
      liveContext: liveContext ?? null,
      whyNow: decisionSummary.whyNow,
      invalidation: decisionSummary.invalidation,
      reportBodyHtml: body.innerHTML,
      supplementaryHtml,
      reportSections,
      provenance,
      dimensions,
      dimensionsCommentary,
      analystCoverage: result?.analyst_coverage ?? null,
      confidenceDetail,
    });
  }, [
    reportBodyRef,
    supplementaryRef,
    canExportHtml,
    ticker,
    date,
    rating,
    decisionSummary,
    levelRows,
    liveContext,
    reportSections,
    provenance,
    dimensions,
    dimensionsCommentary,
    result,
    confidenceDetail,
  ]);

  const handleExportHtml = useCallback(() => {
    const html = buildExportHtml();
    if (!html) return;
    downloadStandaloneReport(`${exportBasename()}.html`, html);
  }, [buildExportHtml, exportBasename]);

  const handleExportPng = useCallback(async () => {
    const node = pngTargetRef?.current;
    if (!node) return;
    try {
      const { toPng } = await import("html-to-image");
      const dataUrl = await toPng(node, {
        pixelRatio: 2,
        cacheBust: true,
        backgroundColor: "#fffbf3",
      });
      const tickerSlug =
        ticker
          .toString()
          .toLowerCase()
          .replace(/[^a-z0-9]+/g, "-")
          .replace(/^-+|-+$/g, "") || "report";
      const dateSlug = (date ?? new Date().toISOString().slice(0, 10)).replace(/[^0-9-]/g, "");
      downloadPng(`agent-report-${tickerSlug}-${dateSlug}.png`, dataUrl);
    } catch (err) {
      console.error("PNG export failed:", err);
    }
  }, [pngTargetRef, ticker, date]);

  const handlePrint = useCallback(() => {
    const html = buildExportHtml();
    if (!html) return;
    printStandaloneReport(html);
  }, [buildExportHtml]);

  return {
    decisionSummary,
    handleExportHtml,
    handleExportPng,
    handleExportMarkdown,
    handlePrint,
    exportDisabled: !canExportHtml,
  };
}
