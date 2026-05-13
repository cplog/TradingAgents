# Standardized Stock Dimensions — Design Spec

**Status:** Draft for review
**Date:** 2026-05-13
**Author:** Brainstormed via superpowers:brainstorming
**Target version:** TradingAgents v0.3.x (fork-local feature; no upstream changes)

---

## 1. Problem

TradingAgents produces rich prose reports per analyst, but there is no normalized, comparable, structured layer about the **stock itself**. The only structured outputs today (`ResearchPlan`, `TraderProposal`, `PortfolioDecision`) describe **decisions**, not the underlying instrument.

Consequences:
- Cross-stock comparison is impossible without re-reading prose
- The UI cannot offer sortable batch tables, radar charts, or filtering ("show me Buys with momentum>4 and valuation<3")
- Downstream agents see the same stock differently each run because their inputs are unstructured

## 2. Goals

1. **Cross-stock comparison and ranking** — rank a watchlist on the same axes
2. **UI dashboards & filters** — render score cards, radar charts, sortable tables, comparison views
3. **Foundation for grounded downstream agents** — v1 ships post-run; v2 (upstream PR) can wire dimensions into agent prompts

## 3. Constraints

- **No edits inside `tradingagents/`.** This fork rebases `main` onto `upstream/main` via `scripts/sync_upstream.sh`. Any divergence inside `tradingagents/` becomes conflict surface on every sync. All new feature code lives in `api/`, `frontend/`, `scripts/`, `tests/`, or top-level config.
- **Use existing infra.** State store, job model, LLM clients, history endpoints are reused, not replaced.
- **Failure-isolated.** Dimensions and commentary build inside a `try/except`; the original job result must ship even if dimensions build fails.

## 4. Data Model

A single `StockDimensions` record per (ticker, date). Three layers.

### 4.1 Layer 1 — `facts` (deterministic, sourced from yfinance)

| Group | Fields |
|---|---|
| Identity | `as_of_date`, `currency`, `exchange`, `sector`, `industry`, `market_cap_usd` |
| Price/return | `price`, `price_52w_high`, `pct_off_52w_high`, `return_1m`, `return_3m`, `return_6m`, `return_12m`, `beta` |
| Volatility/liquidity | `realized_vol_30d`, `rsi_14`, `avg_daily_dollar_volume_30d` |
| Valuation | `pe_ttm`, `forward_pe`, `peg`, `ev_ebitda`, `ps_ttm`, `pb`, `fcf_yield` |
| Growth | `revenue_growth_yoy`, `eps_growth_yoy`, `revenue_cagr_3y`, `eps_cagr_3y` |
| Quality | `roe`, `roic`, `gross_margin`, `operating_margin`, `net_margin`, `debt_to_equity`, `interest_coverage`, `current_ratio` |
| Income | `dividend_yield`, `payout_ratio` |
| Sell-side | `analyst_count`, `analyst_target_mean`, `analyst_recommendation_mean` |

Missing fields are stored `None` and recorded in `data_quality_flags`.

### 4.2 Layer 2 — `pillar_scores` (1-5 LLM-judged, with rationale)

Each pillar has 4 sub-dimensions. Each sub-dimension is `{score: 1..5, rationale: str}`.

| Pillar | Sub-dimensions |
|---|---|
| `market` | `trend`, `momentum`, `volatility_risk`, `setup_quality` |
| `sentiment` | `retail_sentiment`, `social_buzz`, `consensus_quality`, `narrative_strength` |
| `news` | `catalyst_strength`, `macro_alignment`, `headline_quality`, `surprise_risk` |
| `fundamentals` | `valuation`, `growth`, `profitability`, `balance_sheet_strength` |

16 scores total. `volatility_risk` and `surprise_risk` are scored "lower = riskier" — the schema field description tells the model explicitly.

### 4.3 Layer 3 — `factor_scores` (0-100, deterministic with sector peer percentiles)

Six factors: `value`, `growth`, `quality`, `momentum`, `low_risk`, `sentiment`.

