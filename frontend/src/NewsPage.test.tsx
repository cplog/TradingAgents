import { act, StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import * as api from "./api";
import { NewsPage } from "./pages/NewsPage";

describe("NewsPage related themes", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(api, "fetchTopics").mockResolvedValue({
      topics: [
        {
          id: "ai-infrastructure",
          label: "AI Infrastructure",
          query: "AI data center",
          cadence: "daily",
          pinned: true,
          source: "seed",
          candidate_count: 2,
          top_candidates: [],
        },
      ],
    });
  });

  it("renders related theme chips", async () => {
    const el = document.createElement("div");
    document.body.appendChild(el);

    await act(async () => {
      createRoot(el).render(
        <StrictMode>
          <MemoryRouter initialEntries={["/news"]}>
            <NewsPage />
          </MemoryRouter>
        </StrictMode>,
      );
    });

    await act(async () => {
      await Promise.resolve();
    });

    expect(el.textContent).toContain("Related themes");
    expect(el.textContent).toContain("AI Infrastructure");
  });
});
