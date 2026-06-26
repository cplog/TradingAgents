import { act, StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { beforeEach, describe, expect, it, vi } from "vitest";
import * as api from "../api";
import { LlmPicker, defaultsForProviderSwitch, llmConfigToOverrides, useLlmConfig, type LlmConfig } from "./LlmPicker";

describe("llmConfigToOverrides", () => {
  const base: LlmConfig = {
    provider: "openai",
    deepModel: "gpt-5",
    quickModel: "gpt-4o-mini",
    backendUrl: "",
    openrouterFreeOnly: false,
  };

  it("emits provider + model overrides for a stock provider", () => {
    expect(llmConfigToOverrides(base)).toEqual({
      llm_provider: "openai",
      deep_think_llm: "gpt-5",
      quick_think_llm: "gpt-4o-mini",
      openrouter_free_only: false,
      backend_url: null,
    });
  });

  it("forces backend_url=null when switching to ollama with empty backend", () => {
    const out = llmConfigToOverrides({ ...base, provider: "ollama-remote" });
    expect(out.backend_url).toBeNull();
  });

  it("ignores an openrouter backend leaked into an ollama config", () => {
    const out = llmConfigToOverrides({
      ...base,
      provider: "ollama-remote",
      backendUrl: "https://openrouter.ai/api/v1",
    });
    expect(out.backend_url).toBeNull();
  });

  it("passes through a custom backend for non-ollama providers", () => {
    const out = llmConfigToOverrides({ ...base, backendUrl: "https://custom.example/v1" });
    expect(out.backend_url).toBe("https://custom.example/v1");
  });

  it("clears backend_url when the user leaves it blank (avoids stale server .env)", () => {
    const out = llmConfigToOverrides({ ...base, provider: "openai", backendUrl: "" });
    expect(out.backend_url).toBeNull();
  });
});

describe("defaultsForProviderSwitch", () => {
  it("uses server .env models when switching to the server-configured provider", () => {
    const patch = defaultsForProviderSwitch("nvidia", {
      provider: "nvidia",
      deepModel: "google/diffusiongemma-26b-a4b-it",
      quickModel: "google/diffusiongemma-26b-a4b-it",
      backendUrl: "https://integrate.api.nvidia.com/v1",
    });
    expect(patch).toMatchObject({
      provider: "nvidia",
      deepModel: "google/diffusiongemma-26b-a4b-it",
      quickModel: "google/diffusiongemma-26b-a4b-it",
      backendUrl: "https://integrate.api.nvidia.com/v1",
    });
  });

  it("falls back to frontend presets for other providers", () => {
    const patch = defaultsForProviderSwitch("nvidia", {
      provider: "deepseek",
      deepModel: "deepseek-v4-pro",
      quickModel: "deepseek-v4-flash",
      backendUrl: "",
    });
    expect(patch).toMatchObject({
      provider: "nvidia",
      deepModel: "google/gemma-3-27b-it",
      quickModel: "google/gemma-3-27b-it",
    });
  });
});

/** Tiny harness: render a component that exposes `useLlmConfig` to assertions. */
function renderHook<T>(useHook: () => T): {
  current: { value: T };
  unmount: () => void;
  el: HTMLElement;
} {
  const ref: { value: T } = { value: undefined as unknown as T };
  function Probe() {
    ref.value = useHook();
    return null;
  }
  const el = document.createElement("div");
  document.body.appendChild(el);
  const root = createRoot(el);
  act(() => {
    root.render(
      <StrictMode>
        <Probe />
      </StrictMode>,
    );
  });
  return {
    current: ref,
    el,
    unmount: () => {
      act(() => root.unmount());
      el.remove();
    },
  };
}

describe("useLlmConfig", () => {
  let storageBacking: Record<string, string>;

  beforeEach(() => {
    storageBacking = {};
    Object.defineProperty(window, "localStorage", {
      configurable: true,
      value: {
        getItem: vi.fn((key: string) => storageBacking[key] ?? null),
        setItem: vi.fn((key: string, value: string) => {
          storageBacking[key] = value;
        }),
        removeItem: vi.fn((key: string) => {
          delete storageBacking[key];
        }),
      },
    });
  });

  it("reads initial config from localStorage", () => {
    storageBacking["ta:llm.provider"] = "anthropic";
    storageBacking["ta:llm.deepModel"] = "claude-opus";

    const h = renderHook(() => useLlmConfig());
    expect(h.current.value.config.provider).toBe("anthropic");
    expect(h.current.value.config.deepModel).toBe("claude-opus");
    h.unmount();
  });

  it("hydrateFromServer records server defaults without changing saved picker values", () => {
    storageBacking["ta:llm.provider"] = "anthropic";
    storageBacking["ta:llm.deepModel"] = "claude-opus";

    const h = renderHook(() => useLlmConfig());
    act(() => {
      h.current.value.hydrateFromServer({
        llm_provider: "nvidia",
        deep_think_llm: "nvidia/nemotron-3-ultra-550b-a55b",
        quick_think_llm: "nvidia/nemotron-3-ultra-550b-a55b",
        backend_url: "https://integrate.api.nvidia.com/v1",
      });
    });

    expect(h.current.value.config.provider).toBe("anthropic");
    expect(h.current.value.config.deepModel).toBe("claude-opus");
    expect(h.current.value.serverDefaults).toMatchObject({
      provider: "nvidia",
      deepModel: "nvidia/nemotron-3-ultra-550b-a55b",
    });
    h.unmount();
  });

  it("setConfig writes through to localStorage", () => {
    const h = renderHook(() => useLlmConfig());
    act(() => {
      h.current.value.setConfig({ provider: "openrouter" });
    });
    expect(storageBacking["ta:llm.provider"]).toBe("openrouter");
    h.unmount();
  });
});

describe("LlmPicker (component smoke)", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    // Default provider in tests is openai → no discovery call expected. If a provider
    // change triggers one, just return an empty list so the picker stays stable.
    vi.spyOn(api, "fetchProviderModels").mockResolvedValue({
      provider: "openrouter",
      source: "test",
      models: [],
    });
  });

  it("renders provider dropdown and forwards changes through onChange", () => {
    const el = document.createElement("div");
    document.body.appendChild(el);
    const onChange = vi.fn();
    const value: LlmConfig = {
      provider: "openai",
      deepModel: "gpt-5",
      quickModel: "gpt-4o-mini",
      backendUrl: "",
      openrouterFreeOnly: false,
    };

    act(() => {
      createRoot(el).render(
        <StrictMode>
          <LlmPicker value={value} onChange={onChange} />
        </StrictMode>,
      );
    });

    const select = el.querySelector("select") as HTMLSelectElement | null;
    expect(select).toBeTruthy();
    expect(select!.value).toBe("openai");

    act(() => {
      select!.value = "anthropic";
      select!.dispatchEvent(new Event("change", { bubbles: true }));
    });

    expect(onChange).toHaveBeenCalled();
    expect(onChange.mock.calls[0][0]).toMatchObject({ provider: "anthropic" });
    el.remove();
  });
});