Each is computed via a weighted formula combining matching pillar scores (mapped 1-5 → 0-100) with sector-peer percentile ranks of facts. Each factor includes the input components and weights used, so the score is auditable.

Example formula (locked in `api/dimensions/factors.py` for v1):

```
value = 0.5 * scale_1_5_to_0_100(fundamentals.valuation)
      + 0.3 * peer_pct(facts.pe_ttm, inverted=True)
      + 0.2 * peer_pct(facts.pb, inverted=True)
```

Where `peer_pct` uses the sector peer cache; if peers <3 or the fact is null, the term is dropped and the remaining weights are re-normalized. If **all** terms for a factor are dropped (no usable inputs), the factor's `score` is `None` and a `data_quality_flag` like `"factor_value_no_inputs"` is appended.

The complete weight tables for all 6 factors live in `api/dimensions/factors.py` with the audit trail in each `FactorScore.inputs` dict.

### 4.4 `StockDimensions` envelope

```python
class StockDimensions(BaseModel):
    ticker: str
    as_of_date: str
    facts: FactSnapshot
    pillar_scores: PillarScores
    factor_scores: FactorScores
    dimensions_version: str            # SemVer, e.g. "1.0.0"
    peer_universe_id: Optional[str]    # e.g. "sector:Technology|industry:Software"
    data_quality_flags: List[str]
    source: Literal["full_run", "facts_only"] = "full_run"
```

Versioning rule: any change to fact fields, pillar definitions, or factor formulas bumps `dimensions_version`. Rendering-only changes do not.

### 4.5 `DimensionsCommentary` (W1 — dimensions-grounded second view)

```python
class DimensionsCommentary(BaseModel):
    alignment: Literal["aligned", "partial", "misaligned"]
    supporting_dimensions: List[str]
    conflicting_dimensions: List[str]
    risk_flags: List[str]
    summary: str
```

Produced by one LLM call reading the PM decision + freshly built dimensions. It is **not** the PM agent — it is a post-hoc, dimensions-grounded second opinion.

## 5. Architecture

### 5.1 Module layout — `api/dimensions/`

```
api/dimensions/
├── __init__.py          # public: build_dimensions(), build_commentary(), DimensionsBuildResult
├── facts.py             # yfinance fact extraction → StockFacts
├── peers.py             # sector peer cache + percentile lookup
├── scoring.py           # LLM call → PillarScores (structured output)
├── factors.py           # deterministic 16 → 6 factor formula
├── commentary.py        # W1 LLM call → DimensionsCommentary
├── schemas.py           # Pydantic models (re-exported through api/models.py)
└── version.py           # DIMENSIONS_VERSION + changelog
```

Each module is independently testable. Schemas are imported into `api/models.py` so they appear in the FastAPI OpenAPI spec without duplication.

### 5.2 Job lifecycle integration (api/jobs.py)

```
Worker picks up job
  → TradingAgentsGraph.propagate(ticker, date)     ← unchanged, untouched
  → builds final_state + rating
  → build_result(final_state, rating, ticker, date, config)   ← unchanged

[NEW post-pass — runs only on successful completion]
  → try:
      dimensions = build_dimensions(ticker, date, final_state, config, llm_client)
      commentary = build_commentary(dimensions, final_state["final_trade_decision"], llm_client)
      result["dimensions"] = dimensions.model_dump()
      result["dimensions_commentary"] = commentary.model_dump()
    except DimensionsBuildError as exc:
      result["dimensions"] = None
      result["dimensions_commentary"] = None
      result["dimensions_error"] = str(exc)
      logger.warning(...)

  → persist to state store (existing path)
```

The graph and existing analysts/agents are untouched.

### 5.3 `build_dimensions()` internal flow

