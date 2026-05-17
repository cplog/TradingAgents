import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import type { HistoryCoverageRow, IndustryConstituentRow } from "../api";
import { fetchHistoryCoverage, fetchIndustryConstituents } from "../api";

type SectorGroup = { sector: string; rows: HistoryCoverageRow[] };
type MarketFilter = "ALL" | "US" | "HK";

function groupBySector(coverage: HistoryCoverageRow[]): SectorGroup[] {
  const m = new Map<string, HistoryCoverageRow[]>();
  for (const row of coverage) {
    const s = row.sector || "(unknown)";
    if (!m.has(s)) m.set(s, []);
    m.get(s)!.push(row);
  }
  return Array.from(m.entries())
    .map(([sector, rows]) => ({
      sector,
      rows: rows.sort((a, b) =>
        `${a.industry}`.localeCompare(`${b.industry}`, undefined, {
          sensitivity: "base",
        }),
      ),
    }))
    .sort((a, b) => a.sector.localeCompare(b.sector, undefined, { sensitivity: "base" }));
}

function CoverageBadge({
  yes,
  label,
}: {
  yes?: boolean | null;
  label: string;
}) {
  const tone =
    yes === true
      ? { bg: "#dcfce7", color: "#166534", border: "#86efac" }
      : { bg: "#f4f4f5", color: "#71717a", border: "#e4e4e7" };
  return (
    <span
      style={{
        display: "inline-block",
        fontSize: "var(--text-caption)",
        padding: "2px 8px",
        borderRadius: "var(--radius-sm)",
        background: tone.bg,
        color: tone.color,
        border: `1px solid ${tone.border}`,
      }}
    >
      {label}: {yes ? "yes" : "no"}
    </span>
  );
}

const panelStyle: React.CSSProperties = {
  background: "var(--surface-cloud-white)",
  padding: "var(--card-padding)",
  borderRadius: "var(--radius-cards)",
  border: "1px solid var(--color-stone-border)",
  boxShadow: "var(--shadow-subtle)",
  minHeight: 420,
  display: "flex",
  flexDirection: "column",
};

const listBtn = (active: boolean): React.CSSProperties => ({
  display: "block",
  width: "100%",
  textAlign: "left",
  padding: "8px 10px",
  marginBottom: 4,
  borderRadius: "var(--radius-buttons)",
  border: active ? "1px solid var(--color-chartwell-blue)" : "1px solid transparent",
  background: active ? "var(--color-sky-tint)" : "transparent",
  color: "var(--color-slate-text)",
  cursor: "pointer",
  fontSize: "var(--text-body-sm)",
  fontWeight: active ? 600 : 400,
});

