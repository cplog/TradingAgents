# Product Specification: TradingAgents

> **Version**: 2.0-pivot (brand surface)
> **Last Updated**: 2026-06-05
> **Scope**: Brand-led consumer-facing surface wrapping the multi-agent research interface
> **Design System**: see [DESIGN.md](./DESIGN.md) — die-cut paper, visible grain, Mailchimp × Revolut help-center lane

---

## 1. Product Overview

### 1.1 Elevator Pitch
TradingAgents is a financial research interface wrapped in a handcrafted brand surface. The wrapper carries personality: die-cut paper, visible grain, witty-but-precise voice, the **Mailchimp-meets-Revolut-help-center** lane. Inside, a 7-analyst + Kronos pipeline turns a ticker into a structured decision package — rating, evidence chain, forecast chart, risk assessment — in under 4 minutes. The product isn't just the analysis; it's the relationship between the brand surface and the analysis. Visible craft on the outside, serious work on the inside.

### 1.2 Product Purpose
Turn a complex research pipeline into an experience people want to open: **arrive curious → see the craft → run an analysis → trust the result**. Success means a user lands on the brand surface, feels the handmade quality, runs a real analysis inside the embedded interface, and leaves with a decision they understand and remember.

### 1.3 Brand Personality
**Handmade, witty, sharp.**

Voice and tone are crafted the way good stationery is: warm, considered, never sloppy. The interface earns trust through visible craft (die-cut paper edges, visible grain, hand-cut imperfection) and earns respect through sharp typographic detail, accurate financial copy, and surfaces that respect the user's intelligence. The Mailchimp lane: warm but never cute. The Revolut help-center lane: warm but never dumbed down. Personality means we make the craft visible AND we say precise things about it.

Three-word test: anything that reads as *cold, severe, generic, corporate, sterile* fails.

### 1.4 Anti-References (What We Reject)
- ❌ **The previous retro-dark mission-control aesthetic.** Phosphor green, monospace readouts, scanlines, terminal vibes. Explicitly retired.
- ❌ **Generic SaaS cream-and-pastel.** Gradient hero cards, hero-metric templates, identical feature grids, glassmorphism defaults, the "AI workflow tool" look.
- ❌ **Aggressive trading-app urgency.** Red/green tickers, dense Bloomberg-aesthetic data, "ACT NOW" framing, gamified confetti.
- ❌ **Sterile enterprise backoffice.** Jargon-heavy labels, overloaded controls, dense tables, configuration-on-configuration.
- ❌ **Decorative paper collage without system discipline.** Ad-hoc cutouts, illustrations that don't share a grammar, paper grain as decoration rather than as a coherent material language. The reference lane is Mailchimp's illustration *system*, not a one-off cutout.

### 1.5 The Brand Surface

The product is presented inside a brand surface that carries the personality. Functional specs (the research interface) live inside it. The brand surface itself has its own information architecture:

**Brand surface sections (top-down):**
1. **Hero.** One handmade headline, one demonstration artifact (a screenshot of an analysis or a small data piece rendered as paper), one CTA — "Run a sample analysis" or "See the craft." No second column, no metric bar.
2. **Story.** A short narrative about the multi-agent approach, written in the witty voice. No bullet lists, no feature walls. The story earns trust by being honest about the workflow.
3. **How it works.** A 3-step paper-collage explainer — *Configure → Run → Decide* — each step illustrated with a die-cut paper diagram that reuses motifs from the embedded interface.
4. **Live demo.** The research interface itself, embedded. The user runs a real analysis on a sample ticker (000001, 00700, SOFI, NVDA). The demo IS the product.
5. **Principles.** 3-4 cards explaining design principles ("Show the craft, then ship the work"). Each card is itself a small paper-collage composition, not a checkbox list.
6. **Sample decisions.** A scrollable strip of past analysis results, each presented as a paper artifact with a torn edge and hand-cut label.
7. **CTA + footer.** Run it, learn more, see the open-source repo. Footer uses a quiet paper-tape strip, not a corporate link wall.

**Rules:**
- The brand surface uses the full pastel paper-collage system freely: layered depth, hand-cut edges, visible grain, watercolor accents, sharp witty copy.
- The embedded research interface inherits the warm personality but is calmer and more legible. Less decorative motion, more typographic precision, denser information.
- The transition from brand surface to research interface is a single deliberate visual move (a fold, a paper-tape strip, a torn edge across the viewport), not a generic route change.
- The brand surface and the research interface share a paper grammar: same palette, same cutout shapes, same grain. A illustration on the hero should share a hand with an empty-state card inside the analysis page.

### 1.6 Data Sources & Awesome-finance-skills Modules

