# USERFLOW.md — TradingAgents Web UX

> **Version**: 2.0-aligned  
> **Last Updated**: 2026-05-17  
> **Scope**: User flows that match **this repository’s shipped UI + API** (`frontend/` + `api/`).  
> **Design notes**: [DESIGN.md](DESIGN.md)  
> **Broader product vision** (extra analysts, Kronos, dedicated `/runs/*` routes, PDF exports, etc.): see [PRODUCT.md](PRODUCT.md) — not implemented here unless noted below.

---

## Implementation snapshot

| Layer | What exists |
|-------|-------------|
| **SPA routes** | `/dashboard`, `/history`, `/history/stats`, `/batch`, `/screener`, `/sectors`, `/news`, `/watchlists`, `/system`, `/admin`; redirects **`/settings` → `/system`**, **`/configure` → `/dashboard`**; deep links **`/runs/:jobId`** and **`/runs/:jobId/results`** → dashboard with `?job=` (+ optional `tab=reports`) ([`frontend/src/App.tsx`](frontend/src/App.tsx)) |
| **Analysis jobs** | `POST /analyze` or **`POST /api/analyze`** → `job_id`; poll `GET /jobs/{job_id}`; stream `GET /jobs/{job_id}/events`; cancel `POST /jobs/{job_id}/cancel`; markdown artifact `GET /jobs/{job_id}/report` ([`api/main.py`](api/main.py)) |
| **Batch** | `POST /batches` or **`POST /api/batches`**, `GET /batches/{batch_id}` |
| **History** | `GET /api/history/runs`, `GET /api/history/runs/{run_id}`, compare, delete, recompute dimensions |
| **Analysts (configurable)** | `market`, `social` (sentiment), `news`, `fundamentals` — see [`api/models.py`](api/models.py) `AnalystId` |
| **LangGraph** | Selected analysts → tool-using nodes → bull/bear debate → research manager → trader → risk debate → portfolio manager; optional **dimensions** pass ([`tradingagents/graph/setup.py`](tradingagents/graph/setup.py)) |
| **Watchlists** | Browser-local list (`localStorage` key `ta:watchlist`) on **`/watchlists`** — links to **`/dashboard?ticker=`** |
| **History stats** | **`/history/stats`** — client-side aggregates over `GET /api/history/runs?limit=500` (rating distribution, avg confidence) |

---

## Table of Contents

