# Leveraging last30days-skill in TradingAgents — Analysis

> Analysis of https://github.com/mvanhorn/last30days-skill v3.3.2 and integration opportunities for TradingAgents.

---

## 1. What last30days-skill Does (The "Why")

**Core thesis:** "Google aggregates editors. /last30days searches people."

It is a **multi-source social research engine** that searches Reddit, X/Twitter, YouTube, TikTok, Instagram, Hacker News, Polymarket, GitHub, Bluesky, Threads, Pinterest, Digg, Perplexity, and the web — in parallel — then scores results by **real human engagement** (upvotes, likes, views, real-money bets) rather than SEO.

Key differentiators:
- **Engagement-scored relevance** — A Reddit thread with 1,500 upvotes > a blog post nobody read
- **Cross-source cluster merging** — Same story on Reddit + X + YouTube = one cluster
- **LLM-powered planning** — Breaks topics into subqueries with per-source targeting
- **Entity resolution** — Auto-resolves X handles, GitHub users, subreddits for named entities
- **Comparison mode** — "X vs Y" fans out parallel pipelines per entity
- **Polymarket integration** — Real-money prediction market odds, not pundit guesses

---

## 2. Architecture Deep-Dive

### 2.1 Pipeline Orchestration (`pipeline.py`)

```
Topic → Planner (LLM) → SubQueries
   ↓
Parallel Retrieval (ThreadPoolExecutor, max 16 workers)
   ↓
Normalization → Signal Annotation → Deduplication → Snippet Extraction
   ↓
Weighted RRF Fusion → LLM Reranking → Fun Scoring
   ↓
Clustering → Report
```

**Depth settings:**
| Mode | per_stream | pool | rerank |
|------|-----------|------|--------|
| quick | 6 | 15 | 12 |
| default | 12 | 40 | 40 |
| deep | 20 | 60 | 60 |

**Key insight:** The planner generates `SubQuery` objects with `label`, `search_query`, `ranking_query`, `sources`, and `weight`. The `ranking_query` is often *different* from the `search_query` — it tells the reranker what to look for in the retrieved content.

### 2.2 Data Sources & Access Patterns

| Source | API / Access | Key / Auth | Cost |
|--------|-------------|------------|------|
| **Reddit** | Public JSON (`search.json`) + ScrapeCreators backup | None / `SCRAPECREATORS_API_KEY` | Free |
| **Hacker News** | Algolia API | None | Free |
| **Polymarket** | Gamma API | None | Free |
| **GitHub** | GitHub REST API or `gh` CLI | `GITHUB_TOKEN` (optional) | Free tier |
| **YouTube** | yt-dlp + transcript extraction | None | Free |
| **X/Twitter** | Bird CLI, xAI API, xurl CLI, or browser cookies | Various | Free / PAYG |
| **TikTok/IG/Threads** | ScrapeCreators API | `SCRAPECREATORS_API_KEY` | 100 free credits, then PAYG |
| **Bluesky** | AT Protocol API | App password | Free |
| **Web** | Brave Search, Exa, Serper, Parallel | API keys | Free tiers / PAYG |
| **Perplexity** | OpenRouter proxy | `OPENROUTER_API_KEY` | PAYG |
| **Digg** | `digg-pp-cli` | None | Free |

### 2.3 Normalization & Schema (`schema.py`)

All raw items normalize to `SourceItem`:
```python
@dataclass
class SourceItem:
    item_id: str
    source: str          # "reddit", "x", "hackernews", ...
    title: str
    body: str
    url: str
    author: str | None
    container: str | None   # subreddit, channel, etc.
    published_at: str | None
    engagement: dict[str, float | int]  # upvotes, likes, views, etc.
    relevance_hint: float
    why_relevant: str
    snippet: str
    metadata: dict
    # Signal fields (populated post-retrieval):
    local_relevance: float | None
    freshness: int | None
    engagement_score: float | None
    source_quality: float | None
```

This is **exactly** what TradingAgents needs for structured social data.

### 2.4 Fusion & Reranking (`fusion.py`, `rerank.py`)

