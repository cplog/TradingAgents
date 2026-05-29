import { useCallback, useMemo, type RefObject } from "react";
import { toPng } from "html-to-image";
import { deriveDecisionSummary } from "../utils/decisionSummary";
import { deriveTradingPlan, tradingPlanRows } from "../utils/tradingPlan";
import type { JobLiveContext } from "../utils/livePlanContext";
import { buildStandaloneReportHtml, downloadStandaloneReport, downloadPng } from "../utils/reportExport";

export type UseReportExportOptions = {
  reportBodyRef: RefObject<HTMLDivElement | null>;
  /** Ref to the element captured for PNG export (e.g. decision brief card). */
  pngTargetRef?: RefObject<HTMLElement | null>;
  jobId?: string | null;
  ticker: string;
  rating?: string | null;
  date?: string | null;
  confidence?: number | null;
  reports?: Record<string, string>;
  liveContext?: JobLiveContext | null;
  /** When false, HTML export is disabled (e.g. no report body rendered yet). */
  canExportHtml?: boolean;
};

export function useReportExport({
  reportBodyRef,
  pngTargetRef,
  jobId,
  ticker,
  rating,
  date,
  confidence,
  reports,
  liveContext,
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

  const markdownHref = jobId?.trim() ? `/jobs/${encodeURIComponent(jobId.trim())}/report` : null;

  const handleExportHtml = useCallback(() => {
    const body = reportBodyRef.current;
    if (!body || !canExportHtml) return;
    const tickerSlug =
      ticker
        .toString()
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, "-")
        .replace(/^-+|-+$/g, "") || "report";
    const dateSlug = (date ?? new Date().toISOString().slice(0, 10)).replace(/[^0-9-]/g, "");
    const html = buildStandaloneReportHtml({
      ticker,
      rating: rating ?? null,
      date: date ?? null,
      confidencePct: decisionSummary.confidencePct,
      ratingPlain: decisionSummary.ratingPlain,
      ratingPosture: decisionSummary.ratingPosture,
      actionNow: decisionSummary.actionNow,
      executiveSummary: decisionSummary.executiveSummary,
      levelRows,
      liveContext: liveContext ?? null,
      whyNow: decisionSummary.whyNow,
      invalidation: decisionSummary.invalidation,
      reportBodyHtml: body.innerHTML,
    });
    downloadStandaloneReport(`agent-report-${tickerSlug}-${dateSlug}.html`, html);
  }, [reportBodyRef, canExportHtml, ticker, date, rating, decisionSummary, levelRows, liveContext]);

  const handleExportPng = useCallback(async () => {
    const node = pngTargetRef?.current;
    if (!node) return;
    const dataUrl = await toPng(node, {
      pixelRatio: 2,
      cacheBust: true,
      backgroundColor: "#ffffff",
    });
    const tickerSlug =
      ticker
        .toString()
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, "-")
        .replace(/^-+|-+$/g, "") || "report";
    const dateSlug = (date ?? new Date().toISOString().slice(0, 10)).replace(/[^0-9-]/g, "");
    downloadPng(`agent-report-${tickerSlug}-${dateSlug}.png`, dataUrl);
  }, [pngTargetRef, ticker, date]);

  const handlePrint = useCallback(() => {
    if (typeof window !== "undefined") window.print();
  }, []);

  return {
    decisionSummary,
    markdownHref,
    handleExportHtml,
    handleExportPng,
    handlePrint,
    exportDisabled: !canExportHtml,
  };
}
