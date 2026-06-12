import { useCallback, useEffect, useMemo, useState } from "react";
import { fetchProviderModels, type ProviderModel } from "../api";

export type LlmConfig = {
  provider: string;
  deepModel: string;
  quickModel: string;
  backendUrl: string;
  openrouterFreeOnly: boolean;
};

export const PROVIDERS = [
  "openai",
  "google",
  "anthropic",
  "deepseek",
  "openrouter",
  "nvidia",
  "moonshot",
  "xai",
  "qwen",
  "glm",
  "minimax",
  "ollama-local",
  "ollama-remote",
] as const;

export const DISCOVERABLE_PROVIDERS = new Set(["ollama-local", "ollama-remote", "openrouter"]);

export const MODEL_PRESETS: Record<string, { deep: string; quick: string }> = {
  openai: { deep: "gpt-5.5", quick: "gpt-5.4-mini" },
  google: { deep: "gemini-3.1-pro-preview", quick: "gemini-3-flash-preview" },
  anthropic: { deep: "claude-opus-4-7", quick: "claude-sonnet-4-6" },
  deepseek: { deep: "deepseek-v4-pro", quick: "deepseek-v4-flash" },
  openrouter: { deep: "openrouter/free", quick: "openrouter/free" },
  nvidia: { deep: "google/gemma-3-27b-it", quick: "google/gemma-3-27b-it" },
  moonshot: { deep: "moonshot-v1-8k", quick: "moonshot-v1-8k" },
  xai: { deep: "grok-4.20-reasoning", quick: "grok-4.20-non-reasoning" },
  qwen: { deep: "qwen3.6-plus", quick: "qwen3.6-flash" },
  glm: { deep: "glm-5.1", quick: "glm-5-turbo" },
  minimax: { deep: "MiniMax-M2.7", quick: "MiniMax-M2.7-highspeed" },
  ollama: { deep: "glm-4.7-flash:latest", quick: "qwen3:latest" },
  "ollama-local": { deep: "glm-4.7-flash:latest", quick: "qwen3:latest" },
  "ollama-remote": { deep: "glm-4.7-flash:latest", quick: "qwen3:latest" },
};

export type ServerLlmDefaults = {
  provider: string;
  deepModel: string;
  quickModel: string;
  backendUrl: string;
};

function serverCfgToDefaults(serverCfg: Record<string, unknown>): ServerLlmDefaults | null {
  if (typeof serverCfg.llm_provider !== "string") return null;
  return {
    provider: serverCfg.llm_provider === "ollama" ? "ollama-local" : serverCfg.llm_provider,
    deepModel: typeof serverCfg.deep_think_llm === "string" ? serverCfg.deep_think_llm : "",
    quickModel: typeof serverCfg.quick_think_llm === "string" ? serverCfg.quick_think_llm : "",
    backendUrl: typeof serverCfg.backend_url === "string" ? serverCfg.backend_url : "",
  };
}

/** Models/backend to apply when the user picks a provider in the dropdown. */
export function defaultsForProviderSwitch(
  nextProvider: string,
  serverDefaults: ServerLlmDefaults | null,
): Partial<LlmConfig> {
  const preset = MODEL_PRESETS[nextProvider] ?? MODEL_PRESETS.openai;
  const openrouterPatch = nextProvider !== "openrouter" ? { openrouterFreeOnly: false } : {};
  if (
    serverDefaults &&
    serverDefaults.provider === nextProvider &&
    serverDefaults.deepModel &&
    serverDefaults.quickModel
  ) {
    return {
      provider: nextProvider,
      deepModel: serverDefaults.deepModel,
      quickModel: serverDefaults.quickModel,
      ...(serverDefaults.backendUrl ? { backendUrl: serverDefaults.backendUrl } : {}),
      ...openrouterPatch,
    };
  }
  return {
    provider: nextProvider,
    deepModel: preset.deep,
    quickModel: preset.quick,
    ...openrouterPatch,
  };
}

