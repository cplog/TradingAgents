import { useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { AppBreadcrumbs } from "../components/navigation/AppBreadcrumbs";
import { paths, runsPath } from "../navigation/routes";
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
  const activeJobIdRef = useRef<string | null>(null);
  useDocumentTitle(ticker.trim() ? `${ticker.trim().toUpperCase()} — Analysis` : "Analysis");

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
            "Could not load /config (is the API running on :8000 with Vite proxy?). Using local placeholders."
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
          `Unsupported analyst(s) on this API — omitted from request: ${dropped.join(", ")}. ` +
            `Run the API from this repo (\`pip install -e .\`, then \`uvicorn api.main:app --port 8000\`) so all focus areas are accepted.`
        );
      }
      const r = await submitAnalyze({
        ticker: ticker.trim(),
        date: date || undefined,
        config_overrides: overrides,
        analysts: analystsPayload,
        report_format: reportFormat as "markdown" | "json" | "structured",
      });
      activeJobIdRef.current = r.job_id;
      navigate(runsPath(r.job_id), { replace: true });
    } finally {
      setSubmitting(false);
    }
  }

  const hintLine = complexityHint(selectedAnalysts.length, debate, riskRounds);
  const pipelineLabels = ["Queued", "Pipeline", "Report", "Done"];

  function pipelineDotClass(): string {
    return "pipeline-dot pipeline-dot--todo";
  }

  return (
    <PageFrame className="dashboard-page">
      <PageHeader
        title="Main analysis"
        description="Start a single-stock analysis here. Live progress and reports open on the run page. Outputs are research artifacts, not financial advice."
        meta={
          <>
            <AppBreadcrumbs items={[{ label: "Analysis" }]} />
            {configHint && <p className="notice">{configHint}</p>}
            {jobNotice && <p className="notice notice--warn">{jobNotice}</p>}
          </>
        }
      />

      <section className="dashboard-workspace" aria-label="Configuration and run">
        <Panel
          className="dashboard-setup-card"
          title="Setup"
          subtitle="Essentials cover most runs. Open Advanced for routing, sampling, and debate depth."
        >
          <fieldset className="field-group">
            <legend style={{ fontWeight: 600, marginBottom: "var(--spacing-12)", fontSize: "var(--text-caption)" }}>
              Essentials
            </legend>
            <LlmPicker
              value={llmConfig}
              onChange={setLlmConfig}
              onReset={resetLlm}
              disabled={jobActive}
            />
            <label style={{ display: "block", marginBottom: 12, marginTop: 12 }}>
              <span style={{ display: "block", fontSize: "var(--text-caption)", marginBottom: 4 }}>
                Output language
              </span>
              <input
                value={outputLanguage}
                onChange={(e) => setOutputLanguage(e.target.value)}
                disabled={jobActive}
                style={{ width: "100%", padding: 8 }}
              />
            </label>
            <label style={{ display: "block", marginBottom: 12 }}>
              <span style={{ display: "block", fontSize: "var(--text-caption)", marginBottom: 4 }}>
                Focus area (analysts)
              </span>
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                {ANALYST_OPTIONS.map((a) => (
                  <label key={a.id} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 14 }}>
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
            <label style={{ display: "block", marginBottom: 12 }}>
              <span style={{ display: "block", fontSize: "var(--text-caption)", marginBottom: 4 }}>
                Report format
              </span>
              <select
                value={reportFormat}
                onChange={(e) => setReportFormat(e.target.value)}
                disabled={jobActive}
                style={{ width: "100%", padding: 8, borderRadius: "var(--radius-inputs)" }}
              >
                {REPORT_FORMATS.map((f) => (
                  <option key={f} value={f}>
                    {f}
                  </option>
                ))}
              </select>
            </label>
          </fieldset>

          <details style={{ marginTop: "var(--spacing-16)" }}>
            <summary
              style={{
                cursor: "pointer",
                fontWeight: 600,
                fontSize: "var(--text-caption)",
                color: "var(--color-slate-text)",
                marginBottom: "var(--spacing-12)",
              }}
            >
              Advanced
            </summary>
            <label style={{ display: "block", marginBottom: 12 }}>
              <span style={{ display: "block", fontSize: "var(--text-caption)", marginBottom: 4 }}>
                Temperature: {temperature.toFixed(2)}
              </span>
              <label style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
                <input
                  type="checkbox"
                  checked={applyTemperature}
                  disabled={jobActive}
                  onChange={(e) => setApplyTemperature(e.target.checked)}
                />
                <span style={{ fontSize: 13 }}>Send temperature on each run (otherwise model default)</span>
              </label>
              <input
                type="range"
                min={0}
                max={2}
                step={0.05}
                value={temperature}
                onChange={(e) => setTemperature(Number(e.target.value))}
                disabled={!applyTemperature || jobActive}
                style={{ width: "100%", opacity: applyTemperature ? 1 : 0.5 }}
              />
            </label>
            <label style={{ display: "block", marginBottom: 12 }}>
              <span style={{ display: "block", fontSize: "var(--text-caption)", marginBottom: 4 }}>
                Debate rounds
              </span>
              <input
                type="number"
                min={0}
                max={5}
                value={debate}
                disabled={jobActive}
                onChange={(e) => setDebate(Number(e.target.value))}
                style={{ width: "100%", padding: 8 }}
              />
            </label>
            <label style={{ display: "block", marginBottom: 12 }}>
              <span style={{ display: "block", fontSize: "var(--text-caption)", marginBottom: 4 }}>
                Risk rounds
              </span>
              <input
                type="number"
                min={0}
                max={5}
                value={riskRounds}
                disabled={jobActive}
                onChange={(e) => setRiskRounds(Number(e.target.value))}
                style={{ width: "100%", padding: 8 }}
              />
            </label>
          </details>
        </Panel>

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

          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "var(--spacing-8)",
              flexWrap: "wrap",
              marginBottom: "var(--spacing-12)",
              fontSize: "var(--text-caption)",
              color: "var(--color-ash-gray)",
            }}
          >
            <span className="mono">
              {llmConfig.provider} · {llmConfig.quickModel}
            </span>
            {hintLine && <span>· {hintLine}</span>}
          </div>

          <div className="pipeline-track" style={{ marginBottom: "var(--spacing-16)" }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 4 }}>
              {pipelineLabels.map((label, i) => (
                <div key={label} style={{ flex: 1, textAlign: "center", minWidth: 0 }}>
                  <div className={pipelineDotClass()} title={label} />
                  <div
                    style={{
                      fontSize: 10,
                      color: "var(--color-steel-gray)",
                      marginTop: 4,
                      whiteSpace: "nowrap",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                    }}
                  >
                    {label}
                  </div>
                </div>
              ))}
            </div>
          </div>

          <Pressable
            className="ui-btn-primary"
            disabled={jobActive || apiSupportedAnalystIds === undefined}
            onClick={() => void runAnalysis().catch((e) => alert(String(e)))}
            style={{ width: "100%" }}
          >
            {apiSupportedAnalystIds === undefined
              ? "Checking API…"
              : submitting
                ? "Starting…"
                : "Start analysis"}
          </Pressable>

        </Panel>
      </section>

    </PageFrame>
  );
}
