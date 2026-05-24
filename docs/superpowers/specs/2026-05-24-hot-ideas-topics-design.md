# Hot Ideas (Topics) — Design Spec

> **Status:** Draft — pending user review
> **Date:** 2026-05-24
> **Owner:** TradingAgents fork (cplog)
> **Scope:** Topic-driven discovery layer that auto-extracts candidate tickers from web research and feeds them into Batch analysis.
> **Architecture choice:** Approach A — Topic-first (see `Approaches considered`).

---

## 1. Goal

Today users must already *know which tickers to analyze* before reaching the Batch page. This spec adds a discovery surface above Batch:

- **On-demand:** user types a theme ("AI 的產業供應鏈"), gets a research surface with extracted candidate tickers, sends a curated subset to Batch in one click.
- **Scheduled:** a small set of curated default themes plus the user's pinned themes refresh on a configurable cadence so that "what's hot right now" is one click away on every visit.

Both flows share a single primitive: a **Topic**. Every search — on-demand or scheduled — produces a **TopicRun** persisted to local KV storage. The on-demand search is just "create-or-update topic and run now."

The feature delivers on the "alphaear-news — hot-topic clustering" line item already promised in [PRODUCT.md](../../../PRODUCT.md).

## 2. Non-goals (v1)

- Multi-tenant per-user pins. Pins are global to a deployment (single-user assumption matches the rest of the product today).
- Email / Slack / push digests.
- Auto-firing Batch on every scheduled refresh. Cron refreshes *research*; Batch is always a user action.
- Cross-topic ticker analytics ("AAPL appears in 5 themes" dashboards).
- Bring-your-own-key Tavily. Single platform key with budget guardrails.
- Localization of system-topic labels.
- Tavily search-depth / time-range tuning UI. Fixed `advanced` + `month` for v1.

## 3. User flows

### 3.1 On-demand search
1. User opens **Hot Ideas** (`/topics`).
2. Types `AI supply chain` into the search bar and submits.
3. Backend creates a `Topic` (or finds an existing one by normalized query), runs the Tavily → LLM extraction pipeline immediately, persists a `TopicRun`, returns both.
4. UI navigates to `/topics/{topic_id}` showing the research surface.
5. User reviews the LLM theme summary, scans the candidate ticker checklist (with confidence + citations), unchecks any false positives, clicks **Send selected to Batch**.
6. App navigates to `/batch?topic={topic_id}&tickers=NVDA,TSM,…`. Batch shows a small "Imported from topic *AI supply chain*" banner and runs as today.

### 3.2 Pinned topics
1. From either the landing page or the detail view, user pins a topic.
2. Pinned topics appear in a dedicated strip on the Hot Ideas landing.
3. User sets a cadence per pin (`off / 6h / 12h / daily`).
4. Scheduler refreshes pinned topics on cadence; landing strip shows "Last refreshed Xh ago".

### 3.3 Curated defaults
1. App ships with ~10–15 hand-picked themes seeded from [api/data/topics_seed.json](../../../api/data/topics_seed.json).
2. Seed is loaded on first boot if missing from `topics:catalog`. Subsequent seed edits add new defaults without overwriting user pins.
3. Defaults appear in a "Trending" grid on Hot Ideas landing.
4. Defaults default to `daily` cadence and cannot be deleted from the UI (system-owned, read-only).

## 4. UI / UX

### 4.1 Hot Ideas landing (`/topics`)
- Reuses `PageFrame` / `PageHeader` for consistent chrome.
- **Search bar** at the top, single text input + submit button. Loading state replaces the button with an inline spinner; full-page navigation only happens on success.
- **"Pinned by you"** section — hidden when empty. Card grid (responsive: 1 / 2 / 3 / 4 columns at sm/md/lg/xl). Each card: label, "Xh ago" refresh chip, top 3 ticker badges, cadence chip, "•••" menu (unpin / open).
- **"Trending"** section — always visible. Same card layout but `system` owner; no unpin affordance.
- Empty state (first visit, no pins): "Pin your first theme — search above to get started." with two example chips ("AI supply chain", "Weight-loss drugs") that submit on click.
- Daily-cap-reached banner (amber) at top: "Daily search budget reached. Resets at midnight UTC." Hides the search submit button.
- Missing-key banner (red): "Tavily API key not configured." with deep-link to Admin → API Keys.

