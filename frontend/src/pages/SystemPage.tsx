import { useEffect, useState } from "react";
import {
  fetchConfig,
  fetchHealth,
  postClearCache,
  postRuntimeConfig,
  type HealthPayload,
} from "../api";

export function SystemPage() {
  const [health, setHealth] = useState<HealthPayload | null>(null);
  const [config, setConfig] = useState<Record<string, unknown> | null>(null);
  const [adminKey, setAdminKey] = useState("");
  const [provider, setProvider] = useState("openai");
  const [deep, setDeep] = useState("gpt-5.4");
  const [quick, setQuick] = useState("gpt-5.4-mini");
  const [openaiKey, setOpenaiKey] = useState("");
  const [msg, setMsg] = useState<string | null>(null);

  useEffect(() => {
    void fetchHealth()
      .then(setHealth)
      .catch(() => setHealth(null));
    void fetchConfig()
      .then(setConfig)
      .catch(() => setConfig(null));
  }, []);

  return (
    <div style={{ maxWidth: "720px" }}>
      <h1 style={{ marginTop: 0 }}>System and maintenance</h1>

      <section
        style={{
          marginBottom: "var(--spacing-24)",
          padding: "var(--spacing-24)",
          background: "var(--surface-cloud-white)",
          borderRadius: "var(--radius-lg)",
          border: "1px solid var(--color-stone-border)",
        }}
      >
        <h2 style={{ marginTop: 0 }}>Service health</h2>
        {health ? (
          <ul style={{ margin: 0, paddingLeft: 20 }}>
            <li>
              LLM API key:{" "}
              {health.api_key_configured ? (
                <span style={{ color: "#166534" }}>configured</span>
              ) : (
                <span style={{ color: "#b91c1c" }}>missing</span>
              )}
            </li>
            <li>Provider: {health.llm_provider}</li>
            <li>State store: {health.state_store}</li>
            <li>Cloudflare KV: {health.cloudflare_kv_configured ? "yes" : "no"}</li>
            <li>Data cache: {health.data_cache_dir}</li>
            <li>Results: {health.results_dir}</li>
          </ul>
        ) : (
          <p>Could not load /api/health</p>
        )}
      </section>

      <section
        style={{
          marginBottom: "var(--spacing-24)",
          padding: "var(--spacing-24)",
          background: "var(--surface-cloud-white)",
          borderRadius: "var(--radius-lg)",
          border: "1px solid var(--color-stone-border)",
        }}
      >
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

      <section
        style={{
          padding: "var(--spacing-24)",
          background: "var(--surface-cloud-white)",
          borderRadius: "var(--radius-lg)",
          border: "1px solid var(--color-stone-border)",
        }}
      >
        <h2 style={{ marginTop: 0 }}>Runtime updates</h2>
        <p style={{ fontSize: 14, color: "var(--color-ash-gray)" }}>
          Requires <span className="mono">TRADINGAGENTS_ADMIN_KEY</span> on the server. Writes
          non-secret overrides to local state file or Cloudflare KV. Optional allow-listed secrets
          persist to the same store and are loaded into <span className="mono">os.environ</span> on
          next request bootstrap.
        </p>
        <label style={{ display: "block", marginBottom: 8 }}>
          X-Admin-Key
          <input
            type="password"
            value={adminKey}
            onChange={(e) => setAdminKey(e.target.value)}
            style={{ display: "block", width: "100%", marginTop: 4, padding: 8 }}
          />
        </label>
        <label style={{ display: "block", marginBottom: 8 }}>
          llm_provider
          <input
            value={provider}
            onChange={(e) => setProvider(e.target.value)}
            style={{ display: "block", width: "100%", marginTop: 4, padding: 8 }}
          />
        </label>
        <label style={{ display: "block", marginBottom: 8 }}>
          deep_think_llm
          <input
            value={deep}
            onChange={(e) => setDeep(e.target.value)}
            style={{ display: "block", width: "100%", marginTop: 4, padding: 8 }}
          />
        </label>
        <label style={{ display: "block", marginBottom: 8 }}>
          quick_think_llm
          <input
            value={quick}
            onChange={(e) => setQuick(e.target.value)}
            style={{ display: "block", width: "100%", marginTop: 4, padding: 8 }}
          />
        </label>
        <label style={{ display: "block", marginBottom: 8 }}>
          OPENAI_API_KEY (optional, stored if admin enabled)
          <input
            type="password"
            value={openaiKey}
            onChange={(e) => setOpenaiKey(e.target.value)}
            style={{ display: "block", width: "100%", marginTop: 4, padding: 8 }}
          />
        </label>
        {msg && <p>{msg}</p>}
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 12 }}>
          <button
            type="button"
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
            style={{
              padding: "10px 16px",
              background: "var(--color-chartwell-blue)",
              color: "white",
              border: "none",
              borderRadius: "var(--radius-buttons)",
              cursor: "pointer",
            }}
          >
            Save runtime config
          </button>
          <button
            type="button"
            onClick={() =>
              void postClearCache(adminKey, "checkpoints")
                .then(() => setMsg("Checkpoint DBs cleared under data_cache_dir/checkpoints."))
                .catch((e) => setMsg(String(e)))
            }
            style={{
              padding: "10px 16px",
              background: "var(--color-ghost-ink)",
              color: "white",
              border: "none",
              borderRadius: "var(--radius-buttons)",
              cursor: "pointer",
            }}
          >
            Clear checkpoint cache
          </button>
        </div>
      </section>
    </div>
  );
}
