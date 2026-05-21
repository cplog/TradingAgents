import { act, StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import * as api from "./api";
import { DashboardPage } from "./pages/DashboardPage";

async function renderWithRoutes(initialEntry: string) {
  const el = document.createElement("div");
  document.body.appendChild(el);
  await act(async () => {
    createRoot(el).render(
      <StrictMode>
        <MemoryRouter initialEntries={[initialEntry]}>
          <Routes>
            <Route path="/dashboard" element={<DashboardPage />} />
            <Route path="/runs/:jobId" element={<div data-testid="run-page">Run page</div>} />
          </Routes>
        </MemoryRouter>
      </StrictMode>,
    );
  });
  return el;
}

describe("DashboardPage", () => {
  let storageBacking: Record<string, string>;

  beforeEach(() => {
    vi.restoreAllMocks();
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
    vi.spyOn(api, "fetchHealth").mockResolvedValue({
      ok: true,
      llm_provider: "openai",
      api_key_configured: true,
      state_store: "local_file",
      cloudflare_kv_configured: false,
      data_cache_dir: "/tmp",
      results_dir: "/tmp",
      yfinance_reachable: true,
      supported_analyst_ids: ["market", "social", "news", "fundamentals"],
    });
    vi.spyOn(api, "fetchConfig").mockResolvedValue({});
  });

  it("ignores stale ta:lastJobId so /dashboard always lands on the form", async () => {
    window.localStorage.setItem("ta:lastJobId", "old123");

    const el = await renderWithRoutes("/dashboard");

    await act(async () => {
      await Promise.resolve();
    });

    expect(el.querySelector("[data-testid=run-page]")).toBeFalsy();
    expect(el.textContent).toContain("Start analysis");
  });

  it("redirects ?job= deep link to the run page", async () => {
    const getJob = vi.spyOn(api, "getJob");
    const el = await renderWithRoutes("/dashboard?job=deeplink99");

    await act(async () => {
      await Promise.resolve();
    });

    expect(el.querySelector("[data-testid=run-page]")).toBeTruthy();
    expect(getJob).not.toHaveBeenCalled();
  });

  it("renders the analysis launcher when no job deep link is present", async () => {
    const el = await renderWithRoutes("/dashboard");

    await act(async () => {
      await Promise.resolve();
    });

    expect(el.querySelector("[data-testid=run-page]")).toBeFalsy();
    expect(el.textContent).toContain("Start analysis");
  });
});
