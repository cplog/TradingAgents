import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { dashboardPath, runsPath, stocksPath } from "../navigation/routes";
import type { CatalogStatus, HistoryCoverageRow, IndustryConstituentRow } from "../api";
import {
  fetchCatalogStatus,
  fetchHistoryCoverage,
  fetchIndustryConstituents,
} from "../api";

function formatCatalogAge(epochSeconds: number | null | undefined): {
  label: string;
  tone: "fresh" | "ok" | "stale";
} | null {
  if (epochSeconds == null || !Number.isFinite(epochSeconds) || epochSeconds <= 0) return null;
  const ageDays = Math.max(0, Math.floor((Date.now() / 1000 - epochSeconds) / 86400));
  const label =
    ageDays <= 0 ? "today" : ageDays === 1 ? "1 day ago" : `${ageDays} days ago`;
  // Cron runs weekly; tolerate one missed run before nagging.
  const tone: "fresh" | "ok" | "stale" =
    ageDays <= 8 ? "fresh" : ageDays <= 21 ? "ok" : "stale";
  return { label, tone };
}

type SectorGroup = { sector: string; rows: HistoryCoverageRow[]; run_count: number };
type MarketFilter = "ALL" | "US" | "HK";
type ConstituentFilter = "ALL" | "ANALYZED" | "UNANALYZED";

function sortGroups(coverage: HistoryCoverageRow[]): SectorGroup[] {
  const m = new Map<string, HistoryCoverageRow[]>();
  for (const row of coverage) {
    const s = row.sector || "(unknown)";
    if (!m.has(s)) m.set(s, []);
    m.get(s)!.push(row);
  }
  return Array.from(m.entries())
    .map(([sector, rows]) => ({
      sector,
      run_count: rows.reduce((n, r) => n + (r.run_count || 0), 0),
      rows: rows.sort((a, b) => {
        // with-runs first, then alphabetical
        const da = (b.run_count || 0) - (a.run_count || 0);
        if (da !== 0) return da;
        return `${a.industry}`.localeCompare(b.industry, undefined, { sensitivity: "base" });
      }),
    }))
    .sort((a, b) => {
      const da = b.run_count - a.run_count;
      if (da !== 0) return da;
      return a.sector.localeCompare(b.sector, undefined, { sensitivity: "base" });
    });
}

const panelStyle: React.CSSProperties = {
  background: "var(--surface-cloud-white)",
  padding: "var(--card-padding)",
  borderRadius: "var(--radius-cards)",
  border: "1px solid var(--color-stone-border)",
  boxShadow: "var(--shadow-subtle)",
  minHeight: 480,
  display: "flex",
  flexDirection: "column",
};

const listBtn = (active: boolean, hasRuns: boolean): React.CSSProperties => ({
  display: "block",
  width: "100%",
  textAlign: "left",
  padding: "8px 10px",
  marginBottom: 4,
  borderRadius: "var(--radius-buttons)",
  border: active
    ? "1px solid var(--color-phosphor)"
    : hasRuns
      ? "1px solid rgba(120, 240, 168, 0.28)"
      : "1px solid transparent",
  background: active
    ? "var(--color-phosphor-glow)"
    : hasRuns
      ? "rgba(120, 240, 168, 0.05)"
      : "transparent",
  color: active ? "var(--color-phosphor)" : "var(--color-slate-text)",
  cursor: "pointer",
  fontSize: "var(--text-body-sm)",
  fontWeight: active ? 600 : 500,
});

function RunsPill({ count }: { count: number }) {
  if (count <= 0) return null;
  return (
    <span
      style={{
        display: "inline-block",
        marginLeft: 6,
        fontSize: "var(--text-caption)",
        padding: "1px 6px",
        borderRadius: 999,
        background: "rgba(120, 240, 168, 0.18)",
        color: "var(--color-phosphor)",
        border: "1px solid rgba(120, 240, 168, 0.45)",
        fontWeight: 600,
      }}
      aria-label={`${count} runs`}
    >
      {count}
    </span>
  );
}