1. `facts.extract_facts(ticker, as_of_date)` — one yfinance call, populates `StockFacts`. Missing fields → `data_quality_flags`.
2. `peers.get_sector_peers(sector, industry)` — returns up to N=25 peer tickers and cached facts; refreshes from yfinance if cache is older than 24h. Cache location: `<config["data_cache_dir"]>/peer_facts/<sector_slug>.json`.
3. `scoring.score_pillars(facts, analyst_reports, llm)` — ONE structured-output LLM call. Inputs: 4 analyst reports from `final_state` + facts JSON. Output: parsed `PillarScores` (16 fields). Uses `tradingagents.llm_clients.create_llm_client` (public import; no edits to `tradingagents/`).
4. `factors.compute_factors(pillars, facts, peer_pct_table)` — pure function. Returns `FactorScores` with audit `inputs`.
5. Assemble `StockDimensions(...)` with `dimensions_version`, `peer_universe_id`, `data_quality_flags`.

### 5.4 `build_commentary()` flow

One structured-output LLM call. Input: PM decision text + `StockDimensions`. Output: parsed `DimensionsCommentary`.

### 5.5 LLM cost

2 extra LLM calls per job (pillar scoring + commentary), both using `quick_thinking_llm`. The pre-existing graph costs ~12-20 calls per analysis, so this is a ~10-15% increment. Users can opt out via `config_overrides.dimensions_enabled = False`.

### 5.6 Job lifecycle, progress events, SSE, and cancellation

The dimensions post-pass threads into the existing job lifecycle (`api/jobs.py` Worker._run) with these rules:

**Status transitions stay simple.** The job remains `running` through dimensions + commentary and only transitions to `completed` once the result (including dimensions, when built) is persisted. No new intermediate status states. Failures inside dimensions build do NOT flip the job to `failed` — the job still completes with the original report; `dimensions: None` + `dimensions_error: str` indicate the partial result.

**Progress events for dimensions phase.** Six new events emitted via `store.append_progress(job_id, ..., stage="dimensions")`. New `stage` value for UI filtering:

```
"Building dimensions: extracting facts (yfinance)…"          stage="dimensions"
"Building dimensions: loading sector peers (sector: <S>, industry: <I>)…"  stage="dimensions"
"Building dimensions: scoring 16 pillars (1 LLM call)…"      stage="dimensions"
"Building dimensions: computing 6 factor scores…"            stage="dimensions"
"Building dimensions: writing commentary (1 LLM call)…"      stage="dimensions"
"Dimensions built (version <v>). Persisting…"                 stage="dimensions"
```

If dimensions build fails midway, a single `stage="dimensions_skipped"` event is emitted with the error message; the job continues to `completed` with the original report.

**Heartbeat behavior unchanged.** The existing heartbeat task wraps `propagate()` only. Dimensions and commentary calls are not heartbeated individually — each is short (<60s expected) and the progress events themselves serve as activity signals.

**SSE stream semantics.** `GET /jobs/{job_id}/events` already terminates on terminal status (`completed` / `failed`) — verified in code. We add one harden:

- Initial event sent within 100ms of connect (currently events trickle as they arrive — for slow LLM calls the client sees nothing). Solution: on SSE connect, emit a synthetic `{"type": "connected", "cursor": <current_total>, "status": <current_status>}` event before entering the poll loop. Clients use the cursor as their start position.
- Explicit SSE `retry: 5000` field in the first event so reconnecting clients honor a 5s backoff.

**Cancellation.** New endpoint `POST /jobs/{job_id}/cancel` sets a `cancellation_requested` flag on the JobRecord. The Worker checks this flag at stage boundaries:
- Before `build_result()` (after propagate returns) → skip everything, mark `cancelled`
- Before `build_dimensions()` → skip dimensions + commentary, ship result without them, mark `completed` (the analysis itself succeeded)
- Before `build_commentary()` → skip commentary only

Cancellation cannot interrupt `propagate()` itself — LangGraph has no safe-cancellation hook and an executor thread cannot be killed cleanly. Cancellation during propagate is honored at the next stage boundary.

New job status: `cancelled`. Treated like `completed` by SSE termination logic.

