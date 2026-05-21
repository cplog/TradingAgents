import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi, beforeEach } from "vitest";
import * as api from "./api";
import { SectorIndustryPage } from "./pages/SectorIndustryPage";

describe("SectorIndustryPage", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("loads coverage, auto-selects first industry, and loads constituents", async () => {
    vi.spyOn(api, "fetchHistoryCoverage").mockResolvedValue([
      {
        sector: "Technology",
        industry: "Semiconductors",
        run_count: 2,
        with_dimensions_count: 2,
        with_commentary_count: 1,
        latest_completed_at: "2026-05-01T00:00:00Z",
      },
    ]);
    vi.spyOn(api, "fetchIndustryConstituents").mockResolvedValue([
      {
        ticker: "NVDA",
        market: "US",
        run_count: 1,
        has_report: true,
        has_dimensions: true,
        has_commentary: false,
        latest_rating: "Hold",
        latest_date: "2026-05-01",
        latest_run_id: "j1",
      },
      {
        ticker: "AMD",
        market: "US",
        run_count: 0,
        has_report: false,
        has_dimensions: false,
        has_commentary: false,
      },
    ]);

    render(
      <MemoryRouter initialEntries={["/sectors"]}>
        <SectorIndustryPage />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(api.fetchHistoryCoverage).toHaveBeenCalled();
    });

    await waitFor(() => {
      expect(api.fetchIndustryConstituents).toHaveBeenCalledWith({
        sector: "Technology",
        industry: "Semiconductors",
      });
    });

    expect(screen.getByText("NVDA")).toBeDefined();
    expect(screen.getByText("AMD")).toBeDefined();
    // Coverage now renders as accessible dots — NVDA has report yes, AMD has report no.
    expect(screen.getAllByLabelText("report yes")).toHaveLength(1);
    expect(screen.getAllByLabelText("report no")).toHaveLength(1);
  });

  it("reloads constituents when market filter changes", async () => {
    vi.spyOn(api, "fetchHistoryCoverage").mockResolvedValue([
      {
        sector: "Technology",
        industry: "Semiconductors",
        run_count: 0,
        with_dimensions_count: 0,
        with_commentary_count: 0,
      },
    ]);
    const fetchConst = vi.spyOn(api, "fetchIndustryConstituents").mockResolvedValue([]);

    render(
      <MemoryRouter initialEntries={["/sectors"]}>
        <SectorIndustryPage />
      </MemoryRouter>,
    );

    await waitFor(() => expect(fetchConst).toHaveBeenCalled());

    fireEvent.click(screen.getAllByRole("button", { name: "Market HK" })[0]!);

    await waitFor(() => {
      expect(fetchConst).toHaveBeenLastCalledWith({
        sector: "Technology",
        industry: "Semiconductors",
        market: "HK",
      });
    });
  });
});
