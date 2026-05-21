import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { AppBreadcrumbs } from "../components/navigation/AppBreadcrumbs";
import { paths, runsPath, stocksPath } from "../navigation/routes";
import { useParams } from "react-router-dom";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Components } from "react-markdown";
import { PageFrame, PageHeader, Panel } from "../components/PageFrame";
import { PipelineNodeProgress } from "../components/PipelineNodeProgress";
import { ReportExportBar } from "../components/ReportExportBar";
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
import { useReportExport } from "../hooks/useReportExport";
import { useActiveSection } from "../hooks/useActiveSection";
import { buildRerunAnalyzePayload } from "../utils/historyRerun";
import { orderedReportSectionKeys, prepareReportMarkdown } from "../utils/reportMarkdown";

function slugifyHeading(text: string): string {
  return text
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9\u00C0-\u024f]+/gi, "-")
    .replace(/^-+|-+$/g, "");
}

function textFromChildren(node: ReactNode): string {
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(textFromChildren).join("");
  if (node && typeof node === "object" && "props" in node) {
    const p = (node as { props?: { children?: ReactNode } }).props;
    if (p?.children !== undefined) return textFromChildren(p.children);
  }
  return "";
}

function extractToc(md: string): { level: 2 | 3; text: string; id: string }[] {
  const out: { level: 2 | 3; text: string; id: string }[] = [];
  const seen = new Map<string, number>();
  for (const line of md.split("\n")) {
    const m = /^(#{2,3})\s+(.+)$/.exec(line.trim());
    if (!m) continue;
    const level = m[1].length as 2 | 3;
    const raw = m[2].trim();
    let id = slugifyHeading(raw);
    const n = seen.get(id) ?? 0;
    seen.set(id, n + 1);
    if (n > 0) id = `${id}-${n}`;
    out.push({ level, text: raw, id });
  }
  return out;
}

function pct(conf: number | null | undefined): string {
  if (conf == null || !Number.isFinite(conf)) return "—";
  return `${Math.round(conf * 100)}%`;
}

export function RunDetailPage() {
  const { jobId: routeJobId } = useParams<{ jobId: string }>();
  const runId = routeJobId?.trim() ?? "";
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
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
  const eventsLogRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (tabFromQs === "study" || tabFromQs === "reports") {
      setAnalysisTab(tabFromQs);
    }
  }, [tabFromQs]);

  const result = job?.result as JobResultPayload | null | undefined;
  const provenance: RunProvenance | null | undefined =
    job?.provenance ?? historyDetail?.provenance ?? null;
  const ticker = job?.ticker ?? historyDetail?.ticker ?? "—";
  const tradeDate = job?.date ?? historyDetail?.date ?? null;

  const mdReport = useMemo(() => {
    const reps = result?.reports;
    if (!reps || typeof reps !== "object") return "";
    const keys = orderedReportSectionKeys(reps);
    return keys
      .map((k) => prepareReportMarkdown(k, reps[k] ?? ""))
      .filter(Boolean)
      .join("\n\n---\n\n");
  }, [result?.reports]);

  const showAgentReports = Boolean(mdReport);
  const showDimensionalStudy = Boolean(
    job?.status === "completed" && (dimensions || dimensionsError),
  );
  const showAnalysisTabs = showDimensionalStudy && showAgentReports;

  const { handleExportHtml, handlePrint, markdownHref, exportDisabled, decisionSummary } =
    useReportExport({
      reportBodyRef,
      jobId: runId,
      ticker,
      rating: result?.rating ?? historyDetail?.rating ?? null,
      date: tradeDate,
      confidence: result?.confidence ?? historyDetail?.confidence ?? null,
      reports: result?.reports,
      canExportHtml: showAgentReports,
    });

  const tocItems = useMemo(() => extractToc(mdReport), [mdReport]);
  const tocLevel2 = useMemo(() => tocItems.filter((t) => t.level === 2), [tocItems]);
  const tocLevel2Ids = useMemo(() => tocLevel2.map((t) => t.id), [tocLevel2]);
  const activeSectionId = useActiveSection(tocLevel2Ids);

  const headingCursorRef = useRef(0);
  const markdownComponents = useMemo((): Components => {
    headingCursorRef.current = 0;
    return {
      table: ({ children, ...rest }) => (
        <div className="markdown-table-wrap">
          <table {...rest}>{children}</table>
        </div>
      ),
      h2: ({ children }) => {
        const pos = headingCursorRef.current;
        const item = tocItems[pos];
        let id = slugifyHeading(textFromChildren(children));
        if (item?.level === 2) {
          id = item.id;
          headingCursorRef.current += 1;
        }
        return (
          <h2 id={id} className="run-detail-markdown__h2">
            {children}
          </h2>
        );
      },
      h3: ({ children }) => {
        const pos = headingCursorRef.current;
        const item = tocItems[pos];
        let id = slugifyHeading(textFromChildren(children));
        if (item?.level === 3) {
          id = item.id;
          headingCursorRef.current += 1;
        }
        return <h3 id={id}>{children}</h3>;
      },
    };
  }, [tocItems]);

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

  const onRerun = useCallback(async () => {
    const base = historyDetail;
    if (!base) return;
    setActionLoading(true);
    try {
      const body = buildRerunAnalyzePayload(base);
      const r = await submitAnalyze(body);
      navigate(runsPath(r.job_id));
    } finally {
      setActionLoading(false);
    }
  }, [historyDetail, navigate]);

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
            <button type="button" className="ui-btn-secondary" disabled={actionLoading} onClick={() => void onRerun()}>
              Rerun with same setup
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
            <div className="run-detail-page__rating">{result?.rating ?? historyDetail?.rating ?? "—"}</div>
            <div className="run-detail-page__meta">
              <span className="mono">{ticker}</span>
              {tradeDate && <span>As of {tradeDate}</span>}
              <span>Conviction (heuristic): {pct(result?.confidence ?? historyDetail?.confidence)}</span>
            </div>
            <RunProvenancePanel provenance={provenance} />
          </header>

          {showAgentReports && (
            <ReportExportBar
              sticky
              onExportHtml={handleExportHtml}
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
                onClick={() => setAnalysisTab("study")}
              >
                Dimensional study
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={analysisTab === "reports"}
                className={`dashboard-analysis-tab${analysisTab === "reports" ? " dashboard-analysis-tab--active" : ""}`}
                onClick={() => setAnalysisTab("reports")}
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
                  tocLevel2.length > 1
                    ? "dashboard-report-layout dashboard-report-layout--with-toc"
                    : "dashboard-report-layout"
                }
              >
                {tocLevel2.length > 1 && (
                  <nav className="dashboard-report-toc" aria-label="Report sections">
                    <ul>
                      {tocLevel2.map((t) => (
                        <li key={t.id}>
                          <a
                            href={`#${t.id}`}
                            className={
                              "dashboard-report-toc__link" +
                              (t.id === activeSectionId ? " dashboard-report-toc__link--active" : "")
                            }
                          >
                            {t.text}
                          </a>
                        </li>
                      ))}
                    </ul>
                  </nav>
                )}
                <div className="dashboard-report-body">
                  <EvidencePlaceholderCards result={result ?? null} />
                  <section aria-label="Decision summary" className="run-detail-page__glance">
                    <h3>At a glance</h3>
                    <dl className="run-detail-page__glance-grid">
                      {(
                        [
                          ["What to do now", decisionSummary.actionNow],
                          [
                            "Conviction",
                            decisionSummary.confidencePct != null
                              ? `${decisionSummary.confidencePct}% · ${decisionSummary.confidenceLabel}`
                              : decisionSummary.confidenceLabel,
                          ],
                          ["FOMO risk", decisionSummary.fomoLabel],
                          ["Time horizon", decisionSummary.horizon],
                        ] as const
                      ).map(([label, value]) => (
                        <div key={label} className="run-detail-page__glance-row">
                          <dt>{label}</dt>
                          <dd>{value}</dd>
                        </div>
                      ))}
                    </dl>
                  </section>
                  <div ref={reportBodyRef} className="markdown-body dashboard-report-markdown">
                    <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
                      {mdReport}
                    </ReactMarkdown>
                  </div>
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
    </PageFrame>
  );
}
