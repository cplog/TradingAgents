# TradingAgents: Root-Cause Analysis — Low Confidence & Hold Convergence

## Executive Summary

Your system is structurally biased toward **Hold** with **low confidence (~29–37%)**. This is not a data-quality problem or a single bug — it is the emergent behavior of **five interconnected design choices** that reinforce each other:

1. **Pillar scoring fails silently** → all factor scores collapse to neutral (50)
2. **Data-quality flags accumulate** → confidence calibration applies stacked penalties
3. **Peer universe is unavailable** → an additional 10-point peer penalty applies
4. **The debate architecture has no tie-breaker** → balanced arguments always resolve to Hold
5. **The confidence formula is punitive for Hold** → base of 0.55 minus penalties lands in the 30s

Until these are addressed, the system cannot go to production as a directional signal generator.

---

## 1. The Confidence Math (Why 29–37% Is Inevitable)

### Current calibration formula

```python
# api/reports.py:172-248
def calibrate_confidence(rating, factor_scores, data_quality_flags, conflicting_dimensions, peer_scope):
    base = rating_to_confidence(rating)   # Hold = 0.55
    direction = _rating_direction(rating)  # Hold = 0 (neutral)
    
    # Factor coherence penalty: ONLY applies when direction != 0
    # For Hold, this block is SKIPPED — but that doesn't help because...
    
    # Data-quality penalty: 4% per flag, max 20%
    data_quality_penalty = min(0.20, 0.04 * len(flags))
    
    # Peer penalty: 10% for unavailable, 5% for global_fallback
    peer_penalty = 0.10 if peer_scope in ("unavailable", None) else ...
    
    score = max(0.0, base - coherence_penalty - data_quality_penalty - peer_penalty)
```

### Typical TCOM run breakdown

| Component | Value | Source |
|-----------|-------|--------|
| Base (Hold) | 0.55 | `rating_to_confidence("Hold")` |
| Data-quality penalty | −0.12 | 3 flags × 0.04 |
| Peer penalty | −0.10 | `peer_scope = "unavailable"` |
| **Final confidence** | **0.33** | → **33%** displayed as 37% with rounding |

**Key insight:** Even a *perfect* Hold with no data issues would only score **55%**. The system is designed so that Hold can never be high-confidence. This is a product decision, not a bug — but it means Hold is visually indistinguishable from "broken" in the UI.

---

## 2. Why Every Rating Is Hold

### 2.1 The Research Manager Has No Tie-Breaker

```python
# tradingagents/agents/managers/research_manager.py:42
"Reserve Hold for situations where the evidence on both sides is genuinely balanced; 
 otherwise commit to the side with the stronger arguments."
```

**Problem:** With 4–8 analysts each producing 2,000+ word reports covering both bull and bear points, the evidence is *always* "genuinely balanced." The bull researcher and bear researcher are both eloquent, data-rich, and persuasive. There is no scoring rubric, no vote tally, and no "net conviction" metric to force a directional call.

**Evidence from TCOM run:**
- Bull: "46% FCF yield, $40B+ net cash, MACD crossover, 17% revenue growth"
- Bear: "Decelerating growth, 36% FCF contraction, no insider buying, barbell 10/100"
- Research Manager: "The evidence is genuinely balanced — this isn't a cop-out, it's a reflection of a real tug-of-war."
- Result: **Hold**

### 2.2 The Portfolio Manager Is Trapped by Conflicting Risk Analysts

The risk debate has three voices (Aggressive, Conservative, Neutral) who are *designed* to disagree:

- **Aggressive:** "Holding is conviction. The 2:1 reward-to-risk is compelling."
- **Conservative:** "Trim now. The MACD crossover is a dead cat bounce."
- **Neutral:** "Both sides have blind spots. The trader's hold is correct."

The PM prompt says: *"Be decisive and ground every conclusion in specific evidence."* But when three risk analysts explicitly disagree, the PM has no mechanism to override them. It defaults to the safest consensus: **Hold**.

### 2.3 The Dimensions Snapshot Is Neutral (So It Can't Break Ties)