Upstream **[Awesome-finance-skills](https://github.com/RKiding/Awesome-finance-skills)** ships plug-in agent skills; this product integrates them as the **canonical research-data and artifact layer** alongside TradingAgents LangGraph nodes.

| Skill ID | Capability | Primary data / outputs |
|----------|------------|-------------------------|
| **alphaear-news** | Real-time financial news & trends | 10+ aggregated sources (e.g., 财联社 Cailian, WSJ-style feeds, 微博 Weibo, **Polymarket**); hot-topic clustering |
| **alphaear-stock** | A-share, HK & US market data | Ticker search/resolution, OHLCV, fundamentals |
| **alphaear-sentiment** | Sentiment scoring | FinBERT and/or LLM; scores roughly **-1.0 … +1.0** |
| **alphaear-predictor** | Time-series forecasting | **Kronos** with news-aware adjustments |
| **alphaear-signal-tracker** | Signal evolution | **Strengthen / Weaken / Falsify** over time |
| **alphaear-logic-visualizer** | Transmission / evidence chains | **Draw.io XML** + narrative logic chain |
| **alphaear-reporter** | Professional reports | Plan → Write → Edit → Chart |
| **alphaear-search** | Web search & local RAG | **Jina**, **DuckDuckGo**, **Baidu** (configurable) |

**Implementation note**: TradingAgents may route equity tools through existing vendors (`a_stock`, `yfinance`, `alpha_vantage`, etc.) while **news aggregation, logic diagrams, reporter workflow, and search/RAG** follow the contracts implied by the skill pack above. Optional gateways (e.g., NewsNow) remain operator-configurable where they unify fetch + rate limiting.

---

## 2. Users

### 2.1 Primary Users: Retail Traders & Independent Researchers
- **Profile**: Run single-ticker and batch analyses to understand a stock before acting.
- **Pain Points**: 
  - Information scattered across EastMoney, Xueqiu, Weibo, multi-headline aggregators (财联社, WSJ-class feeds, Polymarket), news apps, and broker terminals.
  - No structured way to weigh technicals, fundamentals, sentiment, and hot money signals together.
  - Can't track why a previous recommendation was wrong or right.
- **Workflow**: Short decision windows needing clear run status, fast evidence access, and enough control to adjust configuration without leaving the workflow.
- **Frequency**: 2-5 analyses per week, often before market open or during lunch break.

### 2.2 Secondary Users: Technical Operators
- **Profile**: Tune LLM providers, model choices (FinBERT, Kronos), per-category data vendors (`core_stock_apis`, `news_data`, etc.), **Awesome-finance-skills** backends (search provider, news aggregation caps), and runtime settings.
- **Pain Points**:
  - Kronos model fails to load on CPU-only machines.
  - Multi-source news aggregation or optional NewsNow gateway hits rate limits during batch runs (10+ sources × concurrency).
  - Need to switch between `a_stock`, `yfinance`, and `alpha_vantage` without code changes; HK/US tickers must resolve cleanly via **alphaear-stock**-aligned search/OHLCV paths.
- **Workflow**: Configuration tuning, batch job monitoring, failure debugging, and performance benchmarking.
- **Frequency**: Weekly maintenance + ad-hoc when pipeline breaks.

### 2.3 User Needs Matrix

| Need | Primary | Secondary | Priority |
|------|---------|-----------|----------|
| Single-ticker analysis in < 4 min | ✅ | ❌ | P0 |
| Batch screener (10-50 tickers) | ✅ | ✅ | P1 |
| Real-time run status & progress | ✅ | ✅ | P0 |
| Evidence inspection (news, charts, fundamentals) | ✅ | ❌ | P0 |
| Historical decision review & reflection | ✅ | ✅ | P1 |
| Vendor / model / LLM configuration | ❌ | ✅ | P0 |
| Signal evolution tracking (Strengthen/Weaken/Falsify) | ✅ | ✅ | P1 |
| Multi-source news + optional prediction-market context | ✅ | ✅ | P0 |
| Web search & local RAG (cited snippets in evidence) | ✅ | ✅ | P1 |
| Export reports (PDF, Draw.io XML) | ✅ | ❌ | P2 |

---

## 3. Design Principles

1. **Show the craft, then ship the work.** Visible handcraft is the brand's first promise; serious analysis is the second. Both must be present on every surface.
2. **Paper as material, not decoration.** A fixed paper grammar (3-4 weights, 1-2 cutout shapes, a committed pastel palette, visible grain) makes the 30th illustration feel related to the 1st.
3. **Wit is precision, not noise.** Sharp copy and sharp typography carry the personality. Decoration that doesn't earn its place gets cut.
4. **Calm under uncertainty, even when the surface is warm.** A BUY/SELL decision in a paper-collage interface still has to be legible at a glance. Warmth never overrides clarity.
5. **The brand wrapper and the research interface share a grammar.** The hero, the story, and the analysis run page should feel like the same hands made them.

---

## 4. Core Features

### 4.1 Dashboard (Home)

**Purpose**: Orient the user immediately. Show what's active, what's recent, and what's next.

**Layout**:
```
┌─────────────────────────────────────────────────────────────┐
│  [Logo]  TradingAgents          [Search] [Settings] [User] │
├────────┬──────────────────────────────────────────────────┤
│        │  ┌──────────────────────────────────────────────┐  │
│  NAV   │  │  Quick Run Card                              │  │
│        │  │  Ticker: [________]  [Run Analysis ▶]        │  │
│  ────  │  │  Recent: 000001  000002  SOFI               │  │
│  Dash  │  └──────────────────────────────────────────────┘  │
│  Hist  │                                                  │
│  Screener│  ┌──────────────────┐  ┌──────────────────────┐  │
│  System│  │  Active Runs       │  │  Recent Decisions    │  │
│        │  │  ─────────────     │  │  ─────────────────   │  │
│        │  │  000001  ████░░    │  │  000001  BUY  +5.2%  │  │
│        │  │  SOFI    ████████  │  │  000002  HOLD -1.1%  │  │
│        │  │  000858  ░░░░░░    │  │  000858  SELL +2.8%  │  │
│        │  └──────────────────┘  └──────────────────────┘  │
│        │                                                  │
│        │  ┌──────────────────────────────────────────────┐  │
│        │  │  Signal Tracker (30-day overview)            │  │
│        │  │  Strengthen: 3  |  Weaken: 2  |  Falsify: 1  │  │
│        │  └──────────────────────────────────────────────┘  │
└────────┴──────────────────────────────────────────────────┘
```

**Components**:
- **Quick Run Card**: Primary CTA. Ticker input + Run button. Signal Blue (`#3ba6f1`) pill button. Recent tickers as ghost chips below.
- **Active Runs Panel**: Progress bars with analyst names (Market, News, Sentiment, Fundamentals, Hot Money, Policy, Lockup, Kronos). Real-time status.
- **Recent Decisions Panel**: Last 5 decisions with ticker, action (BUY/HOLD/SELL), and realized return (if available). Color-coded: green for positive, red for negative, gray for pending.
- **Signal Tracker Mini**: 30-day signal evolution summary. Click to expand.

**States**:
- **Empty**: Show onboarding hint + sample tickers (000001, 00700, SOFI).
- **Loading**: Skeleton cards with pulsing placeholders.
- **Error**: Inline error card with retry action and log link.

---

### 4.2 Analysis Run Page

**Purpose**: The core workflow. Configure → Run → Monitor → Review.

**Flow States**:

#### State A: Configuration (Pre-run)
```
┌─────────────────────────────────────────────────────────────┐
│  Configure Analysis                                          │
├─────────────────────────────────────────────────────────────┤
│  Ticker: [000001          ]                                  │
│  Trade Date: [2026-05-17 ▼]  (default: today)               │
│                                                              │
│  ▼ Analyst Selection (default: all)                        │
│  [✓] Market Analyst    [✓] News Analyst                   │
│  [✓] Sentiment Analyst [✓] Fundamentals Analyst           │
│  [✓] Hot Money Tracker [✓] Policy Analyst                 │
│  [✓] Lockup Watcher    [✓] Social Analyst                 │
│  [✓] Kronos Predictor                                     │
│                                                              │
│  ▼ Advanced Options                                         │
│  Stock Vendor: [a_stock ▼] (a_stock | yfinance | alpha_vantage)
│  News Mode: [aggregated ▼] (aggregated | gateway | minimal)
│  Search Backend: [ddg ▼]   (jina | ddg | baidu | off)      │
│  LLM Provider: [openai ▼]    (openai | anthropic | local)   │
│  Deep Think Model: [gpt-5.4 ▼]                              │
│  Quick Think Model: [gpt-5.4-mini ▼]                        │
│  Sentiment Mode: [auto ▼]    (auto | bert | llm | off)     │
│  Kronos: [enabled ▼]         (enabled | cpu_fallback | off) │
│  Max Debate Rounds: [1 ▼]    (1 | 2 | 3)                  │
│  Checkpoint: [✓] Resume on failure                         │
│                                                              │
│  [Run Analysis ▶]  [Save as Preset]                       │
└─────────────────────────────────────────────────────────────┘
```

**Rules**:
- Advanced Options collapsed by default. Chevron toggle.
- **Stock Vendor** maps to TradingAgents `dataflows` routing (`a_stock`, `yfinance`, `alpha_vantage`) while respecting **alphaear-stock** coverage expectations for OHLCV and fundamentals.
- **News Mode**: `aggregated` uses multi-source ingestion aligned with **alphaear-news**; `gateway` uses an optional HTTP facade (e.g., NewsNow); `minimal` reduces sources for low-quota or degraded runs.
- **Search Backend**: selects **alphaear-search** provider (`jina | ddg | baidu`); `off` disables network search (local RAG path remains under System Settings).
- Ticker validation: 6-digit numeric (A-share), 5-digit (HK), or alphabetic (US). Auto-strip SH/SZ/BJ prefix.
- Trade Date default = today. Weekend/holiday warning if selected.
- Analyst checkboxes: unchecking an analyst removes it from the pipeline. Minimum 2 required.
- Kronos "cpu_fallback" option shown only if GPU unavailable (detected at runtime).

#### State B: Running (In-progress)
```
┌─────────────────────────────────────────────────────────────┐
│  Analysis Running: 000001  |  2:14 elapsed                  │
├─────────────────────────────────────────────────────────────┤
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Pipeline Progress                                    │  │
│  │  ─────────────────                                    │  │
│  │  [✓] Market Analyst        (0:32)  12 tool calls    │  │
│  │  [✓] News Analyst          (0:45)  8 tool calls     │  │
│  │  [✓] Sentiment Analyst     (0:58)  156 news scored  │  │
│  │  [→] Fundamentals Analyst  (1:12)  3-source cascade │  │
│  │  [○] Hot Money Tracker     pending                 │  │
│  │  [○] Policy Analyst        pending                 │  │
│  │  [○] Lockup Watcher        pending                 │  │
│  │  [○] Kronos Predictor      pending                 │  │
│  │  [○] Quality Gate          pending                 │  │
│  │  [○] Bull/Bear Debate      pending                 │  │
│  │  [○] Research Manager      pending                 │  │
│  │  [○] Trader                pending                 │  │
│  │  [○] Risk Debate           pending                 │  │
│  │  [○] Portfolio Manager     pending                 │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                              │
│  [Cancel]  [View Live Log]                                 │
└─────────────────────────────────────────────────────────────┘
```

**Rules**:
- Progress list shows all 15 nodes. Completed = checkmark + elapsed time. Active = spinner + live status. Pending = circle.
- Click any completed node to preview its report snippet in a side drawer.
- "View Live Log" opens a terminal-style panel streaming LLM calls, tool responses, and errors.
- Cancel stops the pipeline gracefully, saving checkpoint for resume.

#### State C: Complete (Results)
```
┌─────────────────────────────────────────────────────────────┐
│  Analysis Complete: 000001  |  3:42 total                   │
├─────────────────────────────────────────────────────────────┤
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Final Decision                                        │  │
│  │  ─────────────                                         │  │
│  │  RATING: [BUY]  Confidence: 72%                       │  │
│  │  Position: 15% portfolio allocation                   │  │
│  │  Rationale: Technical breakout + sentiment rebound    │  │
│  │  Risk: T+1 lock, 涨跌停 ±10%, lockup expiry in 14d   │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐        │
│  │ Price Chart  │ │ Sentiment    │ │ Kronos       │        │
│  │ (30d OHLCV)  │ │ (3d WMS)     │ │ (5d Forecast)│        │
│  │              │ │              │ │              │        │
│  └──────────────┘ └──────────────┘ └──────────────┘        │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Evidence Chain (Logic Visualizer)                   │  │
│  │  [View as Draw.io XML] [View as Text]               │  │
│  │                                                      │  │
│  │  Macro → Direct → Transmission → Individual       │  │
│  │  ↓         ↓           ↓              ↓              │  │
│  │  Policy   Market    Hot Money      Fundamentals      │  │
│  │  (bullish) (breakout) (net inflow) (EPS beat)      │  │
│  │  ↓         ↓           ↓              ↓              │  │
│  │  ───────→ Sentiment (WMS: +0.42) ←────────────    │  │
│  │              ↓                                       │  │
│  │         Kronos Forecast (↑↑↑ confidence 0.78)       │  │
│  │              ↓                                       │  │
│  │         Quality Gate (PASS)                         │  │
│  │              ↓                                       │  │
│  │         Bull/Bear Debate (2 rounds)                 │  │
│  │              ↓                                       │  │
│  │         Final: BUY 72%                              │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Analyst Reports (Accordion)                         │  │
│  │  [Market] [News] [Sentiment] [Fundamentals] ...     │  │
│  │  Click to expand full text + tool call logs          │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                              │
│  [Export PDF] [Export Draw.io] [Re-run with Changes] [New Analysis]
└─────────────────────────────────────────────────────────────┘
```

**Rules**:
- Rating badge: BUY = Signal Blue fill, SELL = semantic red, HOLD = Ash Gray.
- Confidence shown as percentage with color gradient (low = gray, mid = blue, high = dark blue).
- Three charts side-by-side: Price (candlestick), Sentiment (WMS timeline), Kronos (forecast band with confidence interval).
- Collapsible **News digest** and **Search citations** panels surface **alphaear-news** / **alphaear-search** outputs without leaving the results page.
- Evidence Chain: Interactive tree. Click node → expand details + source report snippet.
- Analyst Reports: Accordion with full text. Technical operators can inspect raw LLM outputs and tool call logs.
- Export: PDF (structured report with charts), Draw.io XML (logic diagram), JSON (raw state).

---

### 4.3 History & Reflection

**Purpose**: Track past decisions, review outcomes, and learn from falsified signals.

**Layout**:
```
┌─────────────────────────────────────────────────────────────┐
│  Decision History                                            │
├─────────────────────────────────────────────────────────────┤
│  Filter: [All ▼] [Date Range] [Ticker Search] [Rating ▼]   │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  2026-05-10  000001  BUY  Confidence: 68%            │  │
│  │  Actual Return (5d): +3.2%  |  Alpha vs CSI300: +1.1%│  │
│  │  Signal Status: [Strengthen → Falsify → Strengthen] │  │
│  │  [View Report] [View Reflection] [Re-run]           │  │
│  ├──────────────────────────────────────────────────────┤  │
│  │  2026-05-05  SOFI    HOLD Confidence: 55%           │  │
│  │  Actual Return (5d): -2.1%  |  Alpha: -0.8%        │  │
│  │  Signal Status: [Weaken → Falsify]                  │  │
│  │  Reflection: "Premature bullishness on SOFI earnings│  │
│  │  ignored lockup expiry risk. Next time: check       │  │
│  │  lockup calendar before earnings plays."            │  │
│  │  [View Report] [View Reflection] [Re-run]             │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

**Rules**:
- Each card shows: date, ticker, decision, confidence, realized return, alpha, signal evolution timeline.
- Signal Status: Mini timeline with color-coded dots (green = Strengthen, yellow = Weaken, red = Falsify, blue = New).
- Reflection: Auto-generated by Reflector agent after 5-day holding period. Editable by user.
- Re-run: Pre-fills configuration with historical settings, allows modification.

---

### 4.4 Screener (Batch Analysis)

**Purpose**: Run analysis on multiple tickers simultaneously. For primary users building watchlists; for secondary users stress-testing configurations.

**Layout**:
```
┌─────────────────────────────────────────────────────────────┐
│  Batch Screener                                              │
├─────────────────────────────────────────────────────────────┤
│  Tickers: [000001,000002,000858,SOFI          ]            │
│  [Upload CSV]  [Load Watchlist]                            │
│                                                              │
│  Preset: [Default ▼]  [Edit Preset]                        │
│                                                              │
│  [Run Batch ▶]  Max 20 tickers per batch                   │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Batch Progress  3/20  ████████░░░░░░░░░░░░░░░░░░    │  │
│  │  000001  [✓] BUY 72%   000002  [✓] HOLD 51%        │  │
│  │  000858  [→] Running... SOFI    [○] Pending         │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                              │
│  Results Table (sortable):                                   │
│  Ticker | Rating | Confidence | Kronos | Sentiment | Return │
│  ─────────────────────────────────────────────────────────  │
│  000001 | BUY    | 72%        | ↑↑↑    | +0.42     | +3.2% │
│  000002 | HOLD   | 51%        | →      | -0.11     | -1.1% │
│  ...                                                        │
└─────────────────────────────────────────────────────────────┘
```

**Rules**:
- Max 20 tickers per batch (rate limit + compute constraint).
- Results table sortable by any column.
- Click row → drill into full single-ticker report.
- Export: CSV summary + ZIP of individual PDF reports.

---

### 4.5 System Settings

**Purpose**: Technical operators tune the pipeline.

**Sections**:
1. **LLM Configuration**: Provider, API key, deep/quick model selection, temperature, max tokens.
2. **Data Vendors**: Per-category routing (`core_stock_apis`, `fundamental_data`, `news_data`, `technical_indicators`). Stock paths align with **alphaear-stock** (A-share / HK / US); priority & fallback order match TradingAgents `dataflows` conventions.
3. **Awesome-finance-skills**: Enable/disable skill bundles; paths or endpoints if skills run out-of-process; version pin for reproducibility.
4. **Models**: FinBERT model path, Kronos model path, embedding model for **alphaear-search** local RAG, device (auto / cuda / cpu / mps).
5. **News Aggregation**: Max sources per run (default aligned with 10+ source headlines), cache TTL, optional Polymarket inclusion, optional **NewsNow** (or equivalent) gateway URL + rate limit override when used as a single fetch facade.
6. **Search & RAG**: Default backend (**Jina** / **DuckDuckGo** / **Baidu**), API keys if required, query budget per run, local corpus paths for RAG.
7. **Cache & Storage**: SQLite path, CSV cache path, checkpoint enabled/disabled, retention days.
8. **Advanced**: Max debate rounds, max risk discuss rounds, output language, debug mode.

**Rules**:
- Changes require "Apply & Restart Pipeline" confirmation.
- Invalid configurations (e.g., Kronos path doesn't exist) show inline validation errors.
- Export/Import full config as JSON for backup and sharing.

---

## 5. User Flows

### 5.1 Primary Flow: Single-Ticker Analysis

```
[Dashboard] → [Enter Ticker] → [Configure (optional)] → [Run] → [Monitor] → [Review Results] → [Export/Decide]
     ↑                                                                                              │
     └──────────────────────────────────── [History] ← [Reflection after 5d] ← [Execute Trade] ←────┘
```

**Time Budget**:
- Configuration: < 30 seconds (defaults optimized for A-share).
- Run: 3-4 minutes (7 analysts + Kronos + debates; news aggregation and search steps contribute to wall clock).
- Review: 2-3 minutes (scan charts + read rationale + check evidence chain).
- Total: < 8 minutes from intent to decision.

### 5.2 Secondary Flow: Batch Screener

```
[Dashboard] → [Screener Tab] → [Enter Tickers / Upload CSV] → [Select Preset] → [Run Batch]
     → [Monitor Progress] → [Review Table] → [Drill into Individual] → [Export CSV/ZIP]
```

### 5.3 Technical Operator Flow: Debug & Tune

```
[System Settings] → [Adjust Vendor / Models / Finance Skills] → [Run Test Ticker] → [Inspect Live Log]
     → [Review Tool Call Traces] → [Adjust Retry/Timeout] → [Save Preset] → [Batch Validate]
```

### 5.4 Reflection Flow (Deferred)

```
[History] → [Select Past Decision] → [5d Holding Period Complete]
     → [Auto-trigger Reflector Agent] → [Generate Reflection]
     → [User Edits / Approves] → [Saved to Memory Log]
     → [Next Same-Ticker Run: Inject Past Context into Initial State]
```

---

## 6. Feature Specs

Specs below map to **[Awesome-finance-skills](https://github.com/RKiding/Awesome-finance-skills)** modules (`alphaear-*`) where noted; P0/P1/P2 reflect UX priority in Command Center, not upstream repo labels.

### 6.1 Quick Run Card (P0)
- **Input**: Ticker text field with autocomplete (from watchlist + history).
- **Action**: Signal Blue pill button "Run Analysis".
- **Output**: Redirect to Analysis Run Page (State B).
- **Edge Cases**: Invalid ticker → inline error with format hint. Duplicate running ticker → warn and offer "View Active Run".

### 6.2 Pipeline Progress Monitor (P0)
- **Real-time Updates**: WebSocket or SSE streaming node completion events.
- **Node States**: pending → active (spinner + live log snippet) → completed (checkmark + elapsed + tool call count) → failed (red X + error message + retry).
- **Interactivity**: Click completed node → side drawer with full report. Click active node → live log tail.
- **Cancellation**: Graceful stop, save checkpoint, allow resume.

### 6.3 Financial News Aggregation — **alphaear-news** (P0)
- **Input**: Ticker, trade date, locale, max headlines per source, optional theme keywords.
- **Output**: Unified headline feed with source attribution, timestamps, deduped clusters; optional **Polymarket**-linked context when enabled.
- **UX**: News Analyst drawer lists sources contributing to the run (10+ source families per upstream design).
- **Edge Cases**: Partial source outage → show per-source error chips + continue with available sources.

### 6.4 Stock & Fundamentals Data — **alphaear-stock** (P0)
- **Input**: Normalized symbol (A-share / HK / US per §4.2 rules).
- **Output**: Quote snapshot, OHLCV series, key fundamentals fields for analyst prompts and charts.
- **Integration**: Must coexist with TradingAgents `dataflows` vendor routing (`a_stock`, `yfinance`, `alpha_vantage`, …); **alphaear-stock** defines the cross-market contract (search + OHLCV + fundamentals) the UI and tools target.

### 6.5 Sentiment Dashboard — **alphaear-sentiment** (P1)
- **Input**: `sentiment_report` from Sentiment Analyst Node (FinBERT and/or LLM scoring **-1.0 … +1.0**).
- **Output**: 
  - WMS (Weighted Market Sentiment) timeline chart (3-day).
  - Source distribution pie chart aligned with **alphaear-news** (财联社, 华尔街见闻-class, 微博, 雪球, Polymarket slice when on, etc.).
  - Extreme events list (|score| > 0.8) with full text preview.
  - Sentiment-price divergence alert.

### 6.6 Kronos Forecast Chart — **alphaear-predictor** (P1)
- **Input**: `kronos_forecast` from Kronos Predictor Node.
- **Output**: 
  - Candlestick chart with 20-day historical + 5-day forecast band.
  - Forecast confidence interval (shaded area).
  - News-aware adjustment indicator ("Adjusted by N news events") tying back to **alphaear-news**.
  - Model version and run timestamp.

### 6.7 Evidence Chain Visualizer — **alphaear-logic-visualizer** (P1)
- **Input**: Full pipeline state after Portfolio Manager (and intermediate analyst outputs).
- **Output**: Interactive transmission-chain tree (SVG/Canvas) + **Draw.io XML** export for diagrams.net.
- **Nodes**: Seven thematic analysts + sentiment + Kronos + quality gate + debate + trader + risk + PM (same conceptual graph as §4.2 State C).
- **Edges**: Labeled with signal direction (bullish/bearish/neutral) and confidence.
- **Interactivity**: Hover → tooltip with summary. Click → expand details panel with source snippet citations.

### 6.8 Signal Tracker — **alphaear-signal-tracker** (P1)
- **Input**: `signal_evolution` persistence (SQLite or equivalent).
- **Output**: 
  - Timeline: **Strengthen / Weaken / Falsify** with color-coded transitions.
  - Filter by ticker, date range, signal type.
  - Statistics: Strengthen rate, Falsify rate, average holding period.

### 6.9 Professional Report Pipeline — **alphaear-reporter** (P2)
- **Input**: Frozen run results (decision, analyst markdown, charts refs, logic XML).
- **Output**: Structured research brief following **Plan → Write → Edit → Chart** (outline visible in UI before PDF/HTML export).
- **UX**: Optional side-by-side diff between draft and edited version for operator QA.

### 6.10 Search & Local RAG — **alphaear-search** (P1)
- **Input**: Curated queries derived from ticker + themes; optional embedding over local corpus path from config.
- **Output**: Ranked snippets with URLs or doc IDs; citations surfaced in News/Social drawers and evidence nodes.
- **Backends**: **Jina**, **DuckDuckGo**, **Baidu** — selectable per environment; `off` disables network search for air-gapped runs.

### 6.11 Export & Batch Artifacts (P2)
- **PDF**: Structured report with charts, analyst summaries, and final decision. Generated server-side (Playwright + HTML template).
- **Draw.io XML**: Logic diagram from **alphaear-logic-visualizer** for manual editing.
- **JSON**: Full state dump for programmatic consumption.
- **CSV / ZIP**: Screener batch summary + optional bundle of per-ticker PDFs.

---

## 7. Data Model (UI Layer)

### 7.1 Analysis Run
```typescript
interface AnalysisRun {
  id: string;                    // UUID
  ticker: string;                // normalized (6-digit A-share, etc.)
  tradeDate: string;             // ISO date
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';
  config: RunConfig;
  progress: PipelineProgress;
  results: RunResults | null;
  createdAt: string;
  completedAt: string | null;
  error: string | null;
}

interface PipelineProgress {
  currentNode: string;
  completedNodes: string[];
  failedNodes: string[];
  elapsedSeconds: number;
  estimatedRemainingSeconds: number;
}

interface RunResults {
  finalDecision: 'BUY' | 'HOLD' | 'SELL';
  confidence: number;            // 0.0 - 1.0
  allocationPercent: number;    // 0 - 100
  rationale: string;
  analystReports: Record<string, string>;  // key = analyst type
  /** alphaear-news-shaped digest for UI (sources + headlines + optional Polymarket refs) */
  newsDigest: {
    sources: string[];
    items: Array<{ source: string; title: string; url?: string; publishedAt?: string }>;
  } | null;
  /** alphaear-search citations */
  searchCitations: Array<{ title: string; url: string; snippet: string }> | null;
  /** alphaear-reporter staged output */
  reporterStages: { plan: string; draft: string; edited: string } | null;
  kronosForecast: KronosForecast | null;
  sentimentReport: SentimentReport | null;
  evidenceChain: EvidenceChain;
  logicDiagramXml: string;
}
```

### 7.2 Signal Evolution
```typescript
interface SignalEntry {
  id: number;
  ticker: string;
  tradeDate: string;
  signalType: 'BUY' | 'HOLD' | 'SELL';
  strength: number;              // 0.0 - 1.0
  status: 'New' | 'Strengthen' | 'Weaken' | 'Falsify';
  triggerSource: string;         // 'market' | 'sentiment' | 'kronos' | 'news' | 'search' | ...
  previousSignal: string | null;
  notes: string;
  createdAt: string;
}
```

### 7.3 User Configuration
```typescript
interface UserConfig {
  llm: {
    provider: 'openai' | 'anthropic' | 'local';
    apiKey: string;              // encrypted at rest
    deepThinkModel: string;
    quickThinkModel: string;
    temperature: number;
    maxTokens: number;
  };
  dataVendors: Record<string, string>;  // method -> vendor
  models: {
    finbertPath: string;
    kronosPath: string;
    embeddingModel: string;
    device: 'auto' | 'cuda' | 'cpu' | 'mps';
  };
  newsAggregation: {
    mode: 'aggregated' | 'gateway' | 'minimal';
    gatewayBaseUrl: string | null;   // optional NewsNow-style facade
    cacheTtlSeconds: number;
    maxSourcesPerRun: number;
    includePolymarket: boolean;
  };
  search: {
    backend: 'jina' | 'ddg' | 'baidu' | 'off';
    maxQueriesPerRun: number;
    localRagIndexPath: string | null;
  };
  pipeline: {
    maxDebateRounds: number;
    maxRiskDiscussRounds: number;
    checkpointEnabled: boolean;
    outputLanguage: 'Chinese' | 'English';
  };
}
```

---

## 8. Integration Points

### 8.1 Backend API Contract

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/analyze` | POST | Start single-ticker analysis. Returns runId. |
| `/api/analyze/batch` | POST | Start batch analysis. Returns batchId. |
| `/api/runs/{runId}` | GET | Get run status, progress, and results. |
| `/api/runs/{runId}/stream` | SSE | Real-time progress updates. |
| `/api/runs/{runId}/cancel` | POST | Cancel running analysis. |
| `/api/runs/{runId}/report` | GET | Export report (PDF, XML, JSON). |
| `/api/history` | GET | List past decisions with filters. |
| `/api/history/{runId}/reflection` | GET/POST | Get or update reflection. |
| `/api/signals` | GET | Signal evolution timeline. |
| `/api/config` | GET/PUT | System configuration. |
| `/api/health` | GET | System health + model availability. |

### 8.2 WebSocket / SSE Events

```json
// Node Start
{"type": "node_start", "runId": "...", "node": "Market Analyst", "timestamp": "..."}

// Node Complete
{"type": "node_complete", "runId": "...", "node": "Market Analyst", 
 "elapsedSeconds": 32, "toolCalls": 12, "timestamp": "..."}

// Node Error
{"type": "node_error", "runId": "...", "node": "Kronos Predictor", 
 "error": "CUDA out of memory", "fallback": "cpu_fallback", "timestamp": "..."}

// Progress Update
{"type": "progress", "runId": "...", "completedNodes": 3, "totalNodes": 15, 
 "currentNode": "Fundamentals Analyst", "percent": 20}

// Final Decision
{"type": "complete", "runId": "...", "decision": "BUY", "confidence": 0.72, 
 "allocationPercent": 15, "timestamp": "..."}
```

### 8.3 Frontend → Backend Data Flow

```
Frontend (React)
  → REST API / SSE (FastAPI)
  → LangGraph Orchestrator (trading_graph.py)
  → Analyst Nodes (tools + LLM calls)
  → Awesome-finance-skills-aligned layer:
       • alphaear-news      → multi-source headlines + optional Polymarket context
       • alphaear-stock     → OHLCV + fundamentals (A-share / HK / US)
       • alphaear-search    → Jina / DDG / Baidu + optional local RAG
       • alphaear-sentiment → FinBERT / LLM scores (-1…+1)
       • alphaear-predictor → Kronos (news-adjusted)
       • alphaear-logic-visualizer / reporter / signal-tracker → artifacts + SQLite
  → TradingAgents dataflows fallbacks (e.g., yfinance, alpha_vantage, china vendors as configured)
  → SQLite (unified_news, kronos_forecasts, signal_evolution, rag_chunks_cache, …)
  → Response → Frontend
```

---

## 9. Performance & Constraints

### 9.1 Time Budgets
| Phase | Target | Max |
|-------|--------|-----|
| Single-ticker analysis | 3 min | 4 min |
| Batch (20 tickers) | 15 min | 20 min |
| Dashboard load | < 1 sec | 2 sec |
| History page (50 items) | < 1 sec | 2 sec |
| Report export (PDF) | < 10 sec | 30 sec |

### 9.2 Resource Limits
| Resource | Limit | Notes |
|----------|-------|-------|
| News aggregation | 20 req/min per gateway | When using a single HTTP facade (e.g., NewsNow); otherwise per-source throttles + global concurrency cap |
| Search / Jina / DDG | Per-operator quota | Bind to query budget per run to avoid batch stampedes |
| Kronos GPU memory | 2 GB | Fallback to CPU if unavailable |
| FinBERT model size | 500 MB | Download on first use |
| Embedding model | 100 MB | sentence-transformers/all-MiniLM-L6-v2 |
| SQLite cache | 1 GB | Auto-purge after 30 days |
| Max concurrent runs | 3 | Per-user queue |

### 9.3 Error Handling
| Error | UX | Recovery |
|-------|-----|----------|
| News aggregation unavailable | Show stale cache badge + fallback sources (e.g., direct vendor or cached snapshot) | Auto-retry with backoff; degrade to fewer sources |
| Kronos CUDA OOM | Show "CPU fallback" badge + continue | Pre-check GPU on startup |
| LLM rate limit | Pause node + countdown timer + auto-retry | Exponential backoff |
| Invalid ticker | Inline validation + format hint | Immediate |
| Pipeline crash | Save checkpoint + "Resume" button | Resume from last node |

---

## 10. Accessibility

### 10.1 Target
WCAG 2.1 AA across all surfaces (brand surface, research interface, embedded demo). The paper-collage aesthetic must never compromise legibility, contrast, or motion safety.

### 10.2 Texture as a known concern
Die-cut paper with visible grain is a deliberate aesthetic choice, but layered depth + grain can be visually noisy for some users (vestibular disorders, migraine triggers, attention sensitivities). Mitigations:
- Honor `prefers-reduced-motion` for all decorative motion (parallax, layered entrance, paper-tape transitions).
- Decorative motion and parallax must not block task completion; functional motion (progress, status) is allowed but skippable.
- The interface must remain fully functional with `prefers-reduced-motion: reduce`. Decorative layers fall back to flat compositions; functional motion uses static state indicators.

### 10.3 Color and contrast
- Pastel palette is committed (one warm hue carries 30-60% of the brand surface; restrained pastels on the research interface). The committed hue must hit AA contrast on every text/background pairing it touches.
- Charts: semantic red/green (BUY/SELL) require pattern or label alternatives for colorblind users. Don't rely on hue alone for signal state.
- Rating badges in the research interface use shape and label in addition to color: BUY = filled rounded chip, HOLD = outlined, SELL = filled square. Color reinforces; shape carries the signal.

### 10.4 Keyboard
- Full pipeline configuration and result review navigable without mouse.
- Brand surface sections (hero CTA, story, demo entry) are reachable and operable via keyboard alone.
- Paper-tape and torn-edge transitions are visual; they don't gate navigation.

### 10.5 Screen reader
- Progress monitor announces node completions. Evidence chain has ARIA labels for tree navigation.
- Embedded research interface inside the brand surface exposes the same a11y semantics as the standalone interface.
- Decorative paper-collage elements get `aria-hidden="true"` so they don't pollute the screen-reader tree.

---

## 11. Metrics & Success Criteria

### 11.1 Product Metrics
| Metric | Target | Measurement |
|--------|--------|-------------|
| Analysis completion rate | > 95% | % of started runs that complete without user cancellation |
| Time to decision | < 8 min | From ticker entry to final review |
| Report re-open rate | > 30% | % of users who re-open a past report within 7 days |
| Batch adoption | > 20% | % of active users who run batch at least monthly |
| Config change rate | > 5% | % of runs where user modifies default config |

### 11.2 Quality Metrics
| Metric | Target | Measurement |
|--------|--------|-------------|
| Signal accuracy (BUY/SELL) | > 60% | 5-day forward return direction match |
| Alpha generation | > 2% | Average 5-day alpha vs CSI 300 |
| Falsify rate | < 30% | % of signals that reverse within 5 days |
| Reflection usefulness | > 4.0/5 | User rating of auto-generated reflections |

---

## 12. Open Questions

1. **Mobile**: Is mobile analysis a P2? Primary users likely desktop-first, but quick status checks on mobile may be valuable.
2. **Real-time**: Should Active Runs panel auto-refresh for tickers currently running, or require manual refresh?
3. **Social Sharing**: Should users share anonymized decision cards (ticker + rating + rationale) to WeChat/Xueqiu?
4. **Broker Integration**: P3? One-click order execution via broker API (e.g., 富途, 老虎).
5. **Multi-language**: English interface for international users? Current pipeline outputs Chinese.
6. **Subscription Tiers**: Free tier (limited runs/day) vs Pro (unlimited + advanced models)?

---

## 13. Appendix: Design System Quick Reference

### Colors
- Signal Blue: `#3ba6f1` (actions, active states)
- Signal Mist: `#c1e1f7` (selected backgrounds)
- Canvas Fog: `#fafaf9` (app canvas)
- Cloud White: `#ffffff` (cards)
- Slate Text: `#0c0a09` (primary text)
- Ash Gray: `#78716c` (secondary text)
- Steel Gray: `#a8a29e` (tertiary labels)
- Stone Border: `#e5e7eb` (dividers, outlines)
- Ghost Ink: `#1c1917` (inverse surfaces)

### Typography
- Display: 52px / weight 600 / line-height 1
- Headline: 32px / weight 600 / line-height 1.12
- Title: 20px / weight 600 / line-height 1.2
- Body: 16px / weight 400 / line-height 1.5
- Label: 12px / weight 500 / line-height 1.5 / letter-spacing 0.048px

### Shadows
- Subtle Surface: `0px 1px 2px 0px rgba(0,0,0,0.05)`
- Section Lift: `0px 4px 16px 0px rgba(0,0,0,0.05)`
- Medium Utility: `0px 4px 6px -1px rgba(0,0,0,0.1), 0px 2px 4px -2px rgba(0,0,0,0.1)`

### Radii
- sm: 4px (inputs, utility)
- md: 10px (cards)
- lg: 16px (major sections)
- pill: 9999px (primary actions)