### 4.2 Topic detail (`/topics/{topic_id}`)
Desktop layout — two columns:

- **Left (40%) — Ticker checklist**
  - Header row: "X candidates" + select-all checkbox + market filter toggles (US / HK / A).
  - One row per candidate: checkbox, symbol (link to `/stocks/{symbol}`), confidence pill (e.g. "0.82"), market badge, citation count ("3 sources"), expand caret revealing the 3 citation URLs.
  - Sticky bottom toolbar (appears when ≥1 selected): "**X selected** — [Send to Batch] [Add to Watchlist] [Clear]".
- **Right top (60%) — Theme overview**
  - Breadcrumb: "Hot Ideas / *label*".
  - Markdown summary (100–300 words). Reuse the same markdown renderer as report views.
  - Theme tag pills (max 6).
  - Action row: **Refresh now** (disabled while last refresh < 5 min ago, tooltip explains), cadence `<Select>` (off / 6h / 12h / daily), Pin / Unpin button (user-owned only), Edit query (user-owned only).
- **Right bottom — Source articles**
  - Paginated list, 5 per page.
  - Per article: title (links out, target=_blank), source domain, published date, snippet, expand for raw-content excerpt.

Mobile layout: stacked — Theme overview first, then Ticker checklist, then Articles. Sticky "Send to Batch" toolbar collapses to a single FAB.

Empty / error states inside detail:
- No candidates extracted: "We couldn't find tickers in this topic. Try a more specific query, or check articles below."
- Extraction error: "Extraction failed — articles loaded successfully. Try **Refresh now** in a few minutes." Articles still show.
- Tavily quota error: amber inline notice + auto-disable Refresh button.

### 4.3 Integrations with existing pages
- **Batch** (`/batch`): when `?topic=<id>` present, show small banner: "Imported from topic *<label>* — [view source]". Banner is dismissible.
- **News** (`/news`): below the per-ticker search, when the current ticker appears as a candidate in any topic's latest run, show a "Related themes:" chip strip linking to each topic detail. Hidden when there are zero matches. (Uses precomputed reverse index — see Section 5.4.)
- **Watchlists** (`/watchlists`): "Pin as topic" button on each watchlist opens a small client-side modal pre-filled with the watchlist name as `label` and a suggested Tavily `query` (also derived from the watchlist name). The user edits if desired and clicks Save, which fires the same `POST /api/topics/search` endpoint with `pin: true` — there is no separate create-without-running endpoint.
- **Admin** (`/admin`): `TAVILY_API_KEY` joins the existing redact/persist treatment — no special UI work beyond adding the constant to the allow-list.
- **Jobs ribbon**: no changes. Batch jobs launched from Topics use the same `submitBatch` API and naturally appear in the ribbon.

### 4.4 Component inventory (new)
- `frontend/src/pages/TopicsPage.tsx` — landing
- `frontend/src/pages/TopicDetailPage.tsx` — detail
- `frontend/src/components/topics/TopicCard.tsx`
- `frontend/src/components/topics/TickerCandidateRow.tsx`
- `frontend/src/components/topics/ThemeSummary.tsx`
- `frontend/src/components/topics/ArticleList.tsx`
- `frontend/src/components/topics/CadenceSelect.tsx`
- `frontend/src/components/topics/MarketBadge.tsx` (US / HK / A)
- `frontend/src/hooks/useTopics.ts` — list + cache invalidation
- `frontend/src/hooks/useTopicDetail.ts` — single-topic + manual refresh
- Routes added in [frontend/src/navigation/routes.ts](../../../frontend/src/navigation/routes.ts): `paths.topics = "/topics"` and `topicPath(id)` builder. Nav link slot in `Layout.tsx` between **News** and **Watchlists** (Monitor stays where it is).