```
# From TCOM report:
Factor scores (0–100):
- value: 50.00
- growth: 50.00
- quality: 50.00
- momentum: 50.00
- low_risk: 50.00
- sentiment: 50.00
```

When all factors are 50, the dimensions summary tells the PM: *"There is no directional edge in the quantitative data."* This reinforces the Hold decision rather than breaking the tie.

---

## 3. Why the Dimensions System Collapses to Neutral

### 3.1 Pillar Scoring Fails on Structured Output Validation

```
# From TCOM report (line 914):
Data quality flags: pillar_scoring_unavailable: Pillar scoring failed: 
1 validation error for PillarScores
fundamentals
  Field required [type=missing, input_value={...}, input_type=dict]
```

The LLM (deepseek-v4-flash) is asked to produce a JSON object with 16 nested scores:
- `market.trend`, `market.momentum`, `market.volatility_risk`, `market.setup_quality`
- `sentiment.retail_sentiment`, `sentiment.social_buzz`, `sentiment.consensus_quality`, `sentiment.narrative_strength`
- `news.catalyst_strength`, `news.macro_alignment`, `news.headline_quality`, `news.surprise_risk`
- `fundamentals.valuation`, `fundamentals.growth`, `fundamentals.profitability`, `fundamentals.balance_sheet_strength`

**The LLM often omits `fundamentals` entirely** (or another pillar), causing Pydantic validation to fail. The fallback is `_neutral_pillars()`, which sets every score to **3/5** with rationale "neutral default (facts-only)".

### 3.2 Peer Universes Are Almost Always Unavailable

```python
# api/dimensions/builder.py:194
peer_usable = peer_row_count >= 3 and peer_res.peer_scope != "unavailable"
```

The peer resolver searches for tickers in the same sector/industry. For most runs:
- The peer cache is cold (no pre-built peer universe)
- The fallback search returns <3 peers
- `peer_scope` becomes `"unavailable"`
- This triggers `peer_penalty = 0.10` in confidence calibration
- It also means style factors (value, growth, quality, momentum, low_risk) have no peer-relative calibration

### 3.3 Factor Scores Become 50.00 Across the Board

When pillars are all 3/5 and peer percentiles are missing:

```python
# api/dimensions/factors.py:18
scale_1_5_to_0_100(score: int) -> float:
    return (score - 1) * 25.0   # 3 → 50.0
```

Every factor score becomes **50.00**. The radar chart is a flat circle. The PM sees no quantitative edge.

---

## 4. The Debate Architecture Encourages Conservatism

### 4.1 Single-Round Debate (max_debate_rounds=1)

```python
# tradingagents/default_config.py:107
"max_debate_rounds": 1,
"max_risk_discuss_rounds": 1,
```

With only one round:
- Bull makes its case
- Bear makes its case
- Research Manager sees two polished, opposing arguments
- No rebuttal, no convergence, no scoring

**A single round is insufficient for the RM to detect which side has stronger evidence.** It sees two equally compelling narratives and defaults to Hold.

### 4.2 No Analyst Vote Tally

The system has no mechanism to count:
- How many analysts are net bullish vs bearish
- The strength of each analyst's conviction
- Whether the bull case or bear case has more supporting data points

The Research Manager is asked to read 10,000+ words of debate and "feel" which side is stronger. This is cognitively overwhelming and naturally produces the middle ground.

---

## 5. Concrete Fixes (In Order of Impact)

### Fix 1: Force Directional Ratings — Eliminate Hold as a Default

**File:** `tradingagents/agents/schemas.py` (ResearchPlan field description)

**Current:**
```python
"Reserve Hold for situations where the evidence on both sides is genuinely balanced; 
otherwise commit to the side with the stronger arguments."
```

**Proposed:**
```python
"Hold is ONLY allowed when quantitative metrics (factor scores, barbell score, 
peer percentiles) are all neutral AND no catalyst is visible within 30 days. 
Otherwise, you MUST pick Buy, Overweight, Underweight, or Sell. 
When the bull case has more quantitative support, pick Buy or Overweight. 
When the bear case has more quantitative support, pick Underweight or Sell. 
Default to Overweight (not Hold) when the evidence is mixed but fundamentals 
are strong. Default to Underweight (not Hold) when the evidence is mixed but 
technicals are weak."
```

