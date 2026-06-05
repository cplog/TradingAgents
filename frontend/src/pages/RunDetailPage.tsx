import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { AppBreadcrumbs } from "../components/navigation/AppBreadcrumbs";
import { paths, runsPath, stocksPath } from "../navigation/routes";
import { useParams } from "react-router-dom";
import { PageFrame, PageHeader, Panel } from "../components/PageFrame";
import { PipelineNodeProgress } from "../components/PipelineNodeProgress";
import { ReportExportBar } from "../components/ReportExportBar";
import { DecisionBrief } from "../components/DecisionBrief";
import { ReportSections } from "../components/ReportSections";
import { EvidencePlaceholderCards } from "../components/EvidencePlaceholderCards";
import { RunProvenancePanel } from "../components/history/RunProvenancePanel";
import { DimensionsPanel } from "../components/dimensions/DimensionsPanel";
import { DimensionsRadar } from "../components/dimensions/DimensionsRadar";
import type { DimensionsCommentary, StockDimensions } from "../dimensions-types";
import type { JobResultPayload, JobStatus, RunProvenance } from "../api";
import {
  getJobDimensions,
  recomputeDimensions,
  resumeJob,
  submitAnalyze,
} from "../api";
import { useRunDetail } from "../hooks/useRunDetail";
import { useLivePlanContext } from "../hooks/useLivePlanContext";
import { useReportExport } from "../hooks/useReportExport";
import { useActiveSection } from "../hooks/useActiveSection";
import { useDocumentTitle } from "../hooks/useDocumentTitle";
import { useJobsRefresh } from "../contexts/JobsTrackerContext";
import {
  buildRerunAnalyzePayload,
  formatPriorRunLlmLabel,
  withLlmOverrides,
} from "../utils/historyRerun";
import { RerunSetupDialog } from "../components/RerunSetupDialog";
import type { LlmConfig } from "../components/LlmPicker";
import {
  REPORT_SECTION_LABELS,
  orderedReportSectionKeys,
  reportSectionDomId,
} from "../utils/reportMarkdown";