export function SectorIndustryPage() {
  const [coverage, setCoverage] = useState<HistoryCoverageRow[]>([]);
  const [covLoading, setCovLoading] = useState(true);
  const [covError, setCovError] = useState<string | null>(null);

  const [sectorSearch, setSectorSearch] = useState("");
  const [selectedSector, setSelectedSector] = useState<string | null>(null);
  const [selectedIndustry, setSelectedIndustry] = useState<string | null>(null);

  const [marketFilter, setMarketFilter] = useState<MarketFilter>("ALL");
  const [tickerSearch, setTickerSearch] = useState("");

  const [constituents, setConstituents] = useState<IndustryConstituentRow[]>([]);
  const [constLoading, setConstLoading] = useState(false);
  const [constError, setConstError] = useState<string | null>(null);

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
    return () => {
      cancelled = true;
    };
  }, []);

  const grouped = useMemo(() => groupBySector(coverage), [coverage]);

  const filteredSectors = useMemo(() => {
    const q = sectorSearch.trim().toLowerCase();
    if (!q) return grouped;
    return grouped.filter(
      (g) =>
        g.sector.toLowerCase().includes(q) ||
        g.rows.some((r) => r.industry.toLowerCase().includes(q)),
    );
  }, [grouped, sectorSearch]);

  const industriesForSector = useMemo(() => {
    if (!selectedSector) return [];
    return grouped.find((g) => g.sector === selectedSector)?.rows ?? [];
  }, [grouped, selectedSector]);

  useEffect(() => {
    if (covLoading || grouped.length === 0 || selectedSector) return;
    const first = grouped[0];
    setSelectedSector(first.sector);
    setSelectedIndustry(first.rows[0]?.industry ?? null);
  }, [covLoading, grouped, selectedSector]);

  const selectSector = useCallback(
    (sector: string) => {
      setSelectedSector(sector);
      const rows = grouped.find((g) => g.sector === sector)?.rows ?? [];
      setSelectedIndustry(rows[0]?.industry ?? null);
    },
    [grouped],
  );

  const selectIndustry = useCallback((sector: string, industry: string) => {
    setSelectedSector(sector);
    setSelectedIndustry(industry);
    setTickerSearch("");
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

  const filteredConstituents = useMemo(() => {
    const q = tickerSearch.trim().toUpperCase();
    if (!q) return constituents;
    return constituents.filter((c) => c.ticker.includes(q));
  }, [constituents, tickerSearch]);

  const summary = useMemo(() => {
    const withReport = constituents.filter((c) => c.has_report).length;
    const withDims = constituents.filter((c) => c.has_dimensions).length;
    return { total: constituents.length, withReport, withDims };
  }, [constituents]);

  return (
    <div style={{ maxWidth: "1440px" }}>
      <header style={{ marginBottom: "var(--spacing-16)" }}>
        <h1 style={{ margin: 0, fontSize: "var(--text-heading-lg)" }}>
          Sector / industry explorer
        </h1>
        <p style={{ margin: "8px 0 0", color: "var(--color-ash-gray)" }}>
          Pick a sector and industry, then browse catalog constituents (US and HK). Badges show
          whether each ticker has a persisted report and dimensions snapshot.
        </p>
      </header>

      {covLoading && <p style={{ color: "var(--color-ash-gray)" }}>Loading catalog…</p>}
      {covError && (
        <p style={{ color: "#b45309", fontSize: "var(--text-body-sm)" }}>
          Could not load coverage: {covError}
        </p>
      )}

      {!covLoading && !covError && (
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "minmax(160px, 200px) minmax(200px, 260px) minmax(0, 1fr)",
            gap: "var(--spacing-12)",
            alignItems: "stretch",
          }}
        >
          <section style={panelStyle}>
            <h2 style={{ margin: "0 0 8px", fontSize: "var(--text-heading-sm)" }}>Sectors</h2>
            <input
              type="search"
              placeholder="Filter sectors…"
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
              {filteredSectors.map(({ sector, rows }) => {
                const runTotal = rows.reduce((n, r) => n + r.run_count, 0);
                const active = selectedSector === sector;
                return (
                  <button
                    key={sector}
                    type="button"
                    onClick={() => selectSector(sector)}
                    style={listBtn(active)}
                  >
                    <div>{sector}</div>
                    <div
                      style={{ fontSize: "var(--text-caption)", color: "var(--color-ash-gray)" }}
                    >
                      {rows.length} industries · {runTotal} runs
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
              {industriesForSector.map((r) => {
                const active =
                  selectedSector === r.sector && selectedIndustry === r.industry;
                return (
                  <button
                    key={`${r.sector}|${r.industry}`}
                    type="button"
                    onClick={() => selectIndustry(r.sector, r.industry)}
                    style={listBtn(active)}
                  >
                    <div>{r.industry}</div>
                    <div
                      style={{ fontSize: "var(--text-caption)", color: "var(--color-ash-gray)" }}
                    >
                      {r.run_count} runs · dims {r.with_dimensions_count} · notes{" "}
                      {r.with_commentary_count}
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
                    style={{
                      padding: "4px 10px",
                      borderRadius: "var(--radius-buttons)",
                      border: "1px solid var(--color-platinum-outline)",
                      background:
                        marketFilter === m ? "var(--color-chartwell-blue)" : "white",
                      color: marketFilter === m ? "white" : "var(--color-slate-text)",
                      fontSize: "var(--text-caption)",
                      fontWeight: 600,
                      cursor: "pointer",
                    }}
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
                <input
                  type="search"
                  placeholder="Filter tickers…"
                  value={tickerSearch}
                  onChange={(e) => setTickerSearch(e.target.value)}
                  style={{
                    width: "100%",
                    marginBottom: 8,
                    padding: "8px 10px",
                    borderRadius: "var(--radius-buttons)",
                    border: "1px solid var(--color-platinum-outline)",
                    fontSize: "var(--text-body-sm)",
                  }}
                />
                <p
                  style={{
                    margin: "0 0 10px",
                    fontSize: "var(--text-caption)",
                    color: "var(--color-ash-gray)",
                  }}
                >
                  {summary.total} tickers · {summary.withReport} with reports · {summary.withDims}{" "}
                  with dimensions
                </p>
                {constLoading && <p style={{ color: "var(--color-ash-gray)" }}>Loading tickers…</p>}
                {constError && (
                  <p style={{ color: "#b45309", fontSize: "var(--text-body-sm)" }}>{constError}</p>
                )}
                {!constLoading && !constError && filteredConstituents.length === 0 && (
                  <p style={{ color: "var(--color-ash-gray)" }}>
                    No constituents for this slice. Run{" "}
                    <code>scripts/cold_start_yahoo_sectors.py --constituents</code> to populate D1.
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
                        {filteredConstituents.map((c) => (
                          <tr key={`${c.market}-${c.ticker}`}>
                            <td
                              style={{
                                padding: "8px 4px",
                                borderBottom: "1px solid #f4f4f5",
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
                                borderBottom: "1px solid #f4f4f5",
                                fontSize: "var(--text-caption)",
                              }}
                            >
                              {c.market}
                            </td>
                            <td style={{ padding: "8px 4px", borderBottom: "1px solid #f4f4f5" }}>
                              <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
                                <CoverageBadge yes={c.has_report} label="report" />
                                <CoverageBadge yes={c.has_dimensions} label="dimensions" />
                                <CoverageBadge yes={c.has_commentary} label="commentary" />
                              </div>
                            </td>
                            <td
                              style={{
                                padding: "8px 4px",
                                borderBottom: "1px solid #f4f4f5",
                                fontSize: "var(--text-caption)",
                                color: "var(--color-ash-gray)",
                              }}
                            >
                              {c.has_report ? (
                                <>
                                  <div>{c.latest_rating ?? "—"}</div>
                                  <div>{c.latest_date ?? "—"}</div>
                                </>
                              ) : (
                                "—"
                              )}
                            </td>
                            <td
                              style={{
                                padding: "8px 4px",
                                borderBottom: "1px solid #f4f4f5",
                                whiteSpace: "nowrap",
                              }}
                            >
                              <Link
                                to={`/dashboard?ticker=${encodeURIComponent(c.ticker)}`}
                                style={{
                                  marginRight: 8,
                                  fontWeight: 600,
                                  color: "var(--color-chartwell-blue)",
                                }}
                              >
                                Analyze
                              </Link>
                              {c.latest_run_id ? (
                                <Link
                                  to={`/history?run=${encodeURIComponent(c.latest_run_id)}`}
                                  style={{ fontWeight: 600, color: "var(--color-slate-text)" }}
                                >
                                  Report
                                </Link>
                              ) : (
                                <Link
                                  to={`/history?ticker=${encodeURIComponent(c.ticker)}`}
                                  style={{
                                    fontWeight: 600,
                                    color: "var(--color-ash-gray)",
                                  }}
                                  title="Filter History by ticker"
                                >
                                  History
                                </Link>
                              )}
                            </td>
                          </tr>
                        ))}
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