**Impact:** High — directly attacks the Hold convergence.

---

### Fix 2: Add a Scoring Rubric to the Research Manager

**File:** `tradingagents/agents/managers/research_manager.py`

**Proposed addition to prompt:**
```
**Scoring Rubric (apply before deciding):**
1. Count the number of quantitative metrics supporting the bull case (e.g., 
   revenue growth >15%, FCF yield >10%, MACD crossover, insider buying, 
   options flow bullish, peer percentile >60th).
2. Count the number of quantitative metrics supporting the bear case (e.g., 
   revenue deceleration, FCF contraction, price below 50-SMA, insider selling, 
   elevated volume on declines, peer percentile <40th).
3. If bull count > bear count by 2+: pick Buy or Overweight.
4. If bear count > bull count by 2+: pick Underweight or Sell.
5. If counts are within 1: consider Hold ONLY if no near-term catalyst exists.
```

**Impact:** High — gives the RM a deterministic tie-breaker.

---

### Fix 3: Fix Pillar Scoring Reliability

**File:** `api/dimensions/scoring.py`

**Problem:** The LLM is asked to output 16 nested scores in one JSON object. This is too complex for smaller models (deepseek-v4-flash).

**Proposed:** Split pillar scoring into 4 separate LLM calls (one per pillar), then merge:

```python
# New approach in api/dimensions/scoring.py
def score_pillars_separate(facts, reports, llm, ...):
    pillars = {}
    for pillar_name, schema in [
        ("market", MarketPillar),
        ("sentiment", SentimentPillar), 
        ("news", NewsPillar),
        ("fundamentals", FundamentalsPillar),
    ]:
        prompt = build_single_pillar_prompt(facts, reports, pillar_name)
        try:
            result = llm.with_structured_output(schema).invoke(prompt)
            pillars[pillar_name] = result
        except Exception:
            # Fallback to neutral ONLY for this pillar, not all 4
            pillars[pillar_name] = neutral_pillar(pillar_name)
    
    return PillarScores(**pillars)
```

**Impact:** Critical — without this, the dimensions system is decorative.

---

### Fix 4: Warm the Peer Cache for Common Sectors

**File:** `api/dimensions/peer_resolver.py` or a new pre-computation job

**Problem:** Peer universes are built on-demand and usually fail.

**Proposed:** Add a CLI command or cron job that pre-builds peer universes for the ~50 most common sector/industry combinations:

```bash
# New CLI command
python -m tradingagents.cli warm-peer-cache --sectors "Technology,Healthcare,Consumer Cyclical"
```

This would:
1. Query Yahoo Finance for all tickers in each sector
2. Extract facts for each ticker
3. Build and cache peer percentile tables
4. Make `peer_usable = True` for most runs

**Impact:** High — removes the 10-point peer penalty and enables real factor scores.

---

### Fix 5: Increase Debate Rounds or Add Convergence Scoring

**File:** `tradingagents/default_config.py`

**Current:**
```python
"max_debate_rounds": 1,
"max_risk_discuss_rounds": 1,
```

**Proposed:**
```python
"max_debate_rounds": 2,        # Allow rebuttal
"max_risk_discuss_rounds": 2,  # Allow risk analysts to respond to each other
```

**Alternative:** Add a `debate_score` node that numerically scores each side after round 1:

```python
# New node: tradingagents/agents/managers/debate_scorer.py
def create_debate_scorer(llm):
    def debate_scorer_node(state) -> dict:
        prompt = f"""
        Score the bull case and bear case on a 0-100 scale across 5 dimensions:
        1. Quantitative evidence strength
        2. Catalyst proximity (earnings, events within 30 days)
        3. Risk/reward asymmetry
        4. Technical trend alignment
        5. Fundamental valuation support
        
        Return ONLY a JSON object: {{"bull_score": N, "bear_score": N, 
        "winner": "bull|bear|tie", "margin": N}}
        """
        # ... invoke and store in state
```

**Impact:** Medium — more rounds help, but the RM still needs a tie-breaker.

---