function configFromServerDefaults(serverDefaults: ServerLlmDefaults): LlmConfig {
  const preset = MODEL_PRESETS[serverDefaults.provider] ?? MODEL_PRESETS.openai;
  return {
    provider: serverDefaults.provider,
    deepModel: serverDefaults.deepModel || preset.deep,
    quickModel: serverDefaults.quickModel || preset.quick,
    backendUrl: serverDefaults.backendUrl,
    openrouterFreeOnly: false,
  };
}

const DEFAULT_CONFIG: LlmConfig = {
  provider: "openai",
  deepModel: MODEL_PRESETS.openai.deep,
  quickModel: MODEL_PRESETS.openai.quick,
  backendUrl: "",
  openrouterFreeOnly: false,
};

const LS_KEYS: Record<keyof LlmConfig, string> = {
  provider: "ta:llm.provider",
  deepModel: "ta:llm.deepModel",
  quickModel: "ta:llm.quickModel",
  backendUrl: "ta:llm.backendUrl",
  openrouterFreeOnly: "ta:llm.openrouterFreeOnly",
};

function safeStore(): Storage | null {
  if (typeof globalThis === "undefined") return null;
  const s = (globalThis as { localStorage?: Storage }).localStorage;
  if (!s || typeof s.getItem !== "function") return null;
  return s;
}

function loadFromStorage(): { config: LlmConfig; userKeys: Set<keyof LlmConfig> } {
  const config: LlmConfig = { ...DEFAULT_CONFIG };
  const userKeys = new Set<keyof LlmConfig>();
  const store = safeStore();
  if (!store) return { config, userKeys };
  (Object.keys(LS_KEYS) as (keyof LlmConfig)[]).forEach((k) => {
    const raw = store.getItem(LS_KEYS[k]);
    if (raw == null) return;
    userKeys.add(k);
    if (k === "openrouterFreeOnly") {
      (config as LlmConfig).openrouterFreeOnly = raw === "true";
    } else {
      (config as Record<string, unknown>)[k] = raw;
    }
  });
  return { config, userKeys };
}

function writeToStorage(partial: Partial<LlmConfig>) {
  const store = safeStore();
  if (!store) return;
  (Object.entries(partial) as [keyof LlmConfig, unknown][]).forEach(([k, v]) => {
    if (v == null) return;
    store.setItem(LS_KEYS[k], typeof v === "boolean" ? String(v) : String(v));
  });
}

/**
 * Stateful per-browser LLM picker config.
 *
 * - Reads/writes localStorage so each browser user keeps their choice
 *   independent of the server-side .env default.
 * - `hydrateFromServer` only fills keys the user has *never* touched — server
 *   .env becomes the initial default, not a forced override.
 */
export function useLlmConfig() {
  const initial = useMemo(loadFromStorage, []);
  const [config, setConfigState] = useState<LlmConfig>(initial.config);
  const [userKeys, setUserKeys] = useState<Set<keyof LlmConfig>>(initial.userKeys);
  const [serverDefaults, setServerDefaults] = useState<ServerLlmDefaults | null>(null);

  const setConfig = useCallback((partial: Partial<LlmConfig>) => {
    setConfigState((prev) => ({ ...prev, ...partial }));
    setUserKeys((prev) => {
      const next = new Set(prev);
      (Object.keys(partial) as (keyof LlmConfig)[]).forEach((k) => next.add(k));
      return next;
    });
    writeToStorage(partial);
  }, []);

  const hydrateFromServer = useCallback((serverCfg: Record<string, unknown>) => {
    setServerDefaults(serverCfgToDefaults(serverCfg));
    setConfigState((prev) => {
      const next: LlmConfig = { ...prev };
      const apply = (k: keyof LlmConfig, value: unknown) => {
        if (userKeys.has(k)) return;
        if (k === "openrouterFreeOnly") {
          if (typeof value === "boolean") next.openrouterFreeOnly = value;
          return;
        }
        if (typeof value === "string") {
          (next as Record<string, unknown>)[k] = value;
        } else if (value === null && k === "backendUrl") {
          next.backendUrl = "";
        }
      };
      if (typeof serverCfg.llm_provider === "string") {
        apply("provider", serverCfg.llm_provider === "ollama" ? "ollama-local" : serverCfg.llm_provider);
      }
      apply("deepModel", serverCfg.deep_think_llm);
      apply("quickModel", serverCfg.quick_think_llm);
      apply("backendUrl", serverCfg.backend_url);
      apply("openrouterFreeOnly", serverCfg.openrouter_free_only);
      return next;
    });
  }, [userKeys]);

  const reset = useCallback(() => {
    const store = safeStore();
    if (store) {
      (Object.keys(LS_KEYS) as (keyof LlmConfig)[]).forEach((k) => store.removeItem(LS_KEYS[k]));
    }
    setUserKeys(new Set());
    setConfigState(serverDefaults ? configFromServerDefaults(serverDefaults) : DEFAULT_CONFIG);
  }, [serverDefaults]);

  return { config, setConfig, hydrateFromServer, reset, serverDefaults };
}

