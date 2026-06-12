# HPM Pre-Filter Phase 1 — Execution Plan

**Date:** 2026-06-10  
**Goal:** Add deterministic Hard Penny Market (HPM) regime signal as a reusable pre-filter for Topics and analysis, behind feature flags.

## Stage 1 — Foundation: HPM Scorer + Config + Endpoint
**Skill:** None (custom orchestration)  
**Files:**
- `api/hpm.py` — new deterministic HPM scoring service
- `tradingagents/default_config.py` — add regime feature flags
- `api/config.py` — wire env overrides
- `api/main.py` — add `GET /api/hpm/score` endpoint

**Contract:**
- `api/hpm.py` exports:
  - `HPMScoreResult` (Pydantic model)
  - `compute_hpm_score(index: str = "SPY") -> HPMScoreResult`
  - `get_trading_posture(composite_score: float) -> str`
- Score payload: `composite_score` (0-5), `signals` (dict), `trading_posture`, `timestamp`, `index`, `regime_reason_codes`, `dominant_transmission_chain`, `regime_confidence`
- Config flags (default `false`):
  - `regime_prefilter_enabled`
  - `regime_prefilter_mode` (`observe|enforce`, default `observe`)
  - `regime_topic_multipliers` (dict of style -> multiplier)
- Endpoint: `GET /api/hpm/score?index=SPY` — readonly, returns JSON

## Stage 2 — Topics Integration (flagged)
**Files:**
- `api/topics_models.py` — add `RegimeAdjustedScore` model, extend `TopicSummary` and `TopicRun`
- `api/topics_extract.py` — add `apply_regime_multipliers(candidates, regime_snapshot)` when flag ON
- `api/topics_store.py` — `list_summaries()` computes `topic_regime_adjusted_score` when enabled

**Contract:**
- Formula: `topic_regime_adjusted_score = base_topic_score * style_multiplier * regime_confidence`
- Keep `base_topic_score`, `style_multiplier`, `regime_confidence`, `final_score` in metadata
- Preserve exact old behavior when `regime_prefilter_enabled=false`

## Stage 3 — Analysis Gating (flagged)
**Files:**
- `api/main.py` — add regime snapshot annotation to analysis request handling
- `tradingagents/default_config.py` — add `regime_analysis_gate` settings

**Contract:**
- `observe` mode: annotate logs/metadata with regime snapshot only
- `enforce` mode: tighten selection policy (reduce expansion/thresholds) without breaking APIs

## Stage 4 — Tests
**Files:**
- `tests/test_hpm.py` — unit tests for scorer, posture mapping, reason codes
- `tests/test_api_hpm.py` — API tests for endpoint
- `tests/test_topics_regime.py` — topics integration tests (multiplier ON/OFF parity)

**Validation:**
- Feature flag OFF: exact old behavior
- Feature flag ON (observe): regime snapshot + deterministic adjusted scores
- Feature flag ON (enforce): policy gates activate
- Score decomposition assertions: base, multiplier, confidence, final

## Stage 5 — UI/UX Integration
**Files:**
- `frontend/src/api.ts` — add `HPMScoreResult` type, `fetchHpmScore` function, and extend `TopicSummary`/`TickerCandidate` types
- `frontend/src/hooks/useTopics.ts` — sort topics by `topic_regime_adjusted_score` descending if present
- `frontend/src/pages/TopicsPage.tsx` — fetch and display the current HPM score banner
- `frontend/src/components/topics/TopicCard.tsx` — display regime-adjusted score with visual cue
- `frontend/src/components/topics/TickerCandidateRow.tsx` — show confidence decomposition (`Base × Style × Regime Conf = Final`) in tooltip
- `frontend/src/pages/SystemPage.tsx` — add user controls for `regime_prefilter_enabled` and `regime_prefilter_mode`

**Validation:**
- Topics page shows current market regime banner
- Topics are sorted by adjusted score when regime pre-filter is enabled
- System page allows toggling the pre-filter and mode

## Merge Order
1. Stage 1 (foundation)
2. Stage 2 + Stage 3 in parallel (both depend on Stage 1 contract)
3. Stage 4 (depends on Stage 2 + 3)
4. Stage 5 (UI/UX integration)
5. Final integration + run test suite
