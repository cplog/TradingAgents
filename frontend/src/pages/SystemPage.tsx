import { useEffect, useState } from "react";
import {
  fetchConfig,
  fetchHealth,
  postClearCache,
  postRuntimeConfig,
  type HealthPayload,
} from "../api";
import { PageFrame, PageHeader } from "../components/PageFrame";
import { AppBreadcrumbs } from "../components/navigation/AppBreadcrumbs";
import { useDocumentTitle } from "../hooks/useDocumentTitle";

export function SystemPage() {
  const [health, setHealth] = useState<HealthPayload | null>(null);
  const [config, setConfig] = useState<Record<string, unknown> | null>(null);
  const [adminKey, setAdminKey] = useState("");
  const [provider, setProvider] = useState("openai");
  const [deep, setDeep] = useState("gpt-5.4");
  const [quick, setQuick] = useState("gpt-5.4-mini");
  const [openaiKey, setOpenaiKey] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  useDocumentTitle("System");

  useEffect(() => {
    void fetchHealth()
      .then(setHealth)
      .catch(() => setHealth(null));
    void fetchConfig()
      .then(setConfig)
      .catch(() => setConfig(null));
  }, []);

  return (
    <PageFrame>
      <PageHeader
        title="System and maintenance"
        description="Service health, runtime config, and cache controls."
        meta={<AppBreadcrumbs items={[{ label: "System" }]} />}
      />

      <section className="page-section section-gap">
        <h2 style={{ marginTop: 0 }}>Service health</h2>
        {health ? (
          <>
            <ul style={{ margin: 0, paddingLeft: 20 }}>
              <li>
                LLM API key:{" "}
                {health.api_key_configured ? (
                  <span style={{ color: "var(--color-sage)" }}>configured</span>
                ) : (
                  <span style={{ color: "var(--color-danger)" }}>missing</span>
                )}
              </li>
              <li>Provider: {health.llm_provider}</li>
              <li className="mono" style={{ wordBreak: "break-word" }}>
                Analysts accepted: {(health.supported_analyst_ids ?? []).join(", ") || "—"}
              </li>
              <li>State store: {health.state_store}</li>
              <li>Cloudflare KV: {health.cloudflare_kv_configured ? "yes" : "no"}</li>
              <li>Data cache: {health.data_cache_dir}</li>
              <li>Results: {health.results_dir}</li>
            </ul>
            <h3 style={{ margin: "16px 0 8px" }}>Data source checks</h3>
            {health.data_source_checks && Object.keys(health.data_source_checks).length ? (
              <div style={{ overflowX: "auto" }}>
                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 14 }}>
                  <thead>
                    <tr>
                      <th style={{ textAlign: "left", padding: "6px 8px", borderBottom: "1px solid var(--color-stone-border)" }}>Source</th>
                      <th style={{ textAlign: "left", padding: "6px 8px", borderBottom: "1px solid var(--color-stone-border)" }}>Configured</th>
                      <th style={{ textAlign: "left", padding: "6px 8px", borderBottom: "1px solid var(--color-stone-border)" }}>Status</th>
                      <th style={{ textAlign: "left", padding: "6px 8px", borderBottom: "1px solid var(--color-stone-border)" }}>Detail</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(health.data_source_checks).map(([name, check]) => (
                      <tr key={name}>
                        <td style={{ padding: "6px 8px", borderBottom: "1px solid var(--color-canvas-fog)" }}>{name}</td>
                        <td style={{ padding: "6px 8px", borderBottom: "1px solid var(--color-canvas-fog)" }}>
                          {check.configured ? "yes" : "no"}
                        </td>
                        <td style={{ padding: "6px 8px", borderBottom: "1px solid var(--color-canvas-fog)" }}>
                          <span style={{ color: check.ok ? "var(--color-sage)" : "var(--color-danger)" }}>
                            {check.ok ? "ok" : "down"}
                          </span>
                        </td>
                        <td style={{ padding: "6px 8px", borderBottom: "1px solid var(--color-canvas-fog)" }}>
                          {check.detail || "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p style={{ margin: "8px 0 0" }}>No data source checks reported.</p>
            )}
          </>
        ) : (
          <p>Could not load /api/health</p>
        )}
      </section>

      <section className="page-section section-gap">
        <h2 style={{ marginTop: 0 }}>Resolved config (redacted)</h2>
        <pre
          className="mono"
          style={{
            fontSize: 12,
            overflow: "auto",
            maxHeight: 240,
            background: "var(--color-canvas-fog)",
            padding: 12,
            borderRadius: "var(--radius-md)",
          }}
        >
          {config ? JSON.stringify(config, null, 2) : "…"}
        </pre>
      </section>

      <section className="page-section section-gap">
        <h2 style={{ marginTop: 0 }}>Runtime updates</h2>
        <p style={{ fontSize: 14, color: "var(--color-ash-gray)" }}>
          Requires <span className="mono">TRADINGAGENTS_ADMIN_KEY</span> on the server. Writes
          non-secret overrides to local state file or Cloudflare KV. Optional allow-listed secrets
          persist to the same store and are loaded into <span className="mono">os.environ</span> on
          next request bootstrap.
        </p>
        <label className="ui-field">
          <span className="ui-field__label">X-Admin-Key</span>
          <input
            className="ui-input"
            type="password"
            value={adminKey}
            onChange={(e) => setAdminKey(e.target.value)}
          />
        </label>
        <label className="ui-field">
          <span className="ui-field__label">llm_provider</span>
          <input
            className="ui-input"
            value={provider}
            onChange={(e) => setProvider(e.target.value)}
          />
        </label>
        <label className="ui-field">
          <span className="ui-field__label">deep_think_llm</span>
          <input
            className="ui-input"
            value={deep}
            onChange={(e) => setDeep(e.target.value)}
          />
        </label>
        <label className="ui-field">
          <span className="ui-field__label">quick_think_llm</span>
          <input
            className="ui-input"
            value={quick}
            onChange={(e) => setQuick(e.target.value)}
          />
        </label>
        <label className="ui-field">
          <span className="ui-field__label">OPENAI_API_KEY (optional, stored if admin enabled)</span>
          <input
            className="ui-input"
            type="password"
            value={openaiKey}
            onChange={(e) => setOpenaiKey(e.target.value)}
          />
        </label>
        {msg && <p>{msg}</p>}
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 12 }}>
          <button
            type="button"
            className="ui-btn-primary"
            onClick={() =>
              void postRuntimeConfig(
                {
                  service_overrides: {
                    llm_provider: provider,
                    deep_think_llm: deep,
                    quick_think_llm: quick,
                  },
                  secrets: openaiKey.trim() ? { OPENAI_API_KEY: openaiKey.trim() } : undefined,
                },
                adminKey
              )
                .then(() => setMsg("Saved. Restart workers or reload config as needed."))
                .catch((e) => setMsg(String(e)))
            }
          >
            Save runtime config
          </button>
          <button
            type="button"
            className="ui-btn-secondary"
            onClick={() =>
              void postClearCache(adminKey, "checkpoints")
                .then(() => setMsg("Checkpoint DBs cleared under data_cache_dir/checkpoints."))
                .catch((e) => setMsg(String(e)))
            }
          >
            Clear checkpoint cache
          </button>
        </div>
      </section>

      <section className="page-section">
        <h2 style={{ marginTop: 0 }}>External consoles</h2>
        <p style={{ fontSize: 14, color: "var(--color-ash-gray)" }}>
          Optional Cloudflare KV for durable API state, or local JSON at{" "}
          <span className="mono">~/.tradingagents/api_state.json</span>.
        </p>
        <ul>
          <li>
            <a href="https://dash.cloudflare.com/" target="_blank" rel="noreferrer">
              Cloudflare Dashboard
            </a>{" "}
            (Workers → KV)
          </li>
          <li>
            <a href="https://fastapi.tiangolo.com/" target="_blank" rel="noreferrer">
              FastAPI docs
            </a>{" "}
            for this service at <span className="mono">/docs</span> when the API is running.
          </li>
        </ul>
        <p className="notice">
          To add Mongo Express or Redis Commander, extend{" "}
          <span className="mono">docker-compose.yml</span> on your fork; they are not bundled here.
        </p>
      </section>
    </PageFrame>
  );
}