**Weighted RRF** (Reciprocal Rank Fusion):
```python
def weighted_rrf(items_by_source_and_query, plan, pool_limit=40):
    # Combines per-source, per-subquery rankings into global candidates
    # Weighted by subquery weight and source weights from plan
```

**LLM Reranking:** After RRF, an LLM re-scores top candidates for relevance to the topic, producing `rerank_score` and `explanation`.

**Fun Scoring:** A second LLM pass scores for humor/virality — produces "Best Takes" section.

### 2.5 Clustering (`cluster.py`)

Entity-based overlap detection merges cross-source matches even when titles use different words. Produces `Cluster` objects with uncertainty markers (`single-source`, `thin-evidence`).

---

## 3. Current TradingAgents State

### 3.1 What We Already Have

| Feature | Status | Location |
|---------|--------|----------|
| Reddit (public JSON) | ✅ Basic | `tradingagents/dataflows/reddit.py` |
| StockTwits | ✅ Basic | `tradingagents/dataflows/stocktwits.py` |
| Yahoo Finance news | ✅ | `tradingagents/dataflows/yfinance_news.py` |
| Finnhub news | ✅ | `tradingagents/dataflows/finnhub_data.py` |
| Google RSS news | ✅ | `tradingagents/dataflows/rss_news.py` |
| Multi-vendor routing | ✅ | `tradingagents/dataflows/interface.py` |
| Sentiment Analyst | ✅ | `tradingagents/agents/analysts/sentiment_analyst.py` |
| Topics extraction | ✅ | `api/topics_extract.py` |

### 3.2 What's Missing vs. last30days

| Capability | TradingAgents | last30days |
|------------|--------------|------------|
| **Parallel multi-source retrieval** | ❌ Sequential per analyst | ✅ ThreadPoolExecutor, 16 workers |
| **LLM query planning** | ❌ Static prompts | ✅ Dynamic subqueries per topic |
| **Cross-source fusion (RRF)** | ❌ Analysts siloed | ✅ Global ranking |
| **LLM reranking** | ❌ No rerank step | ✅ Post-fusion LLM scoring |
| **Clustering / deduplication** | ❌ Per-source only | ✅ Cross-source entity merge |
| **Hacker News** | ❌ | ✅ Free Algolia API |
| **Polymarket** | ❌ | ✅ Free Gamma API |
| **YouTube transcripts** | ❌ | ✅ yt-dlp |
| **TikTok / Instagram** | ❌ | ✅ ScrapeCreators |
| **X/Twitter** | ❌ | ✅ Multiple backends |
| **Bluesky** | ❌ | ✅ AT Protocol |
| **Perplexity Sonar** | ❌ | ✅ Via OpenRouter |
| **Engagement scoring** | ❌ Basic (upvotes only) | ✅ Multi-signal scoring |
| **Comparison mode** | ❌ | ✅ Parallel fan-out |
| **Entity resolution** | ❌ | ✅ Auto-resolve handles/repos |

---

## 4. Integration Strategies (Ranked by Impact / Effort)

### Strategy A: "Hot Money 2.0" — Polymarket + HN + Reddit Enhancement
**Effort:** Low | **Impact:** High

**What:** Add Polymarket and Hacker News as new dataflow modules. Enhance existing Reddit with last30days' public-JSON + comment-enrichment patterns.

**Why Polymarket matters for TradingAgents:**
- Real-money prediction markets are **harder to manipulate** than social sentiment
- "Will {ticker} beat earnings?" markets exist for major stocks
- Odds move faster than analyst consensus
- Free API, no key needed

**Why HN matters:**
- Tech-stock signal (NVDA, AMD, cloud names) is strong on HN
- Developer sentiment is a leading indicator for SaaS / infra names
- Free Algolia API

**Files to create/modify:**
```
tradingagents/dataflows/polymarket.py      # NEW
tradingagents/dataflows/hackernews.py      # NEW
tradingagents/dataflows/reddit.py          # ENHANCE (add comment fetching)
tradingagents/dataflows/interface.py       # REGISTER new vendors
tradingagents/agents/analysts/hot_money_analyst.py  # ENHANCE
```

