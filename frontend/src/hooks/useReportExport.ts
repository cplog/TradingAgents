import { useCallback, useMemo, type RefObject } from "react";
import { deriveDecisionSummary } from "../utils/decisionSummary";
import { buildStandaloneReportHtml, downloadStandaloneReport } from "../utils/reportExport";

export type UseReportExportOptions = {
  reportBodyRef: RefObject<HTMLDivElement | null>;
  jobId?: string | null;
  ticker: string;
  rating?: string | null;
  date?: string | null;
  confidence?: number | null;
  reports?: Record<string, string>;
  /** When false, HTML export is disabled (e.g. no report body rendered yet). */
  canExportHtml?: boolean;
};

export function useReportExport({
  reportBodyRef,
  jobId,
  ticker,
  rating,
  date,
  confidence,
  reports,
  canExportHtml = true,
}: UseReportExportOptions) {
  const decisionSummary = useMemo(
    () => deriveDecisionSummary(reports, rating, confidence),
    [reports, rating, confidence],
  );

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
      decisionRows: [
        ["What to do now", decisionSummary.actionNow],
        [
          "Conviction",
          decisionSummary.confidencePct != null
            ? `${decisionSummary.confidencePct}% · ${decisionSummary.confidenceLabel}`
            : decisionSummary.confidenceLabel,
        ],
        ["FOMO risk", decisionSummary.fomoLabel],
        ["Time horizon", decisionSummary.horizon],
      ],
      whyNow: decisionSummary.whyNow,
      invalidation: decisionSummary.invalidation,
      reportBodyHtml: body.innerHTML,
    });
    downloadStandaloneReport(`agent-report-${tickerSlug}-${dateSlug}.html`, html);
  }, [reportBodyRef, canExportHtml, ticker, date, rating, decisionSummary]);

  const handlePrint = useCallback(() => {
    if (typeof window !== "undefined") window.print();
  }, []);

  return {
    decisionSummary,
    markdownHref,
    handleExportHtml,
    handlePrint,
    exportDisabled: !canExportHtml,
  };
}