export function RunDetailPage() {
  const { jobId: routeJobId } = useParams<{ jobId: string }>();
  const runId = routeJobId?.trim() ?? "";
  const navigate = useNavigate();
  const refreshJobsRibbon = useJobsRefresh();
  const [searchParams, setSearchParams] = useSearchParams();
  const tabFromQs = searchParams.get("tab");
  const { job, historyDetail, events, notice, loading, jobActive } = useRunDetail(runId);
  const [analysisTab, setAnalysisTab] = useState<"study" | "reports">("reports");
  const [logOpen, setLogOpen] = useState(true);
  const [dimensions, setDimensions] = useState<StockDimensions | null>(null);
  const [dimensionsCommentary, setDimensionsCommentary] = useState<DimensionsCommentary | null>(null);
  const [dimensionsError, setDimensionsError] = useState<string | null>(null);
  const [dimensionsCommentaryError, setDimensionsCommentaryError] = useState<string | null>(null);
  const [recomputing, setRecomputing] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);
  const reportBodyRef = useRef<HTMLDivElement | null>(null);
  const supplementaryRef = useRef<HTMLDivElement | null>(null);
  const decisionBriefRef = useRef<HTMLDivElement | null>(null);
  const eventsLogRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (tabFromQs === "study" || tabFromQs === "reports") {
      setAnalysisTab(tabFromQs);
    }
  }, [tabFromQs]);

  const setAnalysisTabSynced = useCallback(
    (next: "study" | "reports") => {
      setAnalysisTab(next);
      const params = new URLSearchParams(searchParams);
      params.set("tab", next);
      setSearchParams(params, { replace: true });
    },
    [searchParams, setSearchParams],
  );

  const result = job?.result as JobResultPayload | null | undefined;
  const provenance: RunProvenance | null | undefined =
    job?.provenance ?? historyDetail?.provenance ?? null;
  const ticker = job?.ticker ?? historyDetail?.ticker ?? "—";
  const tradeDate = job?.date ?? historyDetail?.date ?? null;

  const reportSectionKeys = useMemo(
    () => orderedReportSectionKeys(result?.reports),
    [result?.reports],
  );

  const showAgentReports = reportSectionKeys.length > 0;
  const showDimensionalStudy = Boolean(
    job?.status === "completed" && (dimensions || dimensionsError),
  );
  const showAnalysisTabs = showDimensionalStudy && showAgentReports;

  const livePlanEnabled = job?.status === "completed" && Boolean(result?.reports);
  const {
    context: liveContext,
    loading: liveContextLoading,
    error: liveContextError,
  } = useLivePlanContext(runId, livePlanEnabled);

  const { handleExportHtml, handleExportPng, handlePrint, markdownHref, exportDisabled, decisionSummary } =
    useReportExport({
      reportBodyRef,
      supplementaryRef,
      pngTargetRef: decisionBriefRef,
      jobId: runId,
      ticker,
      rating: result?.rating ?? historyDetail?.rating ?? null,
      date: tradeDate,
      confidence: result?.confidence ?? historyDetail?.confidence ?? null,
      reports: result?.reports,
      liveContext,
      provenance: provenance ?? null,
      dimensions,
      dimensionsCommentary,
      result: result ?? null,
      canExportHtml: showAgentReports,
    });

  const tocSectionIds = useMemo(
    () => reportSectionKeys.map((k) => reportSectionDomId(k)),
    [reportSectionKeys],
  );
  const activeSectionId = useActiveSection(tocSectionIds);

  useEffect(() => {
    if (!runId || job?.status !== "completed" || !result) return;
    const r = result;
    if ("dimensions" in r || "dimensions_error" in r) {
      setDimensions(r.dimensions ?? null);
      setDimensionsCommentary(r.dimensions_commentary ?? null);
      setDimensionsError(r.dimensions_error && !r.dimensions ? r.dimensions_error : null);
      setDimensionsCommentaryError(
        r.dimensions_error && r.dimensions ? r.dimensions_error : null,
      );
      return;
    }
    let cancelled = false;
    void getJobDimensions(runId)
      .then((b) => {
        if (cancelled) return;
        setDimensions(b.dimensions);
        setDimensionsCommentary(b.commentary);
        setDimensionsError(b.error && !b.dimensions ? b.error : null);
        setDimensionsCommentaryError(b.error && b.dimensions ? b.error : null);
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        setDimensions(null);
        setDimensionsCommentary(null);
        setDimensionsError(e instanceof Error ? e.message : String(e));
      });
    return () => {
      cancelled = true;
    };
  }, [runId, job?.status, result]);

  useEffect(() => {
    if (job?.status === "queued" || job?.status === "running") {
      setDimensions(null);
      setDimensionsCommentary(null);
      setDimensionsError(null);
      setDimensionsCommentaryError(null);
    }
  }, [job?.status]);

  const [rerunOpen, setRerunOpen] = useState(false);

  const onConfirmRerun = useCallback(
    async (llm: LlmConfig) => {
      const base = historyDetail;
      if (!base) return;
      setActionLoading(true);
      try {
        const body = withLlmOverrides(buildRerunAnalyzePayload(base), llm);
        const r = await submitAnalyze(body);
        refreshJobsRibbon();
        setRerunOpen(false);
        navigate(runsPath(r.job_id));
      } finally {
        setActionLoading(false);
      }
    },
    [historyDetail, navigate],
  );

  const onResume = useCallback(async () => {
    if (!runId) return;
    setActionLoading(true);
    try {
      await resumeJob(runId);
    } finally {
      setActionLoading(false);
    }
  }, [runId]);

  const onRecomputeDimensions = useCallback(async () => {
    if (!historyDetail?.run_id && !runId) return;
    const rid = historyDetail?.run_id ?? runId;
    setRecomputing(true);
    try {
      await recomputeDimensions(rid);
      const b = await getJobDimensions(runId);
      setDimensions(b.dimensions);
      setDimensionsCommentary(b.commentary);
    } catch (e: unknown) {
      setDimensionsError(e instanceof Error ? e.message : String(e));
    } finally {
      setRecomputing(false);
    }
  }, [historyDetail?.run_id, runId]);

  const statusLabel = job?.status ? job.status.toLowerCase() : "loading";
  const titleParts = [ticker !== "—" ? ticker : null, statusLabel, `Run ${runId.slice(0, 6)}`]
    .filter(Boolean)
    .join(" · ");
  useDocumentTitle(titleParts || "Run");

  if (!runId) {
    return (
      <PageFrame>
        <p>Missing run id.</p>
      </PageFrame>
    );
  }

  return (
    <PageFrame className="run-detail-page">
      <PageHeader
        title={ticker}
        description="Run-level report — one analysis job, full agent output and dimensions."
        meta={
          <>
            <AppBreadcrumbs
              items={[
                { label: "Analysis", to: paths.dashboard },
                { label: "Runs", to: paths.history },
                { label: ticker, to: stocksPath(ticker) },
                { label: `Run ${runId.slice(0, 8)}…` },
              ]}
            />
          </>
        }
      />

      {notice && <p className="notice notice--warn">{notice}</p>}
      {loading && !job?.result && <p className="ui-muted">Loading run…</p>}

      {(historyDetail && job?.status === "completed") || (job?.resumable && job.status === "failed") ? (
        <div className="run-detail-page__actions">
          {historyDetail && job?.status === "completed" && (
            <button
              type="button"
              className="ui-btn-secondary"
              disabled={actionLoading}
              onClick={() => setRerunOpen(true)}
            >
              Re-run…
            </button>
          )}
          {job?.resumable && job.status === "failed" && (
            <button type="button" className="ui-btn-danger" disabled={actionLoading} onClick={() => void onResume()}>
              Resume failed job
            </button>
          )}
        </div>
      ) : null}

      {jobActive && <PipelineNodeProgress job={job} events={events} />}

      {jobActive && (
        <Panel className="panel--terminal" title="Progress log">
          <button type="button" className="dashboard-log-toggle" onClick={() => setLogOpen(!logOpen)}>
            {logOpen ? "Collapse" : "Expand"} stream
          </button>
          {logOpen && (
            <pre className="mono dashboard-progress-log dashboard-progress-log--open">
              <div ref={eventsLogRef}>
                {events.map((e, i) => (
                  <div key={`${e.ts}-${i}`} className="dashboard-progress-log__entry">
                    <span style={{ color: "#94a3b8" }}>[{e.stage}]</span> {e.message}
                  </div>
                ))}
              </div>
            </pre>
          )}
        </Panel>
      )}

      {job?.status === "completed" && (
        <section className="run-detail-page__results">
          <header className="run-detail-page__hero">
            <div ref={decisionBriefRef}>
              <DecisionBrief
                rating={result?.rating ?? historyDetail?.rating ?? null}
                confidencePct={decisionSummary.confidencePct}
                summary={decisionSummary}
                reports={result?.reports}
                liveContext={liveContext}
                liveContextLoading={liveContextLoading}
                liveContextError={liveContextError}
                tradeDate={tradeDate}
                calibration={
                  result?.confidence_inputs || result?.confidence_breakdown
                    ? {
                        rawTierPct:
                          result?.confidence_raw_tier != null
                            ? Math.round(result.confidence_raw_tier * 100)
                            : null,
                        breakdown: result?.confidence_breakdown ?? null,
                        inputs: result?.confidence_inputs ?? null,
                      }
                    : null
                }
              />
            </div>
            <div className="run-detail-page__meta">
              <span className="mono">{ticker}</span>
              {tradeDate && <span>As of {tradeDate}</span>}
            </div>
            <RunProvenancePanel provenance={provenance} />
          </header>

          {showAgentReports && (
            <ReportExportBar
              sticky
              onExportHtml={handleExportHtml}
              onExportPng={handleExportPng}
              onPrint={handlePrint}
              markdownHref={markdownHref}
              disabled={exportDisabled}
            />
          )}

          {dimensions && (
            <div className="dashboard-dimensions-hero">
              <DimensionsRadar factorScores={dimensions.factor_scores} height={180} />
            </div>
          )}

          {showAnalysisTabs && (
            <div className="dashboard-analysis-tabs" role="tablist">
              <button
                type="button"
                role="tab"
                aria-selected={analysisTab === "study"}
                className={`dashboard-analysis-tab${analysisTab === "study" ? " dashboard-analysis-tab--active" : ""}`}
                onClick={() => setAnalysisTabSynced("study")}
              >
                Dimensional study
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={analysisTab === "reports"}
                className={`dashboard-analysis-tab${analysisTab === "reports" ? " dashboard-analysis-tab--active" : ""}`}
                onClick={() => setAnalysisTabSynced("reports")}
              >
                Agent reports
              </button>
            </div>
          )}

          {showDimensionalStudy && (!showAnalysisTabs || analysisTab === "study") && (
            <Panel className="panel--elevated">
              <DimensionsPanel
                dimensions={dimensions}
                commentary={dimensionsCommentary}
                error={dimensionsError}
                commentaryError={dimensionsCommentaryError}
              />
              {!dimensions && (
                <button type="button" className="ui-btn-primary" disabled={recomputing} onClick={() => void onRecomputeDimensions()}>
                  {recomputing ? "Recomputing…" : "Recompute dimensions"}
                </button>
              )}
            </Panel>
          )}

          {showAgentReports && (!showAnalysisTabs || analysisTab === "reports") && (
            <Panel className="panel--elevated dashboard-report-panel">
              <div
                className={
                  reportSectionKeys.length > 1
                    ? "dashboard-report-layout dashboard-report-layout--with-toc"
                    : "dashboard-report-layout"
                }
              >
                {reportSectionKeys.length > 1 && (
                  <nav className="dashboard-report-toc" aria-label="Report sections">
                    <ul>
                      {reportSectionKeys.map((key) => {
                        const id = reportSectionDomId(key);
                        const label = REPORT_SECTION_LABELS[key] ?? key.replace(/_/g, " ");
                        return (
                          <li key={key}>
                            <a
                              href={`#${id}`}
                              className={
                                "dashboard-report-toc__link" +
                                (id === activeSectionId ? " dashboard-report-toc__link--active" : "")
                              }
                            >
                              {label}
                            </a>
                          </li>
                        );
                      })}
                    </ul>
                  </nav>
                )}
                <div className="dashboard-report-body">
                  <div ref={supplementaryRef}>
                    <EvidencePlaceholderCards result={result ?? null} />
                  </div>
                  <ReportSections reports={result?.reports} reportBodyRef={reportBodyRef} />
                </div>
              </div>
            </Panel>
          )}
        </section>
      )}

      {job?.error && (
        <div className="panel panel--error" role="alert">
          {job.error}
        </div>
      )}

      {historyDetail && (
        <RerunSetupDialog
          open={rerunOpen}
          title="Re-run analysis"
          description="Choose LLM provider and models. Ticker, date, and analysts stay the same as this run."
          runSummary={`${ticker}${tradeDate ? ` · ${tradeDate}` : ""}`}
          priorRunLlm={formatPriorRunLlmLabel(
            historyDetail.config_snapshot,
            historyDetail.provenance ?? provenance,
          )}
          configSnapshot={historyDetail.config_snapshot ?? null}
          submitting={actionLoading}
          onClose={() => {
            if (!actionLoading) setRerunOpen(false);
          }}
          onConfirm={onConfirmRerun}
        />
      )}
    </PageFrame>
  );
}