**Polymarket API pattern (from last30days):**
```python
# Gamma API — free, no auth
# https://gamma-api.polymarket.com/markets?limit=100&active=true&closed=false
# Filter by keyword matching in title/question
```

**HN API pattern:**
```python
# Algolia — free, no auth
# https://hn.algolia.com/api/v1/search?query={ticker}&tags=story&numericFilters=created_at_i>{from_ts}
```

---

### Strategy B: "Sentiment Analyst 2.0" — Multi-Source Parallel Pipeline
**Effort:** Medium | **Impact:** High

**What:** Redesign the Sentiment Analyst to use last30days-style parallel retrieval + fusion, but scoped to ticker-specific queries.

**Current state:** Sentiment Analyst fetches news → StockTwits → Reddit sequentially, then prompts the LLM once.

**Proposed state:**
```
Sentiment Analyst Node
  ├─ Planner: generate subqueries for {ticker}
  │     e.g., "NVDA earnings", "NVDA stock", "Nvidia GPU demand"
  ├─ Parallel Fetch (ThreadPoolExecutor)
  │     ├─ Reddit (r/wallstreetbets, r/stocks, r/investing, r/NVDA_stock)
  │     ├─ StockTwits
  │     ├─ Hacker News (if tech ticker)
  │     ├─ Polymarket (if markets exist)
  │     ├─ Yahoo Finance news
  │     └─ Finnhub news
  ├─ Normalize → RRF Fusion → Top-K selection
  └─ Single LLM call with structured evidence block
```

**Key code to borrow from last30days:**
- `lib/schema.py` → `SourceItem` dataclass
- `lib/fusion.py` → `weighted_rrf()`
- `lib/normalize.py` → Per-source normalization
- `lib/signals.py` → `annotate_stream()`, `prune_low_relevance()`
- `lib/dedupe.py` → Cross-source deduplication
- `lib/relevance.py` → `PreparedQuery` for snippet extraction

**Files:**
```
tradingagents/agents/analysts/sentiment_analyst.py   # REDESIGN
tradingagents/dataflows/social_fusion.py             # NEW (RRF + ranking)
tradingagents/dataflows/social_schema.py             # NEW (SourceItem)
```

---

### Strategy C: "Topics 2.0" — Social-Aware Topic Extraction
**Effort:** Medium | **Impact:** Medium-High

**What:** The current Topics pipeline (`api/topics_extract.py`) uses Tavily web articles + LLM extraction. Enhance with last30days-style social research before LLM extraction.

**Current flow:**
```
Topic query → Tavily search → LLM extract tickers
```

**Enhanced flow:**
```
Topic query → Parallel social search (Reddit, HN, X if configured)
            → RRF fusion + clustering
            → Tavily web search (optional supplement)
            → LLM extract tickers (with social evidence in context)
```

**Why this helps:**
- Tavily misses community discussions that surface tickers organically
- "Best AI infrastructure plays" on Reddit will name $CRDO, $VST, etc.
- Polymarket markets directly map topics to tickers ("Will Trump Media stock hit $50?")

**Files:**
```
api/topics_extract.py           # ENHANCE
api/topics_social_research.py   # NEW (last30days-style fetcher)
```

---

### Strategy D: "Social Research Analyst" — New Analyst Type
**Effort:** Medium | **Impact:** High

**What:** Add a brand-new analyst (`social_research_analyst`) that runs a mini last30days pipeline for the ticker. This analyst produces a "Community Intelligence Report" separate from the existing Sentiment Analyst.