/** Build the `config_overrides` payload for /analyze and /batches. */
export function llmConfigToOverrides(config: LlmConfig): Record<string, unknown> {
  const overrides: Record<string, unknown> = {
    llm_provider: config.provider,
    deep_think_llm: config.deepModel,
    quick_think_llm: config.quickModel,
    openrouter_free_only: config.openrouterFreeOnly,
  };
  const trimmed = config.backendUrl.trim();
  if (config.provider.startsWith("ollama")) {
    // Don't inherit a stale OpenRouter URL when the user picks Ollama.
    overrides.backend_url = trimmed && !trimmed.includes("openrouter.ai") ? trimmed : null;
  } else if (trimmed) {
    overrides.backend_url = trimmed;
  }
  return overrides;
}

type LlmPickerProps = {
  value: LlmConfig;
  onChange: (next: Partial<LlmConfig>) => void;
  onReset?: () => void;
  serverDefaults?: ServerLlmDefaults | null;
  disabled?: boolean;
  /** Compact layout collapses Advanced into a single details block. */
  variant?: "full" | "compact";
};

export function LlmPicker({
  value,
  onChange,
  onReset,
  serverDefaults = null,
  disabled,
  variant = "full",
}: LlmPickerProps) {
  const [providerModels, setProviderModels] = useState<ProviderModel[]>([]);
  const [modelsLoading, setModelsLoading] = useState(false);
  const [modelsError, setModelsError] = useState<string | null>(null);
  const [modelsSource, setModelsSource] = useState<string | null>(null);
  const [modelsRefreshedAt, setModelsRefreshedAt] = useState<string | null>(null);
  const [deepCustomMode, setDeepCustomMode] = useState(false);
  const [quickCustomMode, setQuickCustomMode] = useState(false);

  const preset = MODEL_PRESETS[value.provider] ?? MODEL_PRESETS.openai;

  const modelDiscoveryBackendUrl = useMemo(() => {
    const candidate = value.backendUrl.trim() || undefined;
    if (!candidate) return undefined;
    if (value.provider.startsWith("ollama")) {
      if (candidate.includes("openrouter.ai")) return undefined;
      return candidate;
    }
    if (value.provider === "openrouter") {
      if (candidate.includes("/api/tags") || candidate.includes(":11434")) return undefined;
      return candidate;
    }
    return candidate;
  }, [value.provider, value.backendUrl]);

  const refreshModels = useCallback(() => {
    if (!DISCOVERABLE_PROVIDERS.has(value.provider)) {
      setProviderModels([]);
      setModelsError(null);
      setModelsSource(null);
      setModelsRefreshedAt(null);
      setModelsLoading(false);
      return;
    }
    let cancelled = false;
    setModelsLoading(true);
    setModelsError(null);
    void fetchProviderModels(value.provider, modelDiscoveryBackendUrl)
      .then((payload) => {
        if (cancelled) return;
        setProviderModels(Array.isArray(payload.models) ? payload.models : []);
        setModelsSource(payload.source || null);
        setModelsRefreshedAt(new Date().toISOString());
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setProviderModels([]);
        setModelsError(err instanceof Error ? err.message : String(err));
      })
      .finally(() => {
        if (!cancelled) setModelsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [value.provider, modelDiscoveryBackendUrl]);

  useEffect(() => refreshModels(), [refreshModels]);

  const visibleModels = useMemo(() => {
    if (value.provider !== "openrouter") return providerModels;
    if (!value.openrouterFreeOnly) return providerModels;
    return providerModels.filter((m) => Boolean(m.is_free));
  }, [value.provider, providerModels, value.openrouterFreeOnly]);

  const deepInOptions = visibleModels.some((m) => m.id === value.deepModel);
  const quickInOptions = visibleModels.some((m) => m.id === value.quickModel);

  useEffect(() => {
    if (!visibleModels.length) return;
    if (!deepCustomMode && !deepInOptions) onChange({ deepModel: visibleModels[0].id });
    if (!quickCustomMode && !quickInOptions) onChange({ quickModel: visibleModels[0].id });
    // We intentionally exclude onChange from deps to avoid loops; visibleModels suffices.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visibleModels, deepCustomMode, quickCustomMode, deepInOptions, quickInOptions]);

  function onProviderChange(next: string) {
    setDeepCustomMode(false);
    setQuickCustomMode(false);
    onChange(defaultsForProviderSwitch(next, serverDefaults));
  }

  const rowGap = variant === "compact" ? 8 : 12;

  return (
    <div className="llm-picker" style={{ display: "grid", gap: rowGap }}>
      <label style={{ display: "block" }}>
        <span style={{ display: "block", fontSize: "var(--text-caption)", marginBottom: 4 }}>LLM provider</span>
        <select
          value={value.provider}
          onChange={(e) => onProviderChange(e.target.value)}
          disabled={disabled}
          style={{ width: "100%", padding: 8, borderRadius: "var(--radius-inputs)" }}
        >
          {PROVIDERS.map((p) => (
            <option key={p} value={p}>
              {p}
            </option>
          ))}
        </select>
      </label>

      <label style={{ display: "block" }}>
        <span style={{ display: "block", fontSize: "var(--text-caption)", marginBottom: 4 }}>Deep model</span>
        {visibleModels.length > 0 && !deepCustomMode ? (
          <select
            value={deepInOptions ? value.deepModel : ""}
            onChange={(e) => {
              if (e.target.value === "__custom__") {
                setDeepCustomMode(true);
                return;
              }
              onChange({ deepModel: e.target.value });
            }}
            disabled={disabled || modelsLoading}
            style={{ width: "100%", padding: 8, borderRadius: "var(--radius-inputs)" }}
          >
            {!deepInOptions && <option value="">Select a model…</option>}
            {visibleModels.map((m) => (
              <option key={m.id} value={m.id}>
                {m.loaded ? `${m.label} (loaded)` : m.label}
              </option>
            ))}
            <option value="__custom__">Custom model ID…</option>
          </select>
        ) : (
          <input
            value={value.deepModel}
            onChange={(e) => onChange({ deepModel: e.target.value })}
            disabled={disabled}
            style={{ width: "100%", padding: 8 }}
          />
        )}
        {deepCustomMode && (
          <button
            type="button"
            onClick={() => setDeepCustomMode(false)}
            style={{
              marginTop: 6,
              fontSize: 11,
              border: "1px solid var(--color-stone-border)",
              background: "transparent",
              borderRadius: "var(--radius-inputs)",
              padding: "2px 8px",
              cursor: "pointer",
            }}
          >
            Back to discovered models
          </button>
        )}
        <span style={{ fontSize: 11, color: "var(--color-ash-gray)" }}>
          Suggested for {value.provider}: {preset.deep}
        </span>
      </label>

      <label style={{ display: "block" }}>
        <span style={{ display: "block", fontSize: "var(--text-caption)", marginBottom: 4 }}>Quick model</span>
        {visibleModels.length > 0 && !quickCustomMode ? (
          <select
            value={quickInOptions ? value.quickModel : ""}
            onChange={(e) => {
              if (e.target.value === "__custom__") {
                setQuickCustomMode(true);
                return;
              }
              onChange({ quickModel: e.target.value });
            }}
            disabled={disabled || modelsLoading}
            style={{ width: "100%", padding: 8, borderRadius: "var(--radius-inputs)" }}
          >
            {!quickInOptions && <option value="">Select a model…</option>}
            {visibleModels.map((m) => (
              <option key={m.id} value={m.id}>
                {m.loaded ? `${m.label} (loaded)` : m.label}
              </option>
            ))}
            <option value="__custom__">Custom model ID…</option>
          </select>
        ) : (
          <input
            value={value.quickModel}
            onChange={(e) => onChange({ quickModel: e.target.value })}
            disabled={disabled}
            style={{ width: "100%", padding: 8 }}
          />
        )}
        {quickCustomMode && (
          <button
            type="button"
            onClick={() => setQuickCustomMode(false)}
            style={{
              marginTop: 6,
              fontSize: 11,
              border: "1px solid var(--color-stone-border)",
              background: "transparent",
              borderRadius: "var(--radius-inputs)",
              padding: "2px 8px",
              cursor: "pointer",
            }}
          >
            Back to discovered models
          </button>
        )}
        <span style={{ fontSize: 11, color: "var(--color-ash-gray)" }}>
          Suggested for {value.provider}: {preset.quick}
        </span>
      </label>

      {DISCOVERABLE_PROVIDERS.has(value.provider) && (
        <div
          style={{
            fontSize: 11,
            color: "var(--color-ash-gray)",
            border: "1px solid var(--color-stone-border)",
            background: "var(--surface-canvas-fog)",
            borderRadius: "var(--radius-cards)",
            padding: "10px 12px",
            display: "grid",
            gap: 8,
          }}
        >
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
            <span style={{ fontWeight: 600, color: "var(--color-slate-text)" }}>
              Model Discovery ({value.provider})
            </span>
            <button
              type="button"
              onClick={() => refreshModels()}
              disabled={disabled || modelsLoading}
              style={{
                fontSize: 11,
                border: "1px solid var(--color-stone-border)",
                background: "var(--surface-cloud-white)",
                borderRadius: "var(--radius-inputs)",
                padding: "2px 8px",
                cursor: disabled || modelsLoading ? "not-allowed" : "pointer",
              }}
            >
              {modelsLoading ? "Refreshing..." : "Refresh"}
            </button>
          </div>
          {modelsLoading && <span>Checking available models...</span>}
          {!modelsLoading && modelsError && (
            <span>Could not query provider models ({modelsError}). Using manual/preset models.</span>
          )}
          {!modelsLoading && !modelsError && modelsSource && (
            <span>
              Found {visibleModels.length} model(s) from <span className="mono">{modelsSource}</span>
              {modelsRefreshedAt ? ` · updated ${new Date(modelsRefreshedAt).toLocaleTimeString()}` : ""}
            </span>
          )}
        </div>
      )}

      <details style={{ marginTop: 4 }}>
        <summary style={{ cursor: "pointer", fontSize: "var(--text-caption)", fontWeight: 600 }}>
          Routing & overrides
        </summary>
        <label style={{ display: "block", marginTop: 8 }}>
          <span style={{ display: "block", fontSize: "var(--text-caption)", marginBottom: 4 }}>
            LLM backend URL (optional)
          </span>
          <input
            value={value.backendUrl}
            onChange={(e) => onChange({ backendUrl: e.target.value })}
            placeholder="https://openrouter.ai/api/v1"
            disabled={disabled}
            style={{ width: "100%", padding: 8 }}
            className="mono"
          />
          <span style={{ fontSize: 11, color: "var(--color-ash-gray)" }}>
            Leave blank for server default (.env). Saved per browser.
          </span>
        </label>
        <label style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 8 }}>
          <input
            type="checkbox"
            checked={value.openrouterFreeOnly}
            disabled={disabled || value.provider !== "openrouter"}
            onChange={(e) => onChange({ openrouterFreeOnly: e.target.checked })}
          />
          <span style={{ fontSize: 14 }}>OpenRouter free models only</span>
        </label>
        {onReset && (
          <button
            type="button"
            onClick={() => onReset()}
            disabled={disabled}
            style={{
              marginTop: 12,
              fontSize: 11,
              border: "1px solid var(--color-stone-border)",
              background: "transparent",
              borderRadius: "var(--radius-inputs)",
              padding: "4px 10px",
              cursor: disabled ? "not-allowed" : "pointer",
            }}
          >
            Reset to server defaults
          </button>
        )}
      </details>
    </div>
  );
}
