import { act, StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import * as api from "./api";
import { BatchPage } from "./pages/BatchPage";

describe("BatchPage topic banner", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(api, "fetchHealth").mockResolvedValue({
      ok: true,
      llm_provider: "openai",
      api_key_configured: true,
      state_store: "local",
      cloudflare_kv_configured: false,
      data_cache_dir: "/tmp",
      results_dir: "/tmp",
      yfinance_reachable: true,
      supported_analyst_ids: ["market", "news"],
    });
    vi.spyOn(api, "fetchConfig").mockResolvedValue({});
  });

  it("shows topic banner when ?topic= is present", async () => {
    const el = document.createElement("div");
    document.body.appendChild(el);

    await act(async () => {
      createRoot(el).render(
        <StrictMode>
          <MemoryRouter initialEntries={["/batch?tickers=NVDA&topic=ai-infrastructure"]}>
            <BatchPage />
          </MemoryRouter>
        </StrictMode>,
      );
    });

    await act(async () => {
      await Promise.resolve();
    });

    expect(el.textContent).toContain("From topic");
    expect(el.textContent).toContain("ai-infrastructure");
  });
});
