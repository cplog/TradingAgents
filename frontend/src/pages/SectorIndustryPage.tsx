import { useCallback, useEffect, useMemo, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { Link, useNavigate } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { dashboardPath, runsPath, stocksPath } from "../navigation/routes";
import type {
  BloomSignal,
  CatalogStatus,
  CoverageQualitySummary,
  FactorAggregate,
  HistoryCoverageRow,
  IndustryConstituentRow,
  RatingDistributionBucket,
  SectorAnalyticsResponse,
} from "../api";
import {
  fetchCatalogStatus,
  fetchHistoryCoverage,
  fetchIndustryConstituents,
  fetchSectorAnalytics,
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
type IndustryViewMode = "grouped" | "flat";

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
  transition: "background 0.18s, border-color 0.18s, color 0.18s, transform 0.12s",
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
        boxShadow: on ? "0 0 0 2px rgba(42, 32, 24, 0.06)" : "none",
      }}
    />
  );
  return (
    <span style={{ display: "inline-flex", gap: 5, alignItems: "center" }}>
      {dot(!!hasReport, "report", "var(--color-sage)")}
      {dot(!!hasDims, "dimensions", "var(--color-apricot-soft)")}
      {dot(!!hasComm, "commentary", "var(--color-taupe)")}
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
  transition: "background 0.18s, border-color 0.18s, color 0.18s",
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
  const [industryViewMode, setIndustryViewMode] = useState<IndustryViewMode>("grouped");

  const [marketFilter, setMarketFilter] = useState<MarketFilter>("ALL");
  const [constFilter, setConstFilter] = useState<ConstituentFilter>("ALL");
  const [tickerSearch, setTickerSearch] = useState("");

  const [constituents, setConstituents] = useState<IndustryConstituentRow[]>([]);
  const [constLoading, setConstLoading] = useState(false);
  const [constError, setConstError] = useState<string | null>(null);

  const [selectedTickers, setSelectedTickers] = useState<Set<string>>(new Set());

  const [catalogStatus, setCatalogStatus] = useState<CatalogStatus | null>(null);

  const [analytics, setAnalytics] = useState<SectorAnalyticsResponse | null>(null);
  const [analyticsLoading, setAnalyticsLoading] = useState(false);
  const [analyticsError, setAnalyticsError] = useState<string | null>(null);

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

  const flatIndustries = useMemo(() => {
    let rows: HistoryCoverageRow[] = [];
    for (const g of grouped) {
      rows = rows.concat(g.rows);
    }
    if (onlyWithRuns) rows = rows.filter((r) => (r.run_count || 0) > 0);
    const q = sectorSearch.trim().toLowerCase();
    if (!q) return rows;
    return rows.filter(
      (r) =>
        r.industry.toLowerCase().includes(q) ||
        (r.sector || "").toLowerCase().includes(q),
    );
  }, [grouped, onlyWithRuns, sectorSearch]);

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
      setAnalytics(null);
      setAnalyticsLoading(false);
      setAnalyticsError(null);
      setConstituents([]);
      setConstError(null);
      return;
    }
    let cancelled = false;

    async function loadAnalytics() {
      setAnalyticsLoading(true);
      setAnalyticsError(null);
      try {
        const data = await fetchSectorAnalytics({
          sector: selectedSector!,
          industry: selectedIndustry!,
          market: marketFilter,
        });
        if (!cancelled) setAnalytics(data);
      } catch (e: unknown) {
        const msg = e instanceof Error ? e.message : String(e);
        if (!cancelled) setAnalyticsError(msg);
      } finally {
        if (!cancelled) setAnalyticsLoading(false);
      }
    }
    void loadAnalytics();

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
        <div className="content-entrance">
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
              placeholder={industryViewMode === "flat" ? "Filter sectors & industries…" : "Filter sectors…"}
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
            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                marginBottom: 6,
              }}
            >
              <h2 style={{ margin: 0, fontSize: "var(--text-heading-sm)" }}>
                {industryViewMode === "flat" ? "All Industries" : "Industries"}
              </h2>
              <div style={{ display: "flex", gap: 4 }}>
                {([
                  ["grouped", "By sector"],
                  ["flat", "All"],
                ] as const).map(([key, label]) => (
                  <button
                    key={key}
                    type="button"
                    onClick={() => setIndustryViewMode(key)}
                    style={segBtn(industryViewMode === key)}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>
            {industryViewMode === "grouped" && !selectedSector && (
              <p style={{ color: "var(--color-ash-gray)", fontSize: "var(--text-body-sm)" }}>
                Select a sector.
              </p>
            )}
            <div style={{ overflowY: "auto", flex: 1 }}>
              <AnimatePresence mode="wait">
                {industryViewMode === "grouped" && selectedSector && (
                  <motion.div
                    key={selectedSector}
                    initial={{ opacity: 0, y: 4 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -4 }}
                    transition={{ duration: 0.18, ease: [0.25, 1, 0.5, 1] }}
                  >
                    {industriesForSector.length === 0 && (
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
                  </motion.div>
                )}
                {industryViewMode === "flat" && (
                  <motion.div
                    key="flat-industries"
                    initial={{ opacity: 0, y: 4 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -4 }}
                    transition={{ duration: 0.18, ease: [0.25, 1, 0.5, 1] }}
                  >
                    {flatIndustries.length === 0 && (
                      <p style={{ color: "var(--color-ash-gray)", fontSize: "var(--text-body-sm)" }}>
                        No matching industries{onlyWithRuns ? " with runs" : ""}.
                      </p>
                    )}
                    {flatIndustries.map((r) => {
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
                            {r.sector}
                            {r.run_count > 0
                              ? ` · dims ${r.with_dimensions_count} · notes ${r.with_commentary_count}`
                              : ""}
                          </div>
                        </button>
                      );
                    })}
                  </motion.div>
                )}
              </AnimatePresence>
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

            <AnimatePresence mode="wait">
            {selectedIndustry && (
              <motion.div
                key={`${selectedSector}|${selectedIndustry}`}
                initial={{ opacity: 0, y: 4 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -4 }}
                transition={{ duration: 0.18, ease: [0.25, 1, 0.5, 1] }}
              >
                <div className="sector-filter-row">
                  <input
                    className="sector-filter-input"
                    type="search"
                    placeholder="Filter tickers…"
                    value={tickerSearch}
                    onChange={(e) => setTickerSearch(e.target.value)}
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
                  <AnimatePresence>
                    {selectedTickers.size > 0 && (
                      <motion.span
                        initial={{ opacity: 0, y: -4 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: -4 }}
                        transition={{ duration: 0.18, ease: [0.25, 1, 0.5, 1] }}
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
                      </motion.span>
                    )}
                    </AnimatePresence>
                </div>

                {/* ── Sector Analytics ── */}
                {analyticsLoading && (
                  <p style={{ color: "var(--color-ash-gray)", fontSize: "var(--text-body-sm)", marginBottom: 12 }}>
                    Loading analytics…
                  </p>
                )}
                {analyticsError && !analytics && (
                  <p
                    style={{
                      color: "var(--color-amber-readout)",
                      fontSize: "var(--text-body-sm)",
                      marginBottom: 12,
                    }}
                  >
                    Analytics unavailable: {analyticsError}
                  </p>
                )}
                {analytics && (
                  <div
                    style={{
                      display: "flex",
                      flexWrap: "wrap",
                      gap: 10,
                      marginBottom: 14,
                    }}
                  >
                    {/* Health score */}
                    <div
                      style={{
                        flex: "1 1 160px",
                        minWidth: 140,
                        padding: "10px 12px",
                        borderRadius: "var(--radius-cards)",
                        border: "1px solid var(--color-stone-border)",
                        background: "var(--surface-cloud-white)",
                      }}
                    >
                      <div style={{ fontSize: "var(--text-caption)", color: "var(--color-ash-gray)", marginBottom: 4 }}>
                        Health score
                      </div>
                      <div
                        style={{
                          fontSize: "var(--text-heading-lg)",
                          fontWeight: 700,
                          color:
                            analytics.health_score >= 60
                              ? "var(--color-phosphor)"
                              : analytics.health_score >= 35
                                ? "var(--color-amber-readout)"
                                : "var(--color-strawberry)",
                        }}
                      >
                        {Math.round(analytics.health_score)}
                        <span style={{ fontSize: "var(--text-body-sm)", fontWeight: 400, color: "var(--color-ash-gray)", marginLeft: 4 }}>
                          /100
                        </span>
                      </div>
                      <div style={{ fontSize: "var(--text-caption)", color: "var(--color-ash-gray)", marginTop: 4 }}>
                        <span title="Rating contribution">R {Math.round(analytics.rating_score)}</span>
                        {" · "}
                        <span title="Factor contribution">F {Math.round(analytics.factor_score)}</span>
                        {" · "}
                        <span title="Freshness contribution">Fr {Math.round(analytics.freshness_score)}</span>
                      </div>
                    </div>

                    {/* Bloom / expansion signal */}
                    <div
                      style={{
                        flex: "1 1 200px",
                        minWidth: 160,
                        padding: "10px 12px",
                        borderRadius: "var(--radius-cards)",
                        border: "1px solid var(--color-stone-border)",
                        background: "var(--surface-cloud-white)",
                      }}
                    >
                      <div style={{ fontSize: "var(--text-caption)", color: "var(--color-ash-gray)", marginBottom: 4 }}>
                        Expansion signal
                      </div>
                      <div
                        style={{
                          fontSize: "var(--text-body-lg)",
                          fontWeight: 700,
                          color:
                            analytics.bloom?.bloom_label === "Hot"
                              ? "var(--color-strawberry)"
                              : analytics.bloom?.bloom_label === "Accelerating"
                                ? "var(--color-amber-readout)"
                                : analytics.bloom?.bloom_label === "Emerging"
                                  ? "var(--color-chartwell-blue)"
                                  : "var(--color-ash-gray)",
                        }}
                      >
                        {analytics.bloom?.bloom_label ?? "—"}
                        {(analytics.bloom?.bloom_score ?? 0) > 0 && (
                          <span style={{ fontSize: "var(--text-caption)", fontWeight: 400, color: "var(--color-ash-gray)", marginLeft: 6 }}>
                            ({Math.round(analytics.bloom!.bloom_score)})
                          </span>
                        )}
                      </div>
                      {analytics.bloom && analytics.bloom.reasons.length > 0 && (
                        <div
                          style={{
                            display: "flex",
                            flexWrap: "wrap",
                            gap: 4,
                            marginTop: 6,
                          }}
                        >
                          {analytics.bloom.reasons.map((r, i) => (
                            <span
                              key={i}
                              style={{
                                fontSize: "var(--text-caption)",
                                padding: "1px 6px",
                                borderRadius: 999,
                                background: "rgba(42, 32, 24, 0.06)",
                                color: "var(--color-slate-text)",
                                border: "1px solid var(--color-platinum-outline)",
                              }}
                            >
                              {r}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>

                    {/* Coverage quality */}
                    <div
                      style={{
                        flex: "1 1 160px",
                        minWidth: 140,
                        padding: "10px 12px",
                        borderRadius: "var(--radius-cards)",
                        border: "1px solid var(--color-stone-border)",
                        background: "var(--surface-cloud-white)",
                      }}
                    >
                      <div style={{ fontSize: "var(--text-caption)", color: "var(--color-ash-gray)", marginBottom: 4 }}>
                        Coverage
                      </div>
                      <div style={{ fontSize: "var(--text-body-lg)", fontWeight: 700, color: "var(--color-slate-text)" }}>
                        {analytics.coverage_quality.analyzed_tickers}
                        <span style={{ fontSize: "var(--text-caption)", fontWeight: 400, color: "var(--color-ash-gray)", marginLeft: 4 }}>
                          / {analytics.coverage_quality.total_constituents}
                        </span>
                      </div>
                      <div style={{ fontSize: "var(--text-caption)", color: "var(--color-ash-gray)", marginTop: 4 }}>
                        {Math.round(analytics.coverage_quality.pct_with_dimensions)}% dims · {Math.round(analytics.coverage_quality.pct_with_commentary)}% notes
                      </div>
                      {analytics.coverage_quality.freshness_days_median != null && (
                        <div style={{ fontSize: "var(--text-caption)", color: "var(--color-ash-gray)" }}>
                          μ {Math.round(analytics.coverage_quality.freshness_days_median)}d · p90 {analytics.coverage_quality.freshness_days_p90 != null ? `${Math.round(analytics.coverage_quality.freshness_days_p90)}d` : "—"}
                        </div>
                      )}
                    </div>

                    {/* Avg confidence */}
                    <div
                      style={{
                        flex: "1 1 100px",
                        minWidth: 80,
                        padding: "10px 12px",
                        borderRadius: "var(--radius-cards)",
                        border: "1px solid var(--color-stone-border)",
                        background: "var(--surface-cloud-white)",
                      }}
                    >
                      <div style={{ fontSize: "var(--text-caption)", color: "var(--color-ash-gray)", marginBottom: 4 }}>
                        Avg confidence
                      </div>
                      <div style={{ fontSize: "var(--text-body-lg)", fontWeight: 700, color: "var(--color-slate-text)" }}>
                        {analytics.avg_confidence > 0 ? Math.round(analytics.avg_confidence) : "—"}
                      </div>
                    </div>

                    {/* Rating distribution mini chart */}
                    {analytics.rating_distribution.some((b) => b.count > 0) && (
                      <div
                        style={{
                          flex: "2 1 240px",
                          minWidth: 200,
                          padding: "10px 12px",
                          borderRadius: "var(--radius-cards)",
                          border: "1px solid var(--color-stone-border)",
                          background: "var(--surface-cloud-white)",
                          height: 100,
                        }}
                      >
                        <div style={{ fontSize: "var(--text-caption)", color: "var(--color-ash-gray)", marginBottom: 2 }}>
                          Rating distribution
                        </div>
                        <ResponsiveContainer width="100%" height={68}>
                          <BarChart
                            data={analytics.rating_distribution.filter((b) => b.count > 0)}
                            layout="vertical"
                            margin={{ top: 0, right: 4, left: 4, bottom: 0 }}
                          >
                            <CartesianGrid stroke="var(--color-stone-border)" strokeDasharray="3 3" horizontal={false} />
                            <XAxis type="number" tick={false} axisLine={false} />
                            <YAxis
                              type="category"
                              dataKey="rating"
                              width={60}
                              tick={{ fontSize: 8, fill: "var(--color-ash-gray)" }}
                            />
                            <Tooltip
                              contentStyle={{
                                background: "var(--surface-elevated)",
                                border: "1px solid var(--color-stone-border)",
                                borderRadius: "var(--radius-md)",
                                fontSize: 11,
                              }}
                              formatter={(value: number, _name: string, props: { payload: RatingDistributionBucket }) => [
                                `${value} (${props.payload.pct}%)`,
                                props.payload.rating,
                              ]}
                            />
                            <Bar dataKey="count" fill="var(--color-phosphor)" radius={[0, 2, 2, 0]} />
                          </BarChart>
                        </ResponsiveContainer>
                      </div>
                    )}

                    {/* Factor medians mini chart */}
                    {analytics.factor_medians.some((f) => f.median > 0) && (
                      <div
                        style={{
                          flex: "2 1 240px",
                          minWidth: 200,
                          padding: "10px 12px",
                          borderRadius: "var(--radius-cards)",
                          border: "1px solid var(--color-stone-border)",
                          background: "var(--surface-cloud-white)",
                          height: 100,
                        }}
                      >
                        <div style={{ fontSize: "var(--text-caption)", color: "var(--color-ash-gray)", marginBottom: 2 }}>
                          Factor medians
                        </div>
                        <ResponsiveContainer width="100%" height={68}>
                          <BarChart
                            data={analytics.factor_medians}
                            layout="vertical"
                            margin={{ top: 0, right: 4, left: 4, bottom: 0 }}
                          >
                            <CartesianGrid stroke="var(--color-stone-border)" strokeDasharray="3 3" horizontal={false} />
                            <XAxis
                              type="number"
                              domain={[0, 100]}
                              tick={false}
                              axisLine={false}
                            />
                            <YAxis
                              type="category"
                              dataKey="factor"
                              width={52}
                              tick={{ fontSize: 8, fill: "var(--color-ash-gray)" }}
                            />
                            <Tooltip
                              contentStyle={{
                                background: "var(--surface-elevated)",
                                border: "1px solid var(--color-stone-border)",
                                borderRadius: "var(--radius-md)",
                                fontSize: 11,
                              }}
                              formatter={(value: number, _name: string, props: { payload: FactorAggregate }) => [
                                `${value} (n=${props.payload.tickers_with_data})`,
                                props.payload.factor,
                              ]}
                            />
                            <Bar dataKey="median" fill="var(--color-apricot-soft)" radius={[0, 2, 2, 0]} />
                          </BarChart>
                        </ResponsiveContainer>
                      </div>
                    )}
                  </div>
                )}

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
                              style={{
                                transition: "background 0.18s",
                                ...(selected
                                  ? { background: "var(--color-phosphor-glow)" }
                                  : c.has_report
                                    ? { background: "rgba(120, 240, 168, 0.05)" }
                                    : {}),
                              }}
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
              </motion.div>
            )}
          </AnimatePresence>
          </section>
        </div>
      </div>
      )}
    </div>
  );
}
