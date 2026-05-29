import { act, StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import * as api from "./api";
import { TopicsPage } from "./pages/TopicsPage";

describe("TopicsPage", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("renders pinned and trending sections", async () => {
    vi.spyOn(api, "fetchTopics").mockResolvedValue({
      topics: [
        {
          id: "ai-infrastructure",
          label: "AI Infrastructure",
          query: "AI data center",
          cadence: "daily",
          pinned: true,
          source: "seed",
          candidate_count: 3,
          top_candidates: [{ ticker: "NVDA", confidence: 0.9, market: "us" }],
        },
        {
          id: "nuclear-energy",
          label: "Nuclear Renaissance",
          query: "nuclear SMR",
          cadence: "weekly",
          pinned: false,
          source: "seed",
          candidate_count: 1,
          top_candidates: [],
        },
      ],
    });

    const el = document.createElement("div");
    document.body.appendChild(el);

    await act(async () => {
      createRoot(el).render(
        <StrictMode>
          <MemoryRouter initialEntries={["/topics"]}>
            <TopicsPage />
          </MemoryRouter>
        </StrictMode>,
      );
    });

    await act(async () => {
      await Promise.resolve();
    });

    expect(el.textContent).toContain("Hot Ideas");
    expect(el.textContent).toContain("AI Infrastructure");
    expect(el.textContent).toContain("Pinned");
    expect(el.textContent).toContain("Nuclear Renaissance");
  });
});