**Concurrency unchanged.** `_propagate_sync_lock` (process-global threading lock around `propagate()`) remains. Dimensions build does NOT need to hold that lock — it doesn't touch `tradingagents.dataflows.config.set_config()` global state. This means dimensions for job N can build while propagate for job N+1 runs, improving throughput slightly.

**Persistence ordering.** History persistence happens AFTER both result and dimensions are set on the JobRecord. If history persistence fails (existing behavior: logged and swallowed), the in-memory result is still available via `/jobs/{job_id}`; dimensions are not lost across the same API process lifetime, but ARE lost across an API restart since the job store is in-memory. Cross-restart persistence is explicitly out of scope (see §11).

## 6. Persistence

Existing run record (`HistoryRunDetail`) is extended with two optional fields:

```python
class HistoryRunDetail(BaseModel):
    # existing fields unchanged
    dimensions: Optional[StockDimensions] = None
    dimensions_commentary: Optional[DimensionsCommentary] = None
```

Same fields land on `AnalysisResult` so they flow through `GET /jobs/{job_id}`.

`HistoryRunRef` (compact list row) adds:

```python
factor_scores: Optional[Dict[str, float]] = None
```

So the history list and batch table can sort/filter without fetching full detail.

No schema migration. Old rows have `None` for the new fields and deserialize cleanly.

## 7. API Surface

| Endpoint | Status | Change |
|---|---|---|
| `GET /jobs/{job_id}` | existing | response includes `dimensions` + `dimensions_commentary` when present |
| `GET /jobs/{job_id}/dimensions` | NEW | returns just the `StockDimensions` payload for UI polling |
| `GET /history/runs` | existing | list rows include `factor_scores` summary |
| `GET /history/runs/{run_id}` | existing | detail includes dimensions + commentary |
| `POST /history/compare` | existing | compare side struct adds `dimensions` field per side |
| `GET /dimensions/{ticker}` | NEW | facts-only preview (no analyst context, no LLM call); pillar scores set to neutral 3/5; `source: "facts_only"` |
| `POST /history/runs/{run_id}/recompute-dimensions` | NEW | reads stored reports + PM decision, fetches fresh facts, rebuilds dimensions + commentary; patches run record. Returns the updated `HistoryRunDetail`. 400 if the run lacks the required reports |
| `POST /jobs/{job_id}/cancel` | NEW | sets cancellation flag; honored at next stage boundary (cannot interrupt `propagate()` mid-run). Returns `{ "cancellation_requested": true, "status": <current_status> }` |
| `GET /jobs/{job_id}/events` | existing | first event is now a synthetic `{ "type": "connected", "cursor": <int>, "status": <str> }` with SSE `retry: 5000` so reconnecting clients honor backoff |
| `POST /admin/dimensions/peer-cache/refresh` | NEW (admin) | force refresh of peer cache for a sector |

`GET /dimensions/{ticker}` accepts optional `?as_of_date=YYYY-MM-DD`; defaults to today.

## 8. Frontend

### 8.1 Chart library

**Recharts** added to `frontend/package.json` dependencies. ~50kb gzipped, React-first, SVG, no Canvas blur on small widgets. Used for `RadarChart` and the single-bar `BarChart` cells.

### 8.2 Component module

```
frontend/src/components/dimensions/
├── DimensionsRadar.tsx        # <RadarChart> wrapping factor_scores (6 axes)
├── PillarGrid.tsx             # 4x4 grid with hover rationale tooltips
├── FactsTable.tsx             # sortable grouped facts (price/valuation/growth/quality/income/sell-side)
├── CommentaryCard.tsx         # alignment badge + supporting/conflicting/risks + summary
├── FactorBar.tsx              # 1D bar 0-100 with color tier (used in batch rows)
└── DimensionsPanel.tsx        # composes the above for the dashboard
```

### 8.3 Page touches

