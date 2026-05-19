# Product Specification: TradingAgents Command Center

> **Version**: 1.0-fusion  
> **Last Updated**: 2026-05-17  
> **Scope**: TradingAgents-astock × Awesome-finance-skills integration  
> **Design System**: [TradingAgents Command Center Design System](../design-system.md)

---

## 1. Product Overview

### 1.1 Elevator Pitch
TradingAgents Command Center is an **operational research interface** that transforms complex multi-agent market analysis into an actionable, repeatable workflow. Users configure a ticker, trigger a 7-analyst + AI prediction pipeline backed by **[Awesome-finance-skills](https://github.com/RKiding/Awesome-finance-skills)**-aligned data (multi-source news, A-share/HK/US market data, sentiment, search/RAG, Kronos forecasting), and receive a structured decision package—rating, evidence chain, forecast chart, and risk assessment—in under 4 minutes.

### 1.2 Product Purpose
Turn a complex research pipeline into an actionable flow: **configure → run → inspect artifacts → decide next steps**. Success means users complete an analysis loop with high confidence in what happened, why the rating was produced, and what to do next—without hunting across multiple tools.

### 1.3 Brand Personality
**Approachable, guided, and competent.**

Voice and tone reduce cognitive load for non-expert users while preserving technical trust for advanced users. The interface feels calm and clear under uncertainty, with explicit status language and practical next actions.

### 1.4 Anti-References (What We Reject)
- ❌ Generic glossy SaaS marketing aesthetics that prioritize decoration over utility.
- ❌ Neon trading-terminal visuals that increase urgency and fatigue.
- ❌ Dense enterprise backoffice complexity with overloaded controls and jargon-heavy labels.
- ❌ Playful consumer-app styling that weakens financial-research credibility.

### 1.5 Data Sources & Awesome-finance-skills Modules

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

1. **Guide first, expose depth progressively.** Keep essential actions obvious and move advanced controls behind clear disclosures.
2. **Make system state legible at a glance.** Users should always know run status, progress, and failure context without digging.
3. **Keep evidence close to decisions.** Present ratings, confidence, and report context in one continuous flow.
4. **Optimize for repeatable workflows.** Favor consistency across dashboard, history, screener, and system views so frequent users build speed.
5. **Prefer clarity over spectacle.** Visual design supports trust, readability, and decision quality, not novelty.

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

### 10.1 Current Baseline
- Readable contrast and typographic hierarchy on all primary surfaces.
- Keyboard-reachable controls for core run and review flows.
- Reduced-motion user preferences respected where motion is used.

### 10.2 WCAG 2.1 AA Milestone
- **Color**: Signal Blue (`#3ba6f1`) on white passes AA. Ensure semantic red/green on charts have pattern/texture alternatives for colorblind users.
- **Keyboard**: Full pipeline configuration and result review navigable without mouse.
- **Screen Reader**: Progress monitor announces node completions. Evidence chain has ARIA labels for tree navigation.
- **Motion**: Respect `prefers-reduced-motion`. Disable spinner animations, use static progress indicators.

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