**Outputs:**
1. **Narrative synthesis** — What communities are saying (like last30days' "What I learned:")
2. **Key patterns** — Recurring themes with engagement scores
3. **Cross-source divergence** — Where Reddit and StockTwits disagree
4. **Prediction market signals** — Polymarket odds if available
5. **Catalyst timeline** — Upcoming events surfaced from community discussion

**This is the cleanest integration** because:
- It doesn't break existing analysts
- It leverages the full last30days architecture
- It feeds the Research Manager with richer social context

**Files:**
```
tradingagents/agents/analysts/social_research_analyst.py   # NEW
tradingagents/agents/skills/social_research_analyst/SKILL.md # NEW
tradingagents/dataflows/social_research/                   # NEW dir
    ├── __init__.py
    ├── pipeline.py        # Mini last30days orchestrator
    ├── schema.py          # SourceItem, Cluster, etc.
    ├── fusion.py          # RRF
    ├── sources/           # Per-source fetchers
    │   ├── reddit_enhanced.py
    │   ├── hackernews.py
    │   ├── polymarket.py
    │   ├── stocktwits.py
    │   └── youtube.py
```

---

### Strategy E: Full Pipeline Architecture Port
**Effort:** High | **Impact:** Very High

**What:** Port the entire last30days planner → retrieve → fuse → rerank → cluster → synthesize architecture into TradingAgents as a reusable research layer.

**Use cases:**
- **Pre-analyst research:** Run a last30days-style query for the ticker, feed results into ALL analysts as shared context
- **Topics engine:** Power the Topics feature with full social research
- **Monitor module:** The existing `monitor_enabled` feature could use last30days polling for breaking social signals
- **API endpoint:** `/social-research/{ticker}` on-demand endpoint

**Architecture:**
```
tradingagents/research_engine/          # NEW package (last30days port)
    ├── __init__.py
    ├── planner.py          # LLM query planner
    ├── pipeline.py         # Orchestration
    ├── schema.py           # Data models
    ├── fusion.py           # RRF
    ├── rerank.py           # LLM reranking
    ├── cluster.py          # Entity clustering
    ├── sources/            # Source adapters
    │   ├── reddit.py
    │   ├── hackernews.py
    │   ├── polymarket.py
    │   ├── youtube.py
    │   ├── github.py
    │   └── web.py
    └── render.py           # Markdown synthesis
```

---

## 5. Specific Data Sources to Prioritize

### 5.1 Polymarket (Highest Priority — Financial Signal)

**API:** `https://gamma-api.polymarket.com/markets?active=true&closed=false&limit=100`
**Auth:** None
**Rate limits:** Generous (Cloudflare fronted)

**Relevant market types for tickers:**
- Earnings beats / misses
- Stock price targets
- M&A completion
- Product launch success
- Regulatory approval

**last30days implementation:** `lib/polymarket.py` (303 lines)
- Searches by keyword
- Filters by `active=true`
- Extracts: question, description, outcomes, prices (odds), volume, liquidity, end date
- Topic disambiguation via `--polymarket-keywords`

### 5.2 Hacker News (High Priority — Tech Signal)

**API:** `https://hn.algolia.com/api/v1/search?query={q}&tags=story&numericFilters=created_at_i>{ts}`
**Auth:** None
**Rate limits:** Generous

**last30days implementation:** `lib/hackernews.py` (116 lines)
- Searches by keyword
- Returns: title, url, points, num_comments, author, created_at
- Parses and normalizes to `SourceItem`

### 5.3 YouTube (Medium Priority — Deep Content)

**Access:** yt-dlp (must be installed)
**Auth:** None for search; transcript extraction is local
**Cost:** Free

**last30days implementation:** `lib/youtube_yt.py`
- Search via yt-dlp
- Extract transcripts
- Return transcript highlights + snippet
- Fallback to ScrapeCreators if yt-dlp fails

### 5.4 Enhanced Reddit (Medium Priority — Better Comments)

**Current TradingAgents:** Searches posts only, no comments.

**last30days enhancement:** `lib/reddit_public.py` + `lib/reddit_enrich.py`
- Uses `shreddit` (public JSON) to fetch top comments with upvote counts
- Returns comment insights + excerpts
- Much richer signal than post titles alone

---

## 6. Quick Win: Polymarket + HN Prototype

A minimal viable integration could be built in ~200 lines:

```python
# tradingagents/dataflows/polymarket.py
"""Polymarket prediction market fetcher for ticker-related markets.

Free Gamma API, no authentication required. Real-money odds are a
harder-to-manipulate sentiment signal than social media alone.
"""

import json
import urllib.request
from datetime import datetime, timezone
from typing import Any

_GAMMA_API = "https://gamma-api.polymarket.com/markets"
_UA = "TradingAgents/0.2"


def fetch_polymarket_markets(keywords: list[str], limit: int = 20) -> list[dict]:
    """Fetch active Polymarket markets matching any keyword."""
    markets = []
    for kw in keywords:
        url = f"{_GAMMA_API}?active=true&closed=false&limit={limit}&archived=false"
        req = urllib.request.Request(url, headers={"User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        for m in data.get("markets", data if isinstance(data, list) else []):
            title = (m.get("question") or m.get("title") or "").lower()
            desc = (m.get("description") or "").lower()
            if kw.lower() in title or kw.lower() in desc:
                markets.append(_normalize_market(m))
    return markets


def _normalize_market(m: dict) -> dict:
    outcomes = m.get("outcomes") or []
    prices = m.get("outcomePrices") or []
    return {
        "question": m.get("question") or m.get("title"),
        "description": m.get("description", ""),
        "volume": m.get("volume") or m.get("volumeNum") or 0,
        "liquidity": m.get("liquidity") or m.get("liquidityNum") or 0,
        "end_date": m.get("endDate"),
        "outcomes": [
            {"name": o, "probability": float(p) if isinstance(p, (int, float, str)) else None}
            for o, p in zip(outcomes, prices)
        ],
        "url": f"https://polymarket.com/event/{m.get('slug', '')}",
    }
```

And in the Sentiment Analyst, add a new data block:
```python
polymarket_block = fetch_polymarket_markets([ticker, company_name])
# In prompt: "Prediction market odds: {polymarket_block}"
```

---

## 7. Risk & Considerations

| Risk | Mitigation |
|------|-----------|
| **API rate limits** (Reddit public JSON ~10 req/min) | Add caching; use ScrapeCreators fallback |
| **Non-US ticker coverage** (StockTwits, Reddit) | Graceful degradation; HK-specific subreddits |
| **Data freshness** (social moves fast) | Shorter lookback (7 days default); timestamp weighting |
| **LLM token bloat** (more sources = longer prompts) | RRF fusion + top-K filtering before prompt injection |
| **ScrapeCreators dependency** | All social sources work without it; SC unlocks TikTok/IG/Threads |
| **yt-dlp dependency** | Optional; YouTube only works if installed |
| **Polymarket coverage gaps** | Not all tickers have markets; return empty gracefully |
| **Maintenance burden** | Port last30days modules as-is; they have 1,000+ tests |

---

## 8. Recommended Roadmap

| Phase | Work | ETA |
|-------|------|-----|
| **1** | Add Polymarket + HN dataflow modules; integrate into Sentiment Analyst | 1-2 days |
| **2** | Enhance Reddit with comment fetching (port `reddit_public.py` + `reddit_enrich.py`) | 1-2 days |
| **3** | Build `social_research_analyst` as new analyst type (full last30days mini-pipeline) | 1 week |
| **4** | Add Topics social-research layer (`api/topics_social_research.py`) | 2-3 days |
| **5** | Port full `research_engine/` package for reusable social research across all analysts | 2 weeks |
| **6** | Add YouTube, Bluesky, X (if keys configured) to Social Research Analyst | 1 week |

---

## 9. Files to Study from last30days (Prioritized)

1. `scripts/lib/pipeline.py` — Orchestration pattern
2. `scripts/lib/schema.py` — Data models
3. `scripts/lib/fusion.py` — RRF implementation
4. `scripts/lib/signals.py` — Signal annotation
5. `scripts/lib/polymarket.py` — Financial data source
6. `scripts/lib/hackernews.py` — Free tech sentiment source
7. `scripts/lib/reddit_public.py` + `reddit_enrich.py` — Enhanced Reddit
8. `scripts/lib/cluster.py` — Cross-source merging
9. `scripts/lib/rerank.py` — LLM reranking pattern
10. `scripts/lib/planner.py` — LLM query planning