| Page | Change |
|---|---|
| `DashboardPage.tsx` | Renders `<DimensionsPanel ... />` below the existing run output. Empty state when `dimensions === null` |
| `BatchPage.tsx` | 6 sortable factor columns (`<FactorBar value={..} />` per cell). Header click toggles sort. Filter chips ("Value > 60", "Low-Risk > 50") persisted in URL query params |
| `HistoryPage.tsx` | Row thumbnail = 6 mini `<FactorBar>` strips. Detail view gains a "Dimensions" tab |
| `HistoryPage` compare modal | Side-by-side radar + per-fact diff table |
| `ScreenerPage.tsx` (NEW route `/screener`) | Input: ticker list. Calls `GET /dimensions/{ticker}` per ticker. Sortable table of facts-only previews. Each row has "Run full analysis" CTA POSTing to `/analyze` |

### 8.4 Empty + error states

- Old runs (no dimensions): "Dimensions not available — this run predates v1.0 of the dimensions layer." The CTA is **"Recompute dimensions"**, which POSTs to `POST /history/runs/{run_id}/recompute-dimensions` (new endpoint). That endpoint reads the stored analyst reports + PM decision from the run record, fetches fresh facts for the run's `as_of_date`, runs `build_dimensions` + `build_commentary`, and patches the run record. Cost: 2 LLM calls. Falls back to "Run new analysis" only if the old run is missing one of the 4 analyst reports
- Build failed: "Dimensions unavailable" + the `dimensions_error` string
- Facts-only preview: prominent `source: facts_only` chip
- Stale peer cache: small clock badge + tooltip with last refresh time

### 8.5 Factor color tiers (with non-color cues for accessibility)

| Score | Color | Icon |
|---|---|---|
| 80-100 | green | ▲▲ |
| 60-79 | lime | ▲ |
| 40-59 | amber | ◆ |
| 20-39 | orange | ▼ |
| 0-19 | red | ▼▼ |

## 9. Testing

```
tests/dimensions/
├── test_facts.py              # yfinance fact extraction via fixtures
├── test_peers.py              # cache write/read, percentile math, peers<3 fallback
├── test_factors.py            # deterministic factor formulas + audit-trail snapshots
├── test_scoring.py            # mocked LLM contract for pillar scoring
├── test_commentary.py         # mocked LLM contract for commentary
├── test_build_dimensions.py   # orchestrator: happy, yfinance fail, LLM fail
├── test_api_dimensions.py     # endpoints (TestClient) incl. /recompute-dimensions
└── fixtures/
    ├── yfinance_aapl.json
    ├── yfinance_nvda.json
    ├── yfinance_0700hk.json   # HK ticker, currency=HKD
    └── analyst_reports.json
```

Frontend tests:
- `DimensionsRadar.test.tsx`
- `FactorBar.test.tsx` (boundary mapping at 19/20/39/40/59/60/79/80)
- `PillarGrid.test.tsx` (hover tooltip surfaces rationale)
- `DimensionsPanel.test.tsx` (renders fixture; handles missing data)

**TDD discipline.** Every code task in the implementation plan ships the failing test before the implementation step.

**Additional jobs/SSE tests** (under `tests/`, not `tests/dimensions/`):

- `test_jobs_dimensions_progress.py` — verifies the 6 new `stage="dimensions"` progress events are emitted in order during a stubbed job run
- `test_jobs_cancel.py` — `POST /jobs/{id}/cancel` flips the flag; Worker honors it at the next stage boundary; cancelled status terminates SSE
- `test_jobs_sse_connect_event.py` — SSE first event is `type: "connected"` with current cursor and status; `retry: 5000` field present
- `test_jobs_dimensions_failure_isolation.py` — dimensions raising during build still ships the original report; job ends `completed`; `dimensions_error` populated

**Out of scope for tests:**
- Real yfinance network calls in CI (fixtures only)
- Real LLM calls in CI (mocked)
- Performance benchmarks (defer to v2 if perf bites)
- Real cancellation of `propagate()` mid-run (LangGraph has no safe hook — only stage-boundary cancellation is supported)

## 10. Versioning

`dimensions_version` is a SemVer string defined in `api/dimensions/version.py`. Persisted runs carry the version that produced them. UI shows a badge when a run's dimensions are from an older version.

