import { act, StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import * as api from "./api";
import { TopicDetailPage } from "./pages/TopicDetailPage";

describe("TopicDetailPage", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("shows theme summary and candidates", async () => {
    vi.spyOn(api, "fetchTopic").mockResolvedValue({
      topic: {
        id: "ai-infrastructure",
        label: "AI Infrastructure",
        query: "AI data center GPU",
        cadence: "daily",
        pinned: false,
        source: "seed",
        created_at: "2026-05-01T00:00:00Z",
        updated_at: "2026-05-01T00:00:00Z",
        last_run_at: "2026-05-01T01:00:00Z",
      },
      latest_run: {
        run_id: "abc",
        topic_id: "ai-infrastructure",
        started_at: "2026-05-01T01:00:00Z",
        completed_at: "2026-05-01T01:01:00Z",
        status: "completed",
        articles: [{ title: "NVDA leads", url: "https://example.com" }],
        candidates: [
          { ticker: "NVDA", confidence: 0.88, market: "us", rationale: "GPU leader" },
        ],
        theme_summary: "AI infra demand remains strong.",
      },
    });
    vi.spyOn(api, "fetchTopicRuns").mockResolvedValue({ runs: [] });

    const el = document.createElement("div");
    document.body.appendChild(el);

    await act(async () => {
      createRoot(el).render(
        <StrictMode>
          <MemoryRouter initialEntries={["/topics/ai-infrastructure"]}>
            <Routes>
              <Route path="/topics/:topicId" element={<TopicDetailPage />} />
            </Routes>
          </MemoryRouter>
        </StrictMode>,
      );
    });

    await act(async () => {
      await Promise.resolve();
    });

    expect(el.textContent).toContain("AI Infrastructure");
    expect(el.textContent).toContain("AI infra demand remains strong");
    expect(el.textContent).toContain("NVDA");
    expect(el.textContent).toContain("Batch analyze");
  });
});