## 5. Backend architecture

### 5.1 Data model (`api/topics_models.py`)

```python
class Topic(BaseModel):
    id: str                      # slug for system topics, uuid4 for user
    label: str
    query: str                   # Tavily search string
    owner: Literal["system", "user"]
    cadence: Literal["off", "6h", "12h", "daily"]
    created_at: datetime
    last_run_at: datetime | None
    last_run_id: str | None
    pinned: bool                 # only meaningful when owner == "user"

class TickerCandidate(BaseModel):
    symbol: str                  # normalized
    name: str | None
    market: Literal["US", "HK", "A"] | None
    confidence: float            # 0..1
    citations: list[str]         # article URLs

class TopicArticle(BaseModel):
    title: str
    url: str
    source: str                  # domain
    snippet: str
    published_at: datetime | None

class TopicRun(BaseModel):
    id: str                      # uuid4
    topic_id: str
    ran_at: datetime
    query: str                   # snapshot at run time
    articles: list[TopicArticle]
    candidates: list[TickerCandidate]
    summary_md: str
    theme_tags: list[str]        # max 6
    extraction_model: str        # provider/model id, for audit
    error: str | None            # set when extraction partially failed
```

### 5.2 Storage (`api/topics_store.py`)

Reuses `api/state_store.py` (JSON-on-disk locally, Cloudflare KV in prod). No D1 in v1.

| Key | Value | Purpose |
|---|---|---|
| `topics:catalog` | `list[Topic]` | Single source of truth for what exists |
| `topics:run:{topic_id}:latest_id` | `str` | O(1) latest-run lookup |
| `topics:run:{topic_id}:{run_id}` | `TopicRun` | Full run blob |
| `topics:run:{topic_id}:history` | `list[str]` | Run id history, capped at **14**; oldest auto-pruned |
| `topics:reverse_index` | `dict[symbol, list[topic_id]]` | Powers News "Related themes" chips |
| `topics:budget:YYYY-MM-DD` | `{count: int}` | Daily Tavily-call budget counter |

System topics are seeded from [api/data/topics_seed.json](../../../api/data/topics_seed.json) on app startup *only* when missing from `topics:catalog`. Re-seeding adds new system topics; never overwrites user-pinned ones. System topics cannot be deleted via the API.

### 5.3 Tavily client (`api/tavily.py`)

- Uses the `tavily-python` SDK.
- Reads `TAVILY_API_KEY` via `state_store.get_str("TAVILY_API_KEY")` falling back to env var (same pattern as other persisted secrets).
- Fixed query params for v1: `search_depth="advanced"`, `time_range="month"`, `max_results=10`, `include_raw_content="text"`, `include_usage=True`.
- Returns `list[TopicArticle]` normalized from Tavily response, dropping items with missing URL or empty content.
- Raises typed exceptions: `TavilyMissingKey`, `TavilyRateLimited(retry_after)`, `TavilyUpstreamError`. Surfaced as 503/429/502 in the API layer.
- All Tavily calls increment `topics:budget:{today}.count`. If `count >= TAVILY_DAILY_CAP` (env, default `100`), scheduled refreshes pause and on-demand requests return 429 with a friendly message.

**Security:** key never logged. Key never returned by `/config` (already redacted by existing config logic once added to the allow-list).

### 5.4 Extraction pipeline (`api/topics_extract.py`)

Single function `extract(query: str, articles: list[TopicArticle]) -> ExtractionResult`:

```python
class ExtractionResult(BaseModel):
    summary_md: str         # 100..300 words, markdown
    theme_tags: list[str]   # max 6
    candidates: list[TickerCandidate]
```

