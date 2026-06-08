import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { AppBreadcrumbs } from "../components/navigation/AppBreadcrumbs";
import { runsPath } from "../navigation/routes";
import { Pressable } from "../components/Pressable";
import { PageFrame, PageHeader, Panel } from "../components/PageFrame";
import { LlmPicker, llmConfigToOverrides, useLlmConfig } from "../components/LlmPicker";
import {
  fetchConfig,
  fetchHealth,
  filterAnalystsForBackend,
  mergeSupportedAnalystIds,
  submitAnalyze,
} from "../api";
import { useDocumentTitle } from "../hooks/useDocumentTitle";
import { useJobsRefresh } from "../contexts/JobsTrackerContext";

const ANALYST_OPTIONS = [
  { id: "market", label: "Market" },
  { id: "social", label: "Social Media" },
  { id: "news", label: "News" },
  { id: "fundamentals", label: "Fundamentals" },
  { id: "hot_money", label: "Hot Money" },
  { id: "policy", label: "Policy" },
  { id: "lockup", label: "Lockup" },
  { id: "kronos", label: "Kronos forecast" },
] as const;

const REPORT_FORMATS = ["markdown", "json", "structured"] as const;

/** Rough complexity hint from analyst count and debate rounds. */
function complexityHint(analysts: number, debate: number, risk: number): string {
  const parts: string[] = [];
  if (analysts >= 4 && debate >= 2) parts.push("full pipeline + heavier debate");
  else if (debate >= 2 || risk >= 2) parts.push("extra debate rounds");
  else parts.push("standard depth");
  return parts[0] ?? "";
}

/** Map GET /config into form state for non-LLM-routing fields. LLM routing is owned by useLlmConfig. */
function hydrateFromServerConfig(
  cfg: Record<string, unknown>,
  setters: {
    setDebate: (v: number) => void;
    setRiskRounds: (v: number) => void;
    setOutputLanguage: (v: string) => void;
    setTemperature: (v: number) => void;
    setApplyTemperature: (v: boolean) => void;
  }
) {
  const s = setters;
  if (typeof cfg.max_debate_rounds === "number") s.setDebate(cfg.max_debate_rounds);
  if (typeof cfg.max_risk_discuss_rounds === "number") s.setRiskRounds(cfg.max_risk_discuss_rounds);
  if (typeof cfg.output_language === "string") s.setOutputLanguage(cfg.output_language);
  if (typeof cfg.llm_temperature === "number" && !Number.isNaN(cfg.llm_temperature)) {
    s.setTemperature(cfg.llm_temperature);
    s.setApplyTemperature(true);
  }
}