function CoverageDots({
  hasReport,
  hasDims,
  hasComm,
}: {
  hasReport?: boolean | null;
  hasDims?: boolean | null;
  hasComm?: boolean | null;
}) {
  const dot = (on: boolean, label: string, color: string) => (
    <span
      title={`${label}: ${on ? "yes" : "no"}`}
      aria-label={`${label} ${on ? "yes" : "no"}`}
      style={{
        display: "inline-block",
        width: 9,
        height: 9,
        borderRadius: 999,
        background: on ? color : "transparent",
        border: on ? "none" : "1px solid var(--color-platinum-outline)",
        boxShadow: on ? `0 0 6px ${color}66` : "none",
      }}
    />
  );
  return (
    <span style={{ display: "inline-flex", gap: 5, alignItems: "center" }}>
      {dot(!!hasReport, "report", "#78f0a8")}
      {dot(!!hasDims, "dimensions", "#38bdf8")}
      {dot(!!hasComm, "commentary", "#c4b5fd")}
    </span>
  );
}

const segBtn = (active: boolean): React.CSSProperties => ({
  padding: "4px 10px",
  borderRadius: "var(--radius-buttons)",
  border: active
    ? "1px solid var(--color-phosphor)"
    : "1px solid var(--color-platinum-outline)",
  background: active ? "var(--color-phosphor-glow)" : "var(--surface-elevated)",
  color: active ? "var(--color-phosphor)" : "var(--color-slate-text)",
  fontSize: "var(--text-caption)",
  fontWeight: 600,
  cursor: "pointer",
});

