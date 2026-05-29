import { act, StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import * as api from "./api";
import { MonitorPage } from "./pages/MonitorPage";

describe("MonitorPage", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(api, "fetchMonitorStatus").mockResolvedValue({
      enabled: false,
      session: "regular",
      should_poll: false,
      poll_seconds: 900,
      threshold: 75,
      watchlist: [],
      last_tick: null,
      last_candidates: [],
      last_errors: [],
      cooldown_tickers: [],
    });
    vi.spyOn(api, "fetchMonitorWatchlist").mockResolvedValue({ tickers: [] });
    vi.spyOn(api, "fetchMonitorSignals").mockResolvedValue({ signals: [] });
  });

  it("explains disabled monitor and distinguishes from browser watchlists", async () => {
    const el = document.createElement("div");
    document.body.appendChild(el);

    await act(async () => {
      createRoot(el).render(
        <StrictMode>
          <MemoryRouter initialEntries={["/monitor"]}>
            <MonitorPage />
          </MemoryRouter>
        </StrictMode>,
      );
    });

    await act(async () => {
      await Promise.resolve();
    });

    expect(el.textContent).toContain("TRADINGAGENTS_MONITOR_ENABLED=true");
    expect(el.textContent).toContain("Watchlists");
    expect(el.textContent).toContain("Add at least one ticker");
    expect(el.textContent).toContain("No triggered signals yet");
  });
});