Bump rule:
- Fact field added/removed/renamed → bump
- Pillar definition changed → bump
- Factor formula changed → bump
- Rendering-only changes → no bump

v1 ships as `1.0.0`.

## 11. Out of Scope (v1)

Deferred to v2 or upstream PR (jobs/sessions/SSE work):

- **Cross-restart job persistence.** The job store is in-memory; an API restart loses in-flight job state. Swap `JobStore` for Redis / RQ / Celery in v2.
- **Mid-`propagate()` cancellation.** Requires either a LangGraph cancellation hook or running propagate in a process pool with kill semantics. Stage-boundary cancellation is the v1 compromise.
- **SSE reconnection resume from cursor.** v1 reconnects re-fetch from the connected event's cursor; v2 could let clients send `Last-Event-ID` and resume server-side from that position.
- **Per-user sessions.** No auth model in v1 (admin key only); sessions are job-id-scoped. v2 could add user accounts and per-user job indexes.

Deferred to v2 or upstream PR (dimensions work):
- In-pipeline agent grounding (modify `tradingagents/` to inject dimensions into PM/Trader prompts) → upstream PR path
- LLM-based factor scorer (currently deterministic) → bump to v2.0.0
- Per-analyst structured pillar scoring (Option B) → requires `tradingagents/` edits
- Time-series dimensions / trend rollups
- User-configurable factor weights
- Sector-specific factor weight profiles
- Benchmark-relative factor scores (vs SPY / sector ETF)
- Performance feedback loop (correlate factor scores against realized alpha from memory log)
- Real-time fact refresh without re-running graph
- Multi-currency normalization in factors

Non-goals (never):
- Replacing the analyst agents with dimensions — prose remains primary, dimensions complementary
- Becoming a standalone screener product
- Intraday data

## 12. Risks

| Risk | Mitigation |
|---|---|
| yfinance schema drift | `.get()` with defaults; pin yfinance version in `pyproject.toml` |
| Peer cache cold-start latency | N=25 small; 24h TTL; `scripts/warm_peer_cache.py` admin script for pre-warming |
| LLM structured-output provider variance | Use the existing `tradingagents.agents.schemas` idiom (it already handles Anthropic tool-use / OpenAI json_schema / Gemini response_schema) |
| Extra LLM cost (~10-15%) | Opt-out via `config_overrides.dimensions_enabled = False` |
| Old run records lack dimensions | Both fields `Optional`; UI handles `None`; no migration |

## 13. Definition of Done

- All files in `api/dimensions/` exist with their tests passing
- `api/models.py` exports the new Pydantic schemas
- `api/jobs.py` invokes `build_dimensions` + `build_commentary` post-`propagate()` with failure isolation
- `api/jobs.py` emits the 6 new `stage="dimensions"` progress events (and `dimensions_skipped` on failure)
- `api/jobs.py` honors `cancellation_requested` flag at stage boundaries; `cancelled` is a recognized terminal status
- SSE `GET /jobs/{job_id}/events` emits `type: "connected"` first event with current cursor + status + `retry: 5000`
- All new and modified API endpoints documented in OpenAPI (`/docs`)
- `frontend/src/components/dimensions/` exists with component tests passing
- All 5 pages (Dashboard, Batch, History, HistoryCompare, ScreenerPage) consume dimensions
- `recharts` installed; `npm run build` succeeds
- `pytest tests/dimensions/` passes
- `npm test` passes
- Existing test suites still pass (no regressions in `tests/test_api_*.py`)
- README updated with a short "Dimensions" section pointing to `/screener` and the OpenAPI docs

## 14. References

- Existing structured-output idiom: [tradingagents/agents/schemas.py](../../tradingagents/agents/schemas.py)
- Job lifecycle: [api/jobs.py](../../api/jobs.py)
- Run record persistence: [api/models.py:206](../../api/models.py#L206)
- State store: [api/state_store.py](../../api/state_store.py)
- Upstream sync workflow: [scripts/sync_upstream.sh](../../scripts/sync_upstream.sh)