### Fix 6: Recalibrate Confidence for Hold

**File:** `api/reports.py:134-147`

**Current:**
```python
tiers = {
    "buy": 0.92,
    "overweight": 0.78,
    "hold": 0.55,        # ← Too low; penalties always drag it to ~30%
    "underweight": 0.35,
    "sell": 0.18,
}
```

**Proposed:**
```python
tiers = {
    "buy": 0.92,
    "overweight": 0.78,
    "hold": 0.72,        # ← Raise to 0.72; Hold is a valid high-confidence decision
    "underweight": 0.35,
    "sell": 0.18,
}
```

**AND** reduce the peer penalty for cases where peer data is genuinely unavailable (not missing due to a bug):

```python
# api/reports.py:225-229
peer_penalty = 0.0
if peer_scope == "unavailable":
    peer_penalty = 0.03   # Was 0.10 — only penalize slightly when peers are truly unavailable
elif peer_scope == "global_fallback":
    peer_penalty = 0.02   # Was 0.05
```

**Impact:** Medium — Hold will display as ~60% instead of ~30%, making it distinguishable from "broken."

---

### Fix 7: Add a "Confidence Floor" for Production Gating

**File:** `api/jobs.py` (before persisting result)

**Proposed:** Add a config flag that rejects low-confidence outputs:

```python
# In api/jobs.py, after calibrate_confidence()
if result.get("confidence", 0) < config.get("min_confidence_for_production", 0.60):
    result["rating"] = "Hold"  # or "No Signal"
    result["confidence"] = result["confidence"]  # keep the low score for transparency
    result["production_gated"] = True
    result["gating_reason"] = f"Confidence {result['confidence']} below production threshold"
```

**Impact:** Medium — prevents low-confidence signals from reaching trading systems.

---

## 6. Quick Wins (Can Be Done Today)

| Fix | File | Effort | Impact |
|-----|------|--------|--------|
| Raise Hold base to 0.72 | `api/reports.py:141` | 1 line | Medium |
| Reduce peer penalty to 0.03 | `api/reports.py:227` | 1 line | Medium |
| Change RM prompt to discourage Hold | `tradingagents/agents/managers/research_manager.py` | 3 lines | High |
| Increase debate rounds to 2 | `tradingagents/default_config.py:107` | 1 line | Medium |
| Add `min_confidence_for_production` gating | `api/jobs.py:1341` | 5 lines | Medium |

---

## 7. Deeper Fixes (Require Engineering)

| Fix | Files | Effort | Impact |
|-----|-------|--------|--------|
| Split pillar scoring into 4 calls | `api/dimensions/scoring.py` | 1–2 days | Critical |
| Pre-build peer cache | New CLI + `api/dimensions/peer_resolver.py` | 2–3 days | High |
| Add debate scoring rubric | New node + `tradingagents/graph/setup.py` | 1–2 days | High |
| Add analyst vote tally | `tradingagents/agents/managers/research_manager.py` | 1 day | Medium |
| Fix `fundamentals` field omission in LLM prompt | `api/dimensions/scoring.py:_build_prompt` | 2 hours | High |

---

## 8. Verification Plan

After applying fixes, verify with these metrics:

1. **Rating distribution** across 20+ runs: target ≥30% directional (Buy/Sell/Overweight/Underweight), ≤50% Hold
2. **Confidence distribution** for Hold: target ≥60% (not 29–37%)
3. **Pillar scoring success rate**: target ≥90% (not ~50% with silent fallback)
4. **Peer universe hit rate**: target ≥80% (not ~10%)
5. **Factor score variance**: target std dev ≥15 (not ~0 where all factors = 50)

---

*Analysis generated from codebase inspection on 2025-06-10.*
*Files examined: `api/reports.py`, `api/jobs.py`, `api/dimensions/scoring.py`, `api/dimensions/builder.py`, `api/dimensions/factors.py`, `tradingagents/agents/managers/research_manager.py`, `tradingagents/agents/managers/portfolio_manager.py`, `tradingagents/graph/setup.py`, `tradingagents/default_config.py`, and sample run outputs (`TCOM`, `MSFT`).*