1. [User Personas](#1-user-personas)
2. [Flow A: Single-Ticker Analysis](#2-flow-a-single-ticker-analysis-primary)
3. [Flow B: Batch (full pipeline per ticker)](#3-flow-b-batch-full-pipeline-per-ticker)
4. [Flow C: Screener (dimensions snapshot only)](#4-flow-c-screener-dimensions-snapshot-only)
5. [Flow D: History](#5-flow-d-history)
6. [Flow E: System & Admin](#6-flow-e-system--admin)
7. [Flow F: News, Sectors & Watchlists](#7-flow-f-news-sectors--watchlists)
8. [API Quick Reference](#8-api-quick-reference)
9. [Server-side pipeline (behind the dashboard)](#9-server-side-pipeline-behind-the-dashboard)
10. [Errors & Edge Cases](#10-errors--edge-cases)
11. [State Machine (job-centric)](#11-state-machine-job-centric)
12. [Screen Inventory](#12-screen-inventory)
13. [Future UX (not in repo)](#13-future-ux-not-in-repo)

---

## 1. User Personas

### Alex (Retail Trader, Primary)
- **Goals**: Run one ticker through the full agent pipeline; read rating, rationale, analyst markdown, and optional factor dimensions.
- **Primary path**: `/dashboard` → submit job → stay on dashboard for progress + results.

### Bob (Researcher / Power User, Primary)
- **Goals**: Batch many tickers; sort/filter by dimension scores; compare historical runs.
- **Primary paths**: `/batch`, `/history`, `/screener` (quick factor table without full LLM run).

### Charlie (Operator, Secondary)
- **Goals**: Confirm API health, data-source checks, runtime LLM settings, cache clears.
- **Primary paths**: `/system`, `/admin` (links / maintenance).

---

## 2. Flow A: Single-Ticker Analysis (Primary)

### A.1 Entry

**Route**: `/dashboard` (nav label **Analysis**).

**User actions**:
1. Enter ticker (e.g. `AAPL`, `0700.HK`, or exchange-specific symbols supported by data vendors).
2. (Optional) Choose **report format**: markdown (default), JSON, or structured — see `AnalyzeRequest.report_format` in [`api/models.py`](api/models.py).
3. Toggle **analysts**: Market, Social Media (sentiment), News, Fundamentals. Omitting the list defaults to **all four** on the server.
4. (Optional) Open **Advanced**: LLM provider/models/backend URL, temperature, `max_debate_rounds`, `max_risk_discuss_rounds`, data vendor strings / tool routing keys as exposed in the form (passed via `config_overrides`).
5. Click **Run** → client calls `POST /analyze` with `{ ticker, date?, analysts?, report_format, config_overrides? }`.

**Response**: `{ job_id, status, created_at }`. UI stores `job_id` and begins polling + SSE.

**Deep links**: Share or bookmark **`/runs/{job_id}`** (loads the same job on `/dashboard?job=`) or **`/runs/{job_id}/results`** (`tab=reports`). Invalid or evicted worker jobs strip `job` from the query and show an inline notice.

### A.2 In progress

**Streams**: `GET /jobs/{job_id}/events` — server-sent style stream of status/log updates (see [`api/main.py`](api/main.py) `event_gen`).

**Poll**: `GET /jobs/{job_id}` for `status`, `result`, `error`.

**Cancel**: `POST /jobs/{job_id}/cancel`.

**What the UI shows** (conceptually — not per LangGraph node names):
- Progress derived from events + job status (`queued` → `running` → `completed` | `failed`).
- Live event list / terminal message when stream ends.

**Not in this repo (still)**: Per LangGraph node rows labeled “Hot Money / Policy / Lockup / Kronos”, Draw.io / PDF export from the SPA.

### A.3 Complete

**When** `status === "completed"`:

- **Result payload** includes extracted **rating** (5-tier), optional **confidence**, **reports** (markdown sections), optional **structured** snapshot, optional **dimensions** + **dimensions_commentary**, flags such as **dimensions_in_graph** ([`AnalysisResult`](api/models.py)).
- **Dimensions**: If present, **DimensionsPanel** / study tab shows factor pillars, radar, commentary.
- **Download report**: `GET /jobs/{job_id}/report` returns the saved **markdown** file (`text/markdown`), not PDF.

**Failed jobs**: `error` string on job record; UI should surface it inline.

---

## 3. Flow B: Batch (full pipeline per ticker)

**Route**: `/batch`.

**User actions**:
1. Paste comma- or newline-separated tickers.
2. Select same four analyst toggles as dashboard.
3. Submit → `POST /batches` (see [`frontend/src/api.ts`](frontend/src/api.ts) `submitBatch`).
4. Poll `GET /batches/{batch_id}` for per-job rows + summary counts.

**UI extras** ([`BatchPage.tsx`](frontend/src/pages/BatchPage.tsx)):
- Factor score columns when dimensions are loaded per completed job (`GET /jobs/{job_id}/dimensions`).
- URL-persisted **minimum factor filters** (`?min_value=50` etc.).

**Not in this repo (still)**: Watchlist import from CSV, ZIP of PDFs, aggregate scatter “confidence vs return” charts as in PRODUCT mocks.

---

## 4. Flow C: Screener (dimensions snapshot only)

**Route**: `/screener`.

**Important**: This flow calls **`GET /api/dimensions/{ticker}`** (and `getDimensionsByTicker` in the client) to fetch **precomputed / preview dimensions** — it does **not** enqueue a full LangGraph analysis for each row.

**Use case**: Quick comparison table of factor scores across many symbols without LLM cost.

---

## 5. Flow D: History

**Route**: `/history`.

**User actions**:
- List runs: `GET /api/history/runs` (filters via query params as implemented).
- Open detail: `GET /api/history/runs/{run_id}` — markdown report sections, dimensions snapshot, metadata.
- Compare runs: `POST /api/history/compare`.
- Delete run: `DELETE /api/history/runs/{run_id}`.
- Recompute dimensions for an older run: `POST /api/history/runs/{run_id}/recompute-dimensions`.

**Also**: **`/history/stats`** — lightweight aggregates (rating counts, average confidence) over `GET /api/history/runs?limit=500`. Per-analyst accuracy / win rate vs realized returns are **not** computed here (see PRODUCT mocks for that vision).

---

## 6. Flow E: System & Admin

### `/system` — [`SystemPage.tsx`](frontend/src/pages/SystemPage.tsx)

- **Health**: `GET /api/health` — LLM key configured, provider, state store, paths, optional **data_source_checks** table.
- **Read config**: `GET /config` (redacted/safe view).
- **Runtime LLM patch**: `POST /admin/runtime-config` with admin secret header as implemented.
- **Clear cache**: `POST /admin/cache/clear`.

### `/admin` — [`AdminPage.tsx`](frontend/src/pages/AdminPage.tsx)

- Convenience links and operational actions (jobs clear, peer cache refresh intents, etc.) — see live page for current buttons.

**Not in this repo**: Full-page vendor matrix UI (`a_stock` vs `unified` news), FinBERT/Kronos file pickers, NewsNow TTL sliders — configure those via env + `DEFAULT_CONFIG` / runtime overrides as supported by the API.

---

## 7. Flow F: News, Sectors & Watchlists

- **`/news`**: [`NewsPage.tsx`](frontend/src/pages/NewsPage.tsx) — browse news feed via API (`GET /news/{ticker}` etc.).
- **`/sectors`**: [`SectorIndustryPage.tsx`](frontend/src/pages/SectorIndustryPage.tsx) — sector/industry catalog and related API helpers.
- **`/watchlists`**: [`WatchlistPage.tsx`](frontend/src/pages/WatchlistPage.tsx) — browser-local symbol list (`localStorage`), links to **`/dashboard?ticker=`**.

---

## 8. API Quick Reference

| Action | Method | Path |
|--------|--------|------|
| Submit analysis | POST | `/analyze` (alias: **`/api/analyze`**) |
| Batch submit | POST | `/batches` (alias: **`/api/batches`**) |
| Batch status | GET | `/batches/{batch_id}` |
| List jobs | GET | `/jobs` |
| Job status | GET | `/jobs/{job_id}` |
| Job event stream | GET | `/jobs/{job_id}/events` |
| Cancel job | POST | `/jobs/{job_id}/cancel` |
| Download markdown report | GET | `/jobs/{job_id}/report` |
| Job dimensions | GET | `/jobs/{job_id}/dimensions` |
| Health | GET | `/api/health` |
| Config snapshot | GET | `/config` |
| Dimensions preview | GET | `/api/dimensions/{ticker}` |
| History list | GET | `/api/history/runs` |
| History detail | GET | `/api/history/runs/{run_id}` |
| History compare | POST | `/api/history/compare` |
| Delete history run | DELETE | `/api/history/runs/{run_id}` |
| Recompute dimensions | POST | `/api/history/runs/{run_id}/recompute-dimensions` |

*Prefix note*: In production the SPA is often served from the same origin as FastAPI; Vite dev proxy forwards `/analyze`, `/jobs`, `/api/*`, etc. See [`frontend/src/api.ts`](frontend/src/api.ts).

---

## 9. Server-side pipeline (behind the dashboard)

The browser does **not** expose each LangGraph node as a separate navigable “step.” Rough order after analysts:

1. Tool subgraphs per analyst (market / sentiment / news / fundamentals).
2. Bull ↔ Bear debate (round count from config).
3. Research manager (investment plan).
4. Trader (transaction proposal).
5. Risk team debate.
6. Portfolio manager (final markdown + extracted tier rating).
7. Optional **dimensions_snapshot** when enabled in config ([`dimensions_enabled`](tradingagents/default_config.py), [`dimensions_in_graph`](tradingagents/default_config.py)).

For checkpoint/resume behavior, LLM keys, and vendor routing semantics, see [AGENTS.md](AGENTS.md) and [`tradingagents/graph/`](tradingagents/graph/).

---

## 10. Errors & Edge Cases

| Situation | Expected behavior |
|-----------|-------------------|
| Missing LLM API key | `/api/health` shows misconfiguration; analyze may fail fast with error message. |
| Job failure | `GET /jobs/{job_id}` returns `status: failed` + `error`. |
| Invalid ticker | Data vendor returns empty/error; analyst reports may say “no data”; user retries with corrected symbol. |
| Rate limits (e.g. Alpha Vantage) | Router tries next vendor where implemented ([`tradingagents/dataflows/interface.py`](tradingagents/dataflows/interface.py)). |
| Batch partial failure | Each ticker is its own job; failed rows show in batch summary without blocking siblings. |
| Cancel | Best-effort cancel; completed jobs cannot uncancel. |

**Checkpoint resume**: Supported when enabled in **framework config** for CLI/LangGraph runs ([AGENTS.md](AGENTS.md)); the web UI does not currently expose a dedicated “resume from checkpoint” button — treat as future UX.

---

## 11. State Machine (job-centric)

```
[IDLE on /dashboard]
    │ submit analyze
    ▼
[QUEUED/RUNNING] ──SSE/poll──► stream updates
    │
    ├── success ──► [COMPLETED] view reports + dimensions + download .md
    ├── failed ──► [FAILED] show error
    └── cancel ──► [CANCELLED or terminal error state]
```

History persists completed runs for later reopen under `/history`. Opening **`/runs/{job_id}`** while a job still lives in the worker revisits the same in-flight or finished UI state on `/dashboard`.

---

## 12. Screen Inventory

| # | Screen | Route | Notes |
|---|--------|-------|--------|
| 1 | Analysis / Dashboard | `/dashboard` | Single-ticker jobs, `?job=` deep link, dimensions study tab (`?tab=study` \| `reports`) |
| 2 | History | `/history` | List + detail + compare + delete + recompute dimensions |
| 3 | History statistics | `/history/stats` | Rating distribution + avg confidence (recent runs) |
| 4 | Batch | `/batch` | Multi-ticker full runs + factor filters |
| 5 | Screener | `/screener` | Dimensions-only table |
| 6 | Sectors | `/sectors` | Sector/industry helpers |
| 7 | News | `/news` | News feed UI |
| 8 | Watchlists | `/watchlists` | Local-only symbol list |
| 9 | System | `/system` | Health, runtime config, cache (`/settings` redirects here) |
| 10 | Admin links | `/admin` | Operational shortcuts |
| — | Configure shortcut | `/configure` | Redirects to **`/dashboard`** |
| — | Job deep link | `/runs/:jobId`, `/runs/:jobId/results` | Redirect into dashboard job loader |

Global layout + nav: [`frontend/src/components/Layout.tsx`](frontend/src/components/Layout.tsx).

---

## 13. Future UX (not in repo)

Items that appear in [PRODUCT.md](PRODUCT.md) / older drafts but **are still not** fully implemented:

- Separate SPA surfaces per analyst stage, **signals** hub, or sentiment/Kronos-only routes beyond dashboard tabs.
- **OHLCV candlestick panel**, **Kronos forecast band**, and **interactive evidence-chain map** (Draw.io / graph) — dashboard shows placeholder cards until job payloads expose these artifacts.
- PDF / Draw.io / ZIP export pipelines from the SPA (HTML + markdown export exist on dashboard).
- Push notifications (“reflection ready”, gateway outages).
- Dedicated mobile layouts and global keyboard shortcuts (specified in code).

**Recently shipped in this repo (2026-05):**

- Retro digital design tokens + shared `.ui-*` primitives on Dashboard, News, Screener, Batch.
- Dashboard **pipeline stage list** with per-stage elapsed times and heartbeat copy during long LangGraph runs.
- **Sentiment timeline** chart on `/news`; **rating distribution** chart on `/history/stats`.
- **Dimensions radar** hero on dashboard results when dimensions are present.
- **Batch ↔ Screener** cross-links and screener → batch handoff via `?tickers=`.

*`/runs/:jobId/*`, `/watchlists`, `/history/stats`, `/api/analyze`, `/settings` → `/system`, and `/configure` are implemented.*

When further items ship, update **Version** above and merge relevant bullets back into sections 2–7.