export function DashboardPage() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const refreshJobsRibbon = useJobsRefresh();
  const tickerFromQs = searchParams.get("ticker")?.trim() ?? "";
  const jobFromQs = searchParams.get("job")?.trim() ?? "";
  const [ticker, setTicker] = useState(() => tickerFromQs || "AAPL");
  const [date, setDate] = useState("");
  const { config: llmConfig, setConfig: setLlmConfig, hydrateFromServer: hydrateLlmFromServer, reset: resetLlm } =
    useLlmConfig();
  const [outputLanguage, setOutputLanguage] = useState("English");
  const [temperature, setTemperature] = useState(0.7);
  const [applyTemperature, setApplyTemperature] = useState(false);
  const [debate, setDebate] = useState(1);
  const [riskRounds, setRiskRounds] = useState(1);
  const [selectedAnalysts, setSelectedAnalysts] = useState<string[]>(() =>
    ANALYST_OPTIONS.map((a) => a.id)
  );
  /** undefined = health not loaded yet; null = legacy payload (restrict extras); array = explicit allow-list */
  const [apiSupportedAnalystIds, setApiSupportedAnalystIds] = useState<string[] | null | undefined>(
    undefined
  );
  const [reportFormat, setReportFormat] = useState<string>("markdown");
  const [configHint, setConfigHint] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [jobNotice, setJobNotice] = useState<string | null>(null);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const activeJobIdRef = useRef<string | null>(null);
  useDocumentTitle(ticker.trim() ? `${ticker.trim().toUpperCase()} · Analysis` : "Analysis");

  useEffect(() => {
    if (tickerFromQs) setTicker(tickerFromQs);
  }, [tickerFromQs]);

  useEffect(() => {
    let cancelled = false;
    void Promise.allSettled([fetchHealth(), fetchConfig()]).then((results) => {
      if (cancelled) return;
      const h = results[0].status === "fulfilled" ? results[0].value : null;
      const cfg =
        results[1].status === "fulfilled" && results[1].value && typeof results[1].value === "object"
          ? (results[1].value as Record<string, unknown>)
          : null;
      setApiSupportedAnalystIds(mergeSupportedAnalystIds(h, cfg));
    });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const id = jobFromQs.trim();
    if (!id) return;
    navigate(runsPath(id), { replace: true });
  }, [jobFromQs, navigate]);

  useEffect(() => {
    let cancelled = false;
    void fetchConfig()
      .then((cfg) => {
        if (cancelled) return;
        hydrateFromServerConfig(cfg, {
          setDebate,
          setRiskRounds,
          setOutputLanguage,
          setTemperature,
          setApplyTemperature,
        });
        hydrateLlmFromServer(cfg);
        setConfigHint("Form filled from server config (TRADINGAGENTS_* / .env via GET /config).");
      })
      .catch(() => {
        if (!cancelled) {
          setConfigHint(
            "Could not load /config (is the API running on :8808 with Vite proxy?). Using local placeholders."
          );
        }
      });
    return () => {
      cancelled = true;
    };
  }, [hydrateLlmFromServer]);

  const jobActive = submitting;

  async function runAnalysis() {
    setSubmitting(true);
    setJobNotice(null);
    const overrides: Record<string, unknown> = {
      ...llmConfigToOverrides(llmConfig),
      max_debate_rounds: debate,
      max_risk_discuss_rounds: riskRounds,
      output_language: outputLanguage,
    };
    if (applyTemperature) overrides.llm_temperature = temperature;
    try {
      const { analysts: analystsPayload, dropped } = filterAnalystsForBackend(
        selectedAnalysts,
        apiSupportedAnalystIds
      );
      if (dropped.length) {
        setJobNotice(
          `Unsupported analyst(s) on this API, omitted from request: ${dropped.join(", ")}. ` +
            `Run the API from this repo (\`pip install -e .\`, then \`uvicorn api.main:app --port 8808\`) so all focus areas are accepted.`
        );
      }
      const r = await submitAnalyze({
        ticker: ticker.trim(),
        date: date || undefined,
        config_overrides: overrides,
        analysts: analystsPayload,
        report_format: reportFormat as "markdown" | "json" | "structured",
      });
      refreshJobsRibbon();
      activeJobIdRef.current = r.job_id;
      navigate(runsPath(r.job_id), { replace: true });
    } finally {
      setSubmitting(false);
    }
  }

  const hintLine = complexityHint(selectedAnalysts.length, debate, riskRounds);

  return (
    <PageFrame className="dashboard-page content-entrance">
      <PageHeader
        title="Main analysis"
        description="Start a single-stock analysis here. Live progress and reports open on the run page. Outputs are research artifacts, not financial advice."
        meta={
          <>
            <AppBreadcrumbs items={[{ label: "Analysis" }]} />
            <AnimatePresence>
              {configHint && (
                <motion.p
                  key="config-hint"
                  className="notice"
                  initial={{ opacity: 0, y: -4 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -4 }}
                  transition={{ duration: 0.2, ease: [0.25, 1, 0.5, 1] }}
                >
                  {configHint}
                </motion.p>
              )}
            </AnimatePresence>
            <AnimatePresence>
              {jobNotice && (
                <motion.p
                  key="job-notice"
                  className="notice notice--warn"
                  initial={{ opacity: 0, y: -4 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -4 }}
                  transition={{ duration: 0.2, ease: [0.25, 1, 0.5, 1] }}
                >
                  {jobNotice}
                </motion.p>
              )}
            </AnimatePresence>
          </>
        }
      />

      <motion.section
        className="dashboard-workspace"
        aria-label="Configuration and run"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ staggerChildren: 0.08, delayChildren: 0.05 }}
      >
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.25, ease: [0.25, 1, 0.5, 1] }}
        >
        <Panel
          className="dashboard-setup-card"
          title="Setup"
          subtitle="Ticker and date are all you need. Open Advanced for routing, analysts, and debate depth."
        >

          <div className="dashboard-advanced">
            <button
              type="button"
              className="dashboard-advanced__summary"
              onClick={() => setAdvancedOpen((prev) => !prev)}
              aria-expanded={advancedOpen}
            >
              Advanced
              <motion.span
                style={{ display: "inline-block", marginLeft: 6 }}
                animate={{ rotate: advancedOpen ? 180 : 0 }}
                transition={{ duration: 0.2, ease: [0.25, 1, 0.5, 1] }}
                aria-hidden
              >
                ▼
              </motion.span>
            </button>
            <AnimatePresence initial={false}>
              {advancedOpen && (
                <motion.div
                  key="advanced-content"
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: "auto", transition: { duration: 0.2, ease: [0.25, 1, 0.5, 1] } }}
                  exit={{ opacity: 0, height: 0, transition: { duration: 0.15, ease: [0.25, 1, 0.5, 1] } }}
                >
            <label className="ui-field">
              <span className="ui-field__label">
                Temperature: {temperature.toFixed(2)}
              </span>
              <label className="ui-field-row">
                <input
                  type="checkbox"
                  checked={applyTemperature}
                  disabled={jobActive}
                  onChange={(e) => setApplyTemperature(e.target.checked)}
                />
                <span>Send temperature on each run (otherwise model default)</span>
              </label>
              <input
                type="range"
                min={0}
                max={2}
                step={0.05}
                value={temperature}
                onChange={(e) => setTemperature(Number(e.target.value))}
                disabled={!applyTemperature || jobActive}
                className="dashboard-advanced__range"
              />
            </label>
            <LlmPicker
              value={llmConfig}
              onChange={setLlmConfig}
              onReset={resetLlm}
              disabled={jobActive}
            />
            <label className="ui-field">
              <span className="ui-field__label">Output language</span>
              <input
                className="ui-input"
                value={outputLanguage}
                onChange={(e) => setOutputLanguage(e.target.value)}
                disabled={jobActive}
              />
            </label>
            <label className="ui-field">
              <span className="ui-field__label">Focus area (analysts)</span>
              <div className="stack-sm">
                {ANALYST_OPTIONS.map((a) => (
                  <label key={a.id} className="ui-field-row">
                    <input
                      type="checkbox"
                      checked={selectedAnalysts.includes(a.id)}
                      disabled={jobActive}
                      onChange={(e) => {
                        if (e.target.checked) {
                          setSelectedAnalysts((prev) => [...prev, a.id]);
                        } else {
                          setSelectedAnalysts((prev) => prev.filter((id) => id !== a.id));
                        }
                      }}
                    />
                    {a.label}
                  </label>
                ))}
              </div>
            </label>
            <label className="ui-field">
              <span className="ui-field__label">Report format</span>
              <select
                className="ui-input"
                value={reportFormat}
                onChange={(e) => setReportFormat(e.target.value)}
                disabled={jobActive}
              >
                {REPORT_FORMATS.map((f) => (
                  <option key={f} value={f}>
                    {f}
                  </option>
                ))}
              </select>
            </label>
            <label className="ui-field">
              <span className="ui-field__label">Debate rounds</span>
              <input
                className="ui-input"
                type="number"
                min={0}
                max={5}
                value={debate}
                disabled={jobActive}
                onChange={(e) => setDebate(Number(e.target.value))}
              />
            </label>
            <label className="ui-field">
              <span className="ui-field__label">Risk rounds</span>
              <input
                className="ui-input"
                type="number"
                min={0}
                max={5}
                value={riskRounds}
                disabled={jobActive}
                onChange={(e) => setRiskRounds(Number(e.target.value))}
              />
            </label>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </Panel>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.25, delay: 0.08, ease: [0.25, 1, 0.5, 1] }}
        >
        <Panel className="dashboard-run-card panel--sticky" title="Run">
          <label className="ui-field">
            <span className="ui-field__label">Ticker</span>
            <input
              className="ui-input"
              value={ticker}
              onChange={(e) => setTicker(e.target.value)}
              disabled={jobActive}
            />
          </label>
          <label className="ui-field">
            <span className="ui-field__label">Date (YYYY-MM-DD, optional)</span>
            <input
              className="ui-input"
              value={date}
              onChange={(e) => setDate(e.target.value)}
              placeholder="today"
              disabled={jobActive}
            />
          </label>

          <div className="run-meta-row">
            <span className="mono">
              {llmConfig.provider} · {llmConfig.quickModel}
            </span>
            {hintLine && <span>· {hintLine}</span>}
          </div>

          <Pressable
            className="ui-btn-primary ui-btn-full"
            disabled={jobActive || apiSupportedAnalystIds === undefined}
            onClick={() => void runAnalysis().catch((e) => alert(String(e)))}
          >
            {apiSupportedAnalystIds === undefined
              ? "Checking API…"
              : submitting
                ? (
                    <motion.span
                      key="starting"
                      initial={{ opacity: 0.6 }}
                      animate={{ opacity: [0.6, 1, 0.6] }}
                      transition={{ duration: 1.2, repeat: Infinity, ease: "easeInOut" }}
                    >
                      Starting…
                    </motion.span>
                  )
                : "Start analysis"}
          </Pressable>

        </Panel>
        </motion.div>
      </motion.section>

    </PageFrame>
  );
}