- Uses an LLM with structured output (Pydantic schema), reusing the structured-output adapter pattern at [api/llm_clients/structured_output.py](../../../api/llm_clients/structured_output.py) so Ollama works too.
- LLM selection: same provider chain as the dimensions builder; respects per-request override headers (so admins can route extraction to a cheaper model).
- Prompt skeleton (full text lives in the module):
  > Given the following recent articles about *<query>*, extract publicly traded companies that are materially relevant. For each company return: ticker (US / HK / A-share, exchange-prefixed where needed), market, confidence 0..1, and the article URLs that support the mention. Then write a 100–300 word markdown summary explaining what's driving this theme right now and which sub-themes are emerging. Output 0–6 short theme tags.
- Confidence calibration: the LLM returns an initial confidence per candidate; the orchestrator then **adjusts** that value with these rules (in order):
  - Cap at `0.9` (we never claim certainty).
  - Mentioned in ≥2 distinct articles → bump by `+0.1`, then re-cap at `0.9`.
  - Mentioned in exactly 1 article → clip to `≤0.5`.
  The adjusted value is what's stored on `TickerCandidate.confidence`.
- Normalization: each `symbol` runs through `api.tickers.normalize_ticker`. Candidates that don't resolve are dropped (logged at INFO).
- On LLM failure: catch, log, return `ExtractionResult(summary_md="", theme_tags=[], candidates=[])` and let the caller set `TopicRun.error`. Articles still persist — the user can still read them.

### 5.5 Orchestrator (`api/topics.py`)

Coordinates a single run end-to-end:

```python
def run_topic(topic: Topic) -> TopicRun:
    articles = tavily.search(topic.query)
    extraction = extract(topic.query, articles)
    run = TopicRun(..., articles=articles, **extraction.dict())
    topics_store.save_run(topic.id, run)
    topics_store.update_reverse_index(topic.id, [c.symbol for c in run.candidates])
    topics_store.touch_topic(topic.id, run.id, run.ran_at)
    return run
```

Reverse-index update strategy: when saving a new run, diff the candidate symbols against the previous run's symbols for the same topic; remove dropped, add new. O(|symbols|) per save.

### 5.6 Scheduler (in `api/topics.py`, started from `api/main.py` lifespan)

- Long-running asyncio task launched alongside the existing `jobs.Worker`.
- Wakes every **60 seconds** (tight enough to honor 6h cadence boundaries cleanly; cheap).
- For each topic where `cadence != "off"` and `(now - last_run_at) >= cadence_interval`: enqueue a refresh.
- Refreshes run sequentially (single Tavily call at a time) to keep upstream rate-limit pressure low.
- Per-topic min-refresh-interval gate: 5 minutes between any two runs (manual or scheduled), enforced in the orchestrator.
- Daily-cap gate: scheduler skips topics for the rest of the day if budget is exhausted.
- Errors during scheduled refresh: persisted on the `TopicRun.error` field; loop continues; logged at WARNING. Three consecutive failures → topic auto-disabled (`cadence` → `"off"`) and an `error` field surfaced on the next API read so the UI can prompt the user to fix the query.

## 6. API surface

All routes mounted on the existing FastAPI `app` in `api/main.py`, following the same flat-decorator style as the existing handlers. Both `/topics/...` and `/api/topics/...` aliases registered (consistent with the rest of the codebase).

| Method | Path | Body / Query | Returns |
|---|---|---|---|
| GET | `/api/topics` | — | `list[TopicSummary]` (system + user, with `last_run_at` and top-3 ticker symbols) |
| GET | `/api/topics/{id}` | — | `{topic: Topic, latest_run: TopicRun \| null}` |
| GET | `/api/topics/{id}/runs` | — | `list[TopicRun]` (capped at 14, newest first) |
| POST | `/api/topics/search` | `{query, label?, cadence?, pin?}` | `{topic: Topic, run: TopicRun}` — creates-or-updates topic by normalized query and runs now |
| POST | `/api/topics/{id}/refresh` | — | `{run: TopicRun}` (429 if within 5 min of last run, 429 if daily cap hit) |
| PATCH | `/api/topics/{id}` | `{label?, query?, cadence?}` | `Topic`. `cadence` may be updated on any topic (system or user). `label` and `query` are user-owned-only; 403 if attempted on a system topic. |
| POST | `/api/topics/{id}/pin` | — | `Topic` (user-owned only; flips `pinned`) |
| DELETE | `/api/topics/{id}/pin` | — | `Topic` |
| DELETE | `/api/topics/{id}` | — | `204` (user-owned only) |