export function SectorIndustryPage() {
  const navigate = useNavigate();

  const [coverage, setCoverage] = useState<HistoryCoverageRow[]>([]);
  const [covLoading, setCovLoading] = useState(true);
  const [covError, setCovError] = useState<string | null>(null);

  const [sectorSearch, setSectorSearch] = useState("");
  const [onlyWithRuns, setOnlyWithRuns] = useState(false);
  const [selectedSector, setSelectedSector] = useState<string | null>(null);
  const [selectedIndustry, setSelectedIndustry] = useState<string | null>(null);

  const [marketFilter, setMarketFilter] = useState<MarketFilter>("ALL");
  const [constFilter, setConstFilter] = useState<ConstituentFilter>("ALL");
  const [tickerSearch, setTickerSearch] = useState("");

  const [constituents, setConstituents] = useState<IndustryConstituentRow[]>([]);
  const [constLoading, setConstLoading] = useState(false);
  const [constError, setConstError] = useState<string | null>(null);

  const [selectedTickers, setSelectedTickers] = useState<Set<string>>(new Set());

  const [catalogStatus, setCatalogStatus] = useState<CatalogStatus | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setCovLoading(true);
      setCovError(null);
      try {
        const rows = await fetchHistoryCoverage();
        if (!cancelled) setCoverage(rows);
      } catch (e: unknown) {
        const msg = e instanceof Error ? e.message : String(e);
        if (!cancelled) setCovError(msg);
      } finally {
        if (!cancelled) setCovLoading(false);
      }
    }
    void load();
    void fetchCatalogStatus()
      .then((s) => {
        if (!cancelled) setCatalogStatus(s);
      })
      .catch(() => {
        if (!cancelled) setCatalogStatus(null);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const grouped = useMemo(() => sortGroups(coverage), [coverage]);

  const overall = useMemo(() => {
    const runs = coverage.reduce((n, r) => n + (r.run_count || 0), 0);
    const industries = coverage.filter((r) => (r.run_count || 0) > 0).length;
    const sectors = new Set(
      coverage.filter((r) => (r.run_count || 0) > 0).map((r) => r.sector || "(unknown)"),
    ).size;
    return { runs, industries, sectors, buckets: coverage.length };
  }, [coverage]);

  const filteredSectors = useMemo(() => {
    const q = sectorSearch.trim().toLowerCase();
    let groups = grouped;
    if (onlyWithRuns) groups = groups.filter((g) => g.run_count > 0);
    if (!q) return groups;
    return groups.filter(
      (g) =>
        g.sector.toLowerCase().includes(q) ||
        g.rows.some((r) => r.industry.toLowerCase().includes(q)),
    );
  }, [grouped, sectorSearch, onlyWithRuns]);

  const industriesForSector = useMemo(() => {
    if (!selectedSector) return [];
    const rows = grouped.find((g) => g.sector === selectedSector)?.rows ?? [];
    return onlyWithRuns ? rows.filter((r) => (r.run_count || 0) > 0) : rows;
  }, [grouped, selectedSector, onlyWithRuns]);

  // Auto-select first sector AND industry that have runs; fall back to alphabetical.
  useEffect(() => {
    if (covLoading || grouped.length === 0 || selectedSector) return;
    const withRuns = grouped.find((g) => g.run_count > 0) ?? grouped[0];
    setSelectedSector(withRuns.sector);
    const firstIndustry =
      withRuns.rows.find((r) => (r.run_count || 0) > 0)?.industry ??
      withRuns.rows[0]?.industry ??
      null;
    setSelectedIndustry(firstIndustry);
  }, [covLoading, grouped, selectedSector]);

  const selectSector = useCallback(
    (sector: string) => {
      setSelectedSector(sector);
      const rows = grouped.find((g) => g.sector === sector)?.rows ?? [];
      const firstWithRuns = rows.find((r) => (r.run_count || 0) > 0);
      setSelectedIndustry(firstWithRuns?.industry ?? rows[0]?.industry ?? null);
      setSelectedTickers(new Set());
    },
    [grouped],
  );

  const selectIndustry = useCallback((sector: string, industry: string) => {
    setSelectedSector(sector);
    setSelectedIndustry(industry);
    setTickerSearch("");
    setSelectedTickers(new Set());
  }, []);

  useEffect(() => {
    if (!selectedSector || !selectedIndustry) {
      setConstituents([]);
      setConstError(null);
      return;
    }
    let cancelled = false;
    async function loadConstituents() {
      setConstLoading(true);
      setConstError(null);
      try {
        const rows = await fetchIndustryConstituents({
          sector: selectedSector!,
          industry: selectedIndustry!,
          market: marketFilter === "ALL" ? undefined : marketFilter,
        });
        if (!cancelled) setConstituents(rows);
      } catch (e: unknown) {
        const msg = e instanceof Error ? e.message : String(e);
        if (!cancelled) setConstError(msg);
      } finally {
        if (!cancelled) setConstLoading(false);
      }
    }
    void loadConstituents();
    return () => {
      cancelled = true;
    };
  }, [selectedSector, selectedIndustry, marketFilter]);

  // Sort: has_report first, then latest_completed_at desc, then ticker asc.
  const sortedConstituents = useMemo(() => {
    return [...constituents].sort((a, b) => {
      if (!!b.has_report !== !!a.has_report) return b.has_report ? 1 : -1;
      const ta = a.latest_completed_at || "";
      const tb = b.latest_completed_at || "";
      if (ta !== tb) return ta > tb ? -1 : 1;
      return a.ticker.localeCompare(b.ticker);
    });
  }, [constituents]);

  const filteredConstituents = useMemo(() => {
    let rows = sortedConstituents;
    if (constFilter === "ANALYZED") rows = rows.filter((c) => c.has_report);
    else if (constFilter === "UNANALYZED") rows = rows.filter((c) => !c.has_report);
    const q = tickerSearch.trim().toUpperCase();
    if (q) rows = rows.filter((c) => c.ticker.includes(q));
    return rows;
  }, [sortedConstituents, constFilter, tickerSearch]);

  const summary = useMemo(() => {
    const withReport = constituents.filter((c) => c.has_report).length;
    const withDims = constituents.filter((c) => c.has_dimensions).length;
    return { total: constituents.length, withReport, withDims };
  }, [constituents]);

  const toggleTicker = useCallback((ticker: string) => {
    setSelectedTickers((prev) => {
      const next = new Set(prev);
      if (next.has(ticker)) next.delete(ticker);
      else next.add(ticker);
      return next;
    });
  }, []);

  const toggleAllVisible = useCallback(() => {
    setSelectedTickers((prev) => {
      const visible = filteredConstituents.map((c) => c.ticker);
      const allSelected = visible.length > 0 && visible.every((t) => prev.has(t));
      if (allSelected) {
        const next = new Set(prev);
        for (const t of visible) next.delete(t);
        return next;
      }
      const next = new Set(prev);
      for (const t of visible) next.add(t);
      return next;
    });
  }, [filteredConstituents]);

  const launchBulkAnalyze = useCallback(() => {
    if (selectedTickers.size === 0) return;
    const csv = Array.from(selectedTickers).sort().join(",");
    navigate(`/batch?tickers=${encodeURIComponent(csv)}`);
  }, [navigate, selectedTickers]);

  const visibleAllSelected =
    filteredConstituents.length > 0 &&
    filteredConstituents.every((c) => selectedTickers.has(c.ticker));

  return (
    <div style={{ maxWidth: "1440px" }}>
      <header style={{ marginBottom: "var(--spacing-16)" }}>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 12, alignItems: "center" }}>
          <h1 style={{ margin: 0, fontSize: "var(--text-heading-lg)" }}>
            Sector / industry explorer
          </h1>
          {(() => {
            const ts =
              catalogStatus?.latest_constituent_refreshed_at ??
              catalogStatus?.latest_bucket_refreshed_at ??
              null;
            const age = formatCatalogAge(ts);
            if (!age) return null;
            const palette =
              age.tone === "fresh"
                ? {
                    border: "1px solid rgba(120, 240, 168, 0.45)",
                    background: "rgba(120, 240, 168, 0.14)",
                    color: "var(--color-phosphor)",
                  }
                : age.tone === "ok"
                  ? {
                      border: "1px solid var(--color-platinum-outline)",
                      background: "var(--surface-elevated)",
                      color: "var(--color-slate-text)",
                    }
                  : {
                      border: "1px solid rgba(245, 158, 11, 0.45)",
                      background: "rgba(245, 158, 11, 0.10)",
                      color: "var(--color-amber-readout)",
                    };
            return (
              <span
                title={
                  "Latest constituents refresh in Cloudflare D1. " +
                  "A scheduled GitHub Action re-runs scripts/cold_start_yahoo_sectors.py weekly."
                }
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 6,
                  padding: "2px 10px",
                  borderRadius: 999,
                  fontSize: "var(--text-caption)",
                  fontWeight: 600,
                  letterSpacing: "0.02em",
                  ...palette,
                }}
              >
                <span aria-hidden="true">●</span>
                Catalog refreshed {age.label}
              </span>
            );
          })()}
          {catalogStatus && !catalogStatus.d1_enabled && (
            <span
              title="Cloudflare D1 is not configured; the explorer is reading from disk cache or baseline."
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 6,
                padding: "2px 10px",
                borderRadius: 999,
                fontSize: "var(--text-caption)",
                fontWeight: 600,
                border: "1px solid var(--color-platinum-outline)",
                background: "var(--surface-elevated)",
                color: "var(--color-ash-gray)",
              }}
            >
              D1 disabled
            </span>
          )}
        </div>
        <p style={{ margin: "8px 0 0", color: "var(--color-ash-gray)" }}>
          Browse the full Yahoo catalog or filter to industries you&apos;ve already analyzed. Select
          multiple tickers and queue them as a batch analysis.
        </p>
        {!covLoading && !covError && (
          <p
            style={{
              margin: "8px 0 0",
              fontSize: "var(--text-body-sm)",
              color: "var(--color-slate-text)",
            }}
          >
            <strong>{overall.runs}</strong> persisted runs across{" "}
            <strong>{overall.industries}</strong> industries in{" "}
            <strong>{overall.sectors}</strong> sectors · catalog covers {overall.buckets} buckets.
          </p>
        )}
      </header>

      {covLoading && <p style={{ color: "var(--color-ash-gray)" }}>Loading catalog…</p>}
      {covError && (
        <p style={{ color: "var(--color-amber-readout)", fontSize: "var(--text-body-sm)" }}>
          Could not load coverage: {covError}
        </p>
      )}

      {!covLoading && !covError && (
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "minmax(180px, 220px) minmax(220px, 280px) minmax(0, 1fr)",
            gap: "var(--spacing-12)",
            alignItems: "stretch",
          }}
        >
          <section style={panelStyle}>
            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                marginBottom: 6,
              }}
            >
              <h2 style={{ margin: 0, fontSize: "var(--text-heading-sm)" }}>Sectors</h2>
              <label
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 4,
                  fontSize: "var(--text-caption)",
                  color: "var(--color-ash-gray)",
                  cursor: "pointer",
                }}
              >
                <input
                  type="checkbox"
                  checked={onlyWithRuns}
                  onChange={(e) => setOnlyWithRuns(e.target.checked)}
                />
                only with runs
              </label>
            </div>
            <input
              type="search"
              placeholder="Filter…"
              value={sectorSearch}
              onChange={(e) => setSectorSearch(e.target.value)}
              style={{
                width: "100%",
                marginBottom: 10,
                padding: "8px 10px",
                borderRadius: "var(--radius-buttons)",
                border: "1px solid var(--color-platinum-outline)",
                fontSize: "var(--text-body-sm)",
              }}
            />
            <div style={{ overflowY: "auto", flex: 1 }}>
              {filteredSectors.length === 0 && (
                <p style={{ color: "var(--color-ash-gray)", fontSize: "var(--text-body-sm)" }}>
                  No matches.
                </p>
              )}
              {filteredSectors.map(({ sector, rows, run_count }) => {
                const active = selectedSector === sector;
                const industriesWithRuns = rows.filter((r) => (r.run_count || 0) > 0).length;
                return (
                  <button
                    key={sector}
                    type="button"
                    onClick={() => selectSector(sector)}
                    style={listBtn(active, run_count > 0)}
                  >
                    <div
                      style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}
                    >
                      <span>{sector}</span>
                      <RunsPill count={run_count} />
                    </div>
                    <div
                      style={{ fontSize: "var(--text-caption)", color: "var(--color-ash-gray)" }}
                    >
                      {rows.length} industries
                      {industriesWithRuns > 0 ? ` · ${industriesWithRuns} analyzed` : ""}
                    </div>
                  </button>
                );
              })}
            </div>
          </section>

          <section style={panelStyle}>
            <h2 style={{ margin: "0 0 8px", fontSize: "var(--text-heading-sm)" }}>Industries</h2>
            {!selectedSector && (
              <p style={{ color: "var(--color-ash-gray)", fontSize: "var(--text-body-sm)" }}>
                Select a sector.
              </p>
            )}
            <div style={{ overflowY: "auto", flex: 1 }}>
              {industriesForSector.length === 0 && selectedSector && (
                <p style={{ color: "var(--color-ash-gray)", fontSize: "var(--text-body-sm)" }}>
                  No matching industries{onlyWithRuns ? " with runs" : ""}.
                </p>
              )}
              {industriesForSector.map((r) => {
                const active =
                  selectedSector === r.sector && selectedIndustry === r.industry;
                return (
                  <button
                    key={`${r.sector}|${r.industry}`}
                    type="button"
                    onClick={() => selectIndustry(r.sector, r.industry)}
                    style={listBtn(active, (r.run_count || 0) > 0)}
                  >
                    <div
                      style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}
                    >
                      <span>{r.industry}</span>
                      <RunsPill count={r.run_count || 0} />
                    </div>
                    <div
                      style={{ fontSize: "var(--text-caption)", color: "var(--color-ash-gray)" }}
                    >
                      {r.run_count > 0
                        ? `dims ${r.with_dimensions_count} · notes ${r.with_commentary_count}`
                        : "no runs yet"}
                    </div>
                  </button>
                );
              })}
            </div>
          </section>

          <section style={panelStyle}>
            <div
              style={{
                display: "flex",
                flexWrap: "wrap",
                alignItems: "center",
                gap: 10,
                marginBottom: 10,
              }}
            >
              <h2 style={{ margin: 0, fontSize: "var(--text-heading-sm)", flex: "1 1 auto" }}>
                Constituents
                {selectedIndustry ? (
                  <span
                    style={{
                      display: "block",
                      fontWeight: 400,
                      fontSize: "var(--text-caption)",
                      color: "var(--color-ash-gray)",
                    }}
                  >
                    {selectedSector} · {selectedIndustry}
                  </span>
                ) : null}
              </h2>
              <div style={{ display: "flex", gap: 4 }}>
                {(["ALL", "US", "HK"] as const).map((m) => (
                  <button
                    key={m}
                    type="button"
                    aria-label={`Market ${m}`}
                    onClick={() => setMarketFilter(m)}
                    style={segBtn(marketFilter === m)}
                  >
                    {m}
                  </button>
                ))}
              </div>
            </div>

            {!selectedIndustry && (
              <p style={{ color: "var(--color-ash-gray)" }}>Select an industry to list tickers.</p>
            )}

            {selectedIndustry && (
              <>
                <div
                  style={{
                    display: "flex",
                    flexWrap: "wrap",
                    gap: 8,
                    alignItems: "center",
                    marginBottom: 8,
                  }}
                >
                  <input
                    type="search"
                    placeholder="Filter tickers…"
                    value={tickerSearch}
                    onChange={(e) => setTickerSearch(e.target.value)}
                    style={{
                      flex: "1 1 200px",
                      padding: "8px 10px",
                      borderRadius: "var(--radius-buttons)",
                      border: "1px solid var(--color-platinum-outline)",
                      fontSize: "var(--text-body-sm)",
                    }}
                  />
                  <div style={{ display: "flex", gap: 4 }}>
                    {(
                      [
                        ["ALL", "All"],
                        ["ANALYZED", "Analyzed"],
                        ["UNANALYZED", "Un-analyzed"],
                      ] as const
                    ).map(([key, label]) => (
                      <button
                        key={key}
                        type="button"
                        onClick={() => setConstFilter(key)}
                        style={segBtn(constFilter === key)}
                      >
                        {label}
                      </button>
                    ))}
                  </div>
                </div>
                <div
                  style={{
                    display: "flex",
                    flexWrap: "wrap",
                    alignItems: "center",
                    justifyContent: "space-between",
                    gap: 8,
                    marginBottom: 10,
                    fontSize: "var(--text-caption)",
                    color: "var(--color-ash-gray)",
                  }}
                >
                  <span>
                    {filteredConstituents.length} of {summary.total} tickers ·{" "}
                    {summary.withReport} with reports · {summary.withDims} with dimensions
                  </span>
                  {selectedTickers.size > 0 && (
                    <span
                      style={{
                        display: "inline-flex",
                        alignItems: "center",
                        gap: 8,
                      }}
                    >
                      <strong style={{ color: "var(--color-slate-text)" }}>
                        {selectedTickers.size} selected
                      </strong>
                      <button
                        type="button"
                        onClick={() => setSelectedTickers(new Set())}
                        style={{
                          background: "transparent",
                          border: "none",
                          color: "var(--color-chartwell-blue)",
                          cursor: "pointer",
                          padding: 0,
                          fontSize: "var(--text-caption)",
                        }}
                      >
                        clear
                      </button>
                      <button
                        type="button"
                        onClick={launchBulkAnalyze}
                        style={{
                          padding: "4px 10px",
                          background: "var(--color-phosphor)",
                          color: "var(--color-deep-space)",
                          border: "1px solid var(--color-phosphor-dim)",
                          borderRadius: "var(--radius-buttons)",
                          cursor: "pointer",
                          fontWeight: 600,
                          fontSize: "var(--text-caption)",
                        }}
                      >
                        Analyze {selectedTickers.size} in batch
                      </button>
                    </span>
                  )}
                </div>
                {constLoading && (
                  <p style={{ color: "var(--color-ash-gray)" }}>Loading tickers…</p>
                )}
                {constError && (
                  <p style={{ color: "var(--color-amber-readout)", fontSize: "var(--text-body-sm)" }}>{constError}</p>
                )}
                {!constLoading && !constError && filteredConstituents.length === 0 && (
                  <p style={{ color: "var(--color-ash-gray)" }}>
                    {constituents.length === 0 ? (
                      <>
                        No constituents for this slice. Run{" "}
                        <code>scripts/cold_start_yahoo_sectors.py --constituents</code> to populate
                        D1.
                      </>
                    ) : (
                      "No tickers match the current filter."
                    )}
                  </p>
                )}
                {!constLoading && filteredConstituents.length > 0 && (
                  <div style={{ overflow: "auto", flex: 1 }}>
                    <table
                      style={{
                        width: "100%",
                        borderCollapse: "collapse",
                        fontSize: "var(--text-body-sm)",
                      }}
                    >
                      <thead>
                        <tr style={{ textAlign: "left", color: "var(--color-ash-gray)" }}>
                          <th
                            style={{
                              padding: "6px 4px",
                              borderBottom: "1px solid var(--color-platinum-outline)",
                              width: 28,
                            }}
                          >
                            <input
                              type="checkbox"
                              checked={visibleAllSelected}
                              ref={(el) => {
                                if (el) {
                                  const any = filteredConstituents.some((c) =>
                                    selectedTickers.has(c.ticker),
                                  );
                                  el.indeterminate = any && !visibleAllSelected;
                                }
                              }}
                              onChange={toggleAllVisible}
                              aria-label="Select all visible"
                            />
                          </th>
                          <th
                            style={{
                              padding: "6px 4px",
                              borderBottom: "1px solid var(--color-platinum-outline)",
                            }}
                          >
                            Ticker
                          </th>
                          <th
                            style={{
                              padding: "6px 4px",
                              borderBottom: "1px solid var(--color-platinum-outline)",
                            }}
                          >
                            Mkt
                          </th>
                          <th
                            style={{
                              padding: "6px 4px",
                              borderBottom: "1px solid var(--color-platinum-outline)",
                            }}
                          >
                            Coverage
                          </th>
                          <th
                            style={{
                              padding: "6px 4px",
                              borderBottom: "1px solid var(--color-platinum-outline)",
                            }}
                          >
                            Latest
                          </th>
                          <th
                            style={{
                              padding: "6px 4px",
                              borderBottom: "1px solid var(--color-platinum-outline)",
                            }}
                          />
                        </tr>
                      </thead>
                      <tbody>
                        {filteredConstituents.map((c) => {
                          const selected = selectedTickers.has(c.ticker);
                          return (
                            <tr
                              key={`${c.market}-${c.ticker}`}
                              style={
                                selected
                                  ? { background: "var(--color-phosphor-glow)" }
                                  : c.has_report
                                    ? { background: "rgba(120, 240, 168, 0.05)" }
                                    : undefined
                              }
                            >
                              <td
                                style={{
                                  padding: "8px 4px",
                                  borderBottom: "1px solid var(--color-stone-border)",
                                }}
                              >
                                <input
                                  type="checkbox"
                                  checked={selected}
                                  onChange={() => toggleTicker(c.ticker)}
                                  aria-label={`Select ${c.ticker}`}
                                />
                              </td>
                              <td
                                style={{
                                  padding: "8px 4px",
                                  borderBottom: "1px solid var(--color-stone-border)",
                                  fontWeight: 600,
                                }}
                              >
                                {c.ticker}
                                {c.run_count > 1 && (
                                  <span
                                    style={{
                                      marginLeft: 6,
                                      fontSize: "var(--text-caption)",
                                      color: "var(--color-ash-gray)",
                                      fontWeight: 400,
                                    }}
                                  >
                                    ×{c.run_count}
                                  </span>
                                )}
                              </td>
                              <td
                                style={{
                                  padding: "8px 4px",
                                  borderBottom: "1px solid var(--color-stone-border)",
                                  fontSize: "var(--text-caption)",
                                }}
                              >
                                {c.market}
                              </td>
                              <td
                                style={{
                                  padding: "8px 4px",
                                  borderBottom: "1px solid var(--color-stone-border)",
                                }}
                              >
                                <CoverageDots
                                  hasReport={c.has_report}
                                  hasDims={c.has_dimensions}
                                  hasComm={c.has_commentary}
                                />
                              </td>
                              <td
                                style={{
                                  padding: "8px 4px",
                                  borderBottom: "1px solid var(--color-stone-border)",
                                  fontSize: "var(--text-caption)",
                                  color: "var(--color-ash-gray)",
                                }}
                              >
                                {c.has_report ? (
                                  <>
                                    <div style={{ color: "var(--color-slate-text)", fontWeight: 600 }}>
                                      {c.latest_rating ?? "—"}
                                    </div>
                                    <div>{c.latest_date ?? "—"}</div>
                                  </>
                                ) : (
                                  "—"
                                )}
                              </td>
                              <td
                                style={{
                                  padding: "8px 4px",
                                  borderBottom: "1px solid var(--color-stone-border)",
                                  whiteSpace: "nowrap",
                                }}
                              >
                                <Link
                                  to={dashboardPath({ ticker: c.ticker })}
                                  className="link-action"
                                  style={{ marginRight: 8 }}
                                >
                                  Analyze
                                </Link>
                                {c.latest_run_id ? (
                                  <Link
                                    to={runsPath(c.latest_run_id)}
                                    className="link-action"
                                  >
                                    Report
                                  </Link>
                                ) : (
                                  <Link
                                    to={stocksPath(c.ticker)}
                                    className="link-action"
                                    title={`All runs for ${c.ticker}`}
                                  >
                                    Runs
                                  </Link>
                                )}
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                )}
              </>
            )}
          </section>
        </div>
      )}
    </div>
  );
}