**Query normalization** (for create-or-update on `/search`): lowercased, whitespace-collapsed, trailing punctuation stripped. Two queries that normalize the same are treated as the same topic.

**TopicSummary** (`list` endpoint) is a lightweight projection — avoids streaming full articles + summary for every card on the landing page.

## 7. Approaches considered

- **A. Topic-first ("research bank")** — *chosen.* Single entity, single code path for on-demand and scheduled, natural history.
- **B. Search-first with promote-to-pin** — Lower friction for casual use, but two code paths (ephemeral vs persisted) and harder to share results.
- **C. Curated-only MVP** — Smallest scope but does not deliver the "both modes" the user confirmed.

## 8. Testing

### 8.1 Backend
- `api/topics_extract.py` unit tests with mocked LLM client: assert ticker normalization, confidence calibration rules, unresolved-symbol drop, summary length bounds.
- `api/topics_store.py` round-trip tests using an in-memory StateStore: catalog read/write, history cap-at-14 auto-prune, reverse-index diff on save.
- `api/tavily.py` unit tests against a recorded fixture response: normalization, missing-field tolerance, error-class mapping.
- `api/main.py` integration tests for each route with the Tavily and LLM clients monkey-patched. Assert: query normalization on `/search`, `pin` flip, 403 for system-topic edits, 429 on min-refresh-interval, 429 on daily-cap, `?topic=<id>` round-trip via the Batch banner test.
- Scheduler test with a fake clock: assert cadence triggers fire, budget guardrail pauses, three-consecutive-failure auto-disable kicks in.

### 8.2 Frontend
- `TopicsPage.test.tsx`: renders Pinned and Trending sections; search submits and navigates with the returned topic id; empty-state copy renders when no pins.
- `TopicDetailPage.test.tsx`: select-some-tickers + Send-to-Batch builds the correct `/batch?topic=…&tickers=…` URL; cadence change PATCHes and updates UI; Refresh disabled within 5-minute window.
- `NewsPage.test.tsx`: "Related themes" chip strip renders for a ticker present in the reverse index, hidden otherwise.
- `BatchPage.test.tsx`: "Imported from topic" banner renders when `?topic=` present.

### 8.3 Smoke
- `scripts/smoke_topics.sh` — `POST /api/topics/search` with `{"query": "AI supply chain"}` against a running local API, prints topic id + first 5 candidates. Skipped if `TAVILY_API_KEY` is unset.

## 9. Rollout

- Single PR per layer (data model → tavily client → extractor → orchestrator+scheduler → API → frontend) or one bundled PR — to be decided in the implementation plan.
- New env vars: `TAVILY_API_KEY` (required for the feature; absence shows the missing-key banner and disables search), `TAVILY_DAILY_CAP` (optional, default `100`).
- Seed `api/data/topics_seed.json` with 10–15 initial themes spanning US / HK / A-share markets. Initial list to be drafted during implementation.
- No DB migrations.
- Honors the [fork rule](../../../.claude/projects/-Users-erictaicp-work-TradingAgents/memory/feedback-no-tradingagents-edits.md) — zero edits inside `tradingagents/`. All code lives in `api/`, `frontend/`, `scripts/`, `docs/`.

## 10. Open questions

None blocking implementation. Items to confirm during plan-writing:
- Exact initial 10–15 seed themes (content question, not architectural).
- Whether the Topics landing should auto-refresh the "last refreshed Xh ago" chips on a timer or only on focus/visit.

---

*End of spec.*
