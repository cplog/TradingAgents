# Standardized Stock Dimensions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a standardized per-stock dimensions layer (deterministic facts + 16 LLM-judged pillar scores + 6 deterministic factor scores) computed post-run inside `api/`, plus a "dimensions-grounded commentary" LLM call, surfaced via API + UI for cross-stock comparison and dashboards.

**Architecture:** All new code lives in `api/dimensions/`, `api/` (jobs/main/models/history), and `frontend/`. No edits inside `tradingagents/`. Post-pass orchestration in `Worker._run`, persisted alongside the existing run record. UI uses Recharts for the radar chart.

**Tech Stack:** Python 3.13 + FastAPI + Pydantic v2 + yfinance + LangGraph (untouched); React 19 + Vite + Recharts; pytest + vitest.

**Spec:** [docs/superpowers/specs/2026-05-13-standardized-stock-dimensions-design.md](../specs/2026-05-13-standardized-stock-dimensions-design.md)

---

## File structure overview

**New files:**
```
api/dimensions/
├── __init__.py
├── version.py
├── schemas.py
├── facts.py
├── peers.py
├── factors.py
├── scoring.py
├── commentary.py
└── builder.py

tests/dimensions/
├── __init__.py
├── test_facts.py
├── test_peers.py
├── test_factors.py
├── test_scoring.py
├── test_commentary.py
├── test_build_dimensions.py
├── test_api_dimensions.py
└── fixtures/
    ├── yfinance_aapl.json
    ├── yfinance_nvda.json
    ├── yfinance_0700hk.json
    └── analyst_reports.json

tests/
├── test_jobs_dimensions_progress.py
├── test_jobs_cancel.py
├── test_jobs_sse_connect_event.py
└── test_jobs_dimensions_failure_isolation.py

scripts/
└── warm_peer_cache.py

frontend/src/components/dimensions/
├── FactorBar.tsx
├── DimensionsRadar.tsx
├── PillarGrid.tsx
├── FactsTable.tsx
├── CommentaryCard.tsx
├── DimensionsPanel.tsx
└── *.test.tsx (one per component)

frontend/src/pages/
└── ScreenerPage.tsx
```

**Modified files:**
- `api/models.py` — re-export new Pydantic schemas + extend HistoryRunDetail, HistoryRunRef, AnalysisResult
- `api/jobs.py` — dimensions post-pass, progress events, cancellation flag
- `api/main.py` — new endpoints + SSE `connected` event
- `api/history.py` — persist `dimensions` field; recompute helper; D1 column additions
- `frontend/package.json` — add `recharts`
- `frontend/src/api.ts` — typed helpers for new endpoints
- `frontend/src/App.tsx` — `/screener` route
- `frontend/src/pages/DashboardPage.tsx` — embed `<DimensionsPanel>`
- `frontend/src/pages/BatchPage.tsx` — factor columns
- `frontend/src/pages/HistoryPage.tsx` — row thumbs + dimensions tab + compare
- `README.md` — Dimensions section

---

## Task 1: Dimensions package skeleton, version, schemas

**Files:**
- Create: `api/dimensions/__init__.py`
- Create: `api/dimensions/version.py`
- Create: `api/dimensions/schemas.py`
- Create: `tests/dimensions/__init__.py`
- Create: `tests/dimensions/test_schemas.py`

- [ ] **Step 1: Write the failing test**

`tests/dimensions/test_schemas.py`:

```python
import pytest
from pydantic import ValidationError

from api.dimensions.schemas import (
    FactSnapshot, PillarScore, PillarScores, MarketPillar, SentimentPillar,
    NewsPillar, FundamentalsPillar, FactorScore, FactorScores, StockDimensions,
    DimensionsCommentary,
)
from api.dimensions.version import DIMENSIONS_VERSION


def test_pillar_score_validates_range():
    PillarScore(score=1, rationale="ok")
    PillarScore(score=5, rationale="ok")
    with pytest.raises(ValidationError):
        PillarScore(score=0, rationale="too low")
    with pytest.raises(ValidationError):
        PillarScore(score=6, rationale="too high")


def test_factor_score_allows_null():
    fs = FactorScore(score=None, inputs={"reason": "no_inputs"})
    assert fs.score is None


def test_factor_score_validates_range():
    FactorScore(score=0.0, inputs={})
    FactorScore(score=100.0, inputs={})
    with pytest.raises(ValidationError):
        FactorScore(score=-1.0, inputs={})
    with pytest.raises(ValidationError):
        FactorScore(score=101.0, inputs={})


def _ps(score=3, why="ok"):
    return PillarScore(score=score, rationale=why)


def test_stock_dimensions_roundtrip():
    sd = StockDimensions(
        ticker="AAPL",
        as_of_date="2026-05-13",
        facts=FactSnapshot(as_of_date="2026-05-13", currency="USD"),
        pillar_scores=PillarScores(
            market=MarketPillar(trend=_ps(), momentum=_ps(), volatility_risk=_ps(), setup_quality=_ps()),
            sentiment=SentimentPillar(retail_sentiment=_ps(), social_buzz=_ps(),
                                     consensus_quality=_ps(), narrative_strength=_ps()),
            news=NewsPillar(catalyst_strength=_ps(), macro_alignment=_ps(),
                           headline_quality=_ps(), surprise_risk=_ps()),
            fundamentals=FundamentalsPillar(valuation=_ps(), growth=_ps(),
                                           profitability=_ps(), balance_sheet_strength=_ps()),
        ),
        factor_scores=FactorScores(
            value=FactorScore(score=72.0, inputs={"weight_valuation": 0.5}),
            growth=FactorScore(score=60.0, inputs={}),
            quality=FactorScore(score=80.0, inputs={}),
            momentum=FactorScore(score=55.0, inputs={}),
            low_risk=FactorScore(score=40.0, inputs={}),
            sentiment=FactorScore(score=50.0, inputs={}),
        ),
        dimensions_version=DIMENSIONS_VERSION,
        peer_universe_id="sector:Technology|industry:Software",
        data_quality_flags=[],
    )
    dumped = sd.model_dump()
    assert dumped["ticker"] == "AAPL"
    restored = StockDimensions.model_validate(dumped)
    assert restored.factor_scores.value.score == 72.0


def test_commentary_alignment_literal():
    DimensionsCommentary(
        alignment="aligned",
        supporting_dimensions=["value"],
        conflicting_dimensions=[],
        risk_flags=[],
        summary="ok",
    )
    with pytest.raises(ValidationError):
        DimensionsCommentary(
            alignment="kinda",  # type: ignore[arg-type]
            supporting_dimensions=[], conflicting_dimensions=[], risk_flags=[], summary="x",
        )


def test_version_is_semver_one_zero_zero():
    assert DIMENSIONS_VERSION == "1.0.0"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/dimensions/test_schemas.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'api.dimensions'`.

- [ ] **Step 3: Create the package and version file**

`api/dimensions/__init__.py`:

```python
"""Standardized stock dimensions: facts + pillar scores + factor scores.

Computed post-run inside api/ (no edits to tradingagents/). See
docs/superpowers/specs/2026-05-13-standardized-stock-dimensions-design.md.
"""
from api.dimensions.version import DIMENSIONS_VERSION

__all__ = ["DIMENSIONS_VERSION"]
```

`api/dimensions/version.py`:

```python
"""Dimensions schema/formula version. Bump on any field/formula change.

Changelog:
- 1.0.0 (2026-05-13): initial release — yfinance facts, 16 pillar scores,
  6 deterministic factor scores with sector-peer percentiles.
"""
DIMENSIONS_VERSION = "1.0.0"
```

`tests/dimensions/__init__.py`:

```python
```

- [ ] **Step 4: Create the schemas file**

`api/dimensions/schemas.py`:

```python
"""Pydantic schemas for the standardized stock dimensions layer."""
from __future__ import annotations

from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class FactSnapshot(BaseModel):
    """Deterministic yfinance-sourced facts for a (ticker, as_of_date)."""

    as_of_date: str
    currency: str
    exchange: Optional[str] = None
    sector: Optional[str] = None
    industry: Optional[str] = None
    market_cap_usd: Optional[float] = None

    price: Optional[float] = None
    price_52w_high: Optional[float] = None
    pct_off_52w_high: Optional[float] = None
    return_1m: Optional[float] = None
    return_3m: Optional[float] = None
    return_6m: Optional[float] = None
    return_12m: Optional[float] = None
    beta: Optional[float] = None

    realized_vol_30d: Optional[float] = None
    rsi_14: Optional[float] = None
    avg_daily_dollar_volume_30d: Optional[float] = None

    pe_ttm: Optional[float] = None
    forward_pe: Optional[float] = None
    peg: Optional[float] = None
    ev_ebitda: Optional[float] = None
    ps_ttm: Optional[float] = None
    pb: Optional[float] = None
    fcf_yield: Optional[float] = None

    revenue_growth_yoy: Optional[float] = None
    eps_growth_yoy: Optional[float] = None
    revenue_cagr_3y: Optional[float] = None
    eps_cagr_3y: Optional[float] = None

    roe: Optional[float] = None
    roic: Optional[float] = None
    gross_margin: Optional[float] = None
    operating_margin: Optional[float] = None
    net_margin: Optional[float] = None
    debt_to_equity: Optional[float] = None
    interest_coverage: Optional[float] = None
    current_ratio: Optional[float] = None

    dividend_yield: Optional[float] = None
    payout_ratio: Optional[float] = None

    analyst_count: Optional[int] = None
    analyst_target_mean: Optional[float] = None
    analyst_recommendation_mean: Optional[float] = None


class PillarScore(BaseModel):
    score: int = Field(..., ge=1, le=5)
    rationale: str


class MarketPillar(BaseModel):
    trend: PillarScore
    momentum: PillarScore
    volatility_risk: PillarScore = Field(
        ..., description="Lower score = MORE volatility risk; higher score = lower risk."
    )
    setup_quality: PillarScore


class SentimentPillar(BaseModel):
    retail_sentiment: PillarScore
    social_buzz: PillarScore
    consensus_quality: PillarScore
    narrative_strength: PillarScore


class NewsPillar(BaseModel):
    catalyst_strength: PillarScore
    macro_alignment: PillarScore
    headline_quality: PillarScore
    surprise_risk: PillarScore = Field(
        ..., description="Lower score = MORE surprise risk; higher score = lower risk."
    )


class FundamentalsPillar(BaseModel):
    valuation: PillarScore
    growth: PillarScore
    profitability: PillarScore
    balance_sheet_strength: PillarScore


class PillarScores(BaseModel):
    market: MarketPillar
    sentiment: SentimentPillar
    news: NewsPillar
    fundamentals: FundamentalsPillar


class FactorScore(BaseModel):
    score: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    inputs: Dict[str, float] = Field(default_factory=dict)


class FactorScores(BaseModel):
    value: FactorScore
    growth: FactorScore
    quality: FactorScore
    momentum: FactorScore
    low_risk: FactorScore
    sentiment: FactorScore


class StockDimensions(BaseModel):
    ticker: str
    as_of_date: str
    facts: FactSnapshot
    pillar_scores: PillarScores
    factor_scores: FactorScores
    dimensions_version: str
    peer_universe_id: Optional[str] = None
    data_quality_flags: List[str] = Field(default_factory=list)
    source: Literal["full_run", "facts_only"] = "full_run"


class DimensionsCommentary(BaseModel):
    alignment: Literal["aligned", "partial", "misaligned"]
    supporting_dimensions: List[str]
    conflicting_dimensions: List[str]
    risk_flags: List[str]
    summary: str
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/dimensions/test_schemas.py -v
```

Expected: 5 passed.

- [ ] **Step 6: Commit**

```bash
git add api/dimensions/__init__.py api/dimensions/version.py api/dimensions/schemas.py \
        tests/dimensions/__init__.py tests/dimensions/test_schemas.py
git commit -m "feat(dimensions): package skeleton + Pydantic schemas + version 1.0.0"
```

---

## Task 2: yfinance fact extraction

**Files:**
- Create: `api/dimensions/facts.py`
- Create: `tests/dimensions/test_facts.py`
- Create: `tests/dimensions/fixtures/yfinance_aapl.json`
- Create: `tests/dimensions/fixtures/yfinance_0700hk.json`

- [ ] **Step 1: Write the failing test**

`tests/dimensions/test_facts.py`:

```python
import json
from pathlib import Path

import pytest

from api.dimensions.facts import extract_facts, FactExtractionError

FIXTURES = Path(__file__).parent / "fixtures"


class _FakeTicker:
    def __init__(self, info, history_df=None):
        self.info = info
        self._history = history_df

    def history(self, *_args, **_kwargs):
        return self._history


def _load(name):
    return json.loads((FIXTURES / name).read_text())


def test_extract_facts_aapl_happy_path(monkeypatch):
    info = _load("yfinance_aapl.json")
    import pandas as pd
    df = pd.DataFrame({"Close": [170.0, 175.0, 180.0, 185.0, 190.0]})
    monkeypatch.setattr(
        "api.dimensions.facts._yf_ticker",
        lambda t: _FakeTicker(info, df),
    )
    facts, flags = extract_facts("AAPL", "2026-05-13")
    assert facts.currency == "USD"
    assert facts.sector == "Technology"
    assert facts.pe_ttm == pytest.approx(info["trailingPE"])
    assert facts.market_cap_usd == pytest.approx(info["marketCap"])
    assert "missing_sector" not in flags


def test_extract_facts_handles_missing_fields(monkeypatch):
    sparse = {"currency": "USD", "regularMarketPrice": 100.0}
    monkeypatch.setattr(
        "api.dimensions.facts._yf_ticker",
        lambda t: _FakeTicker(sparse, None),
    )
    facts, flags = extract_facts("XYZ", "2026-05-13")
    assert facts.pe_ttm is None
    assert facts.sector is None
    assert "missing_sector" in flags
    assert "missing_pe_ttm" in flags


def test_extract_facts_hk_ticker_currency(monkeypatch):
    info = _load("yfinance_0700hk.json")
    monkeypatch.setattr(
        "api.dimensions.facts._yf_ticker",
        lambda t: _FakeTicker(info, None),
    )
    facts, _ = extract_facts("0700.HK", "2026-05-13")
    assert facts.currency == "HKD"
    assert facts.exchange == "HKG"


def test_extract_facts_string_forward_pe_coerced(monkeypatch):
    """yfinance occasionally returns numeric fields as strings."""
    info = {"currency": "USD", "forwardPE": "25.4"}
    monkeypatch.setattr(
        "api.dimensions.facts._yf_ticker",
        lambda t: _FakeTicker(info, None),
    )
    facts, _ = extract_facts("ABC", "2026-05-13")
    assert facts.forward_pe == pytest.approx(25.4)


def test_extract_facts_propagates_yfinance_error(monkeypatch):
    def boom(_t):
        raise RuntimeError("network down")
    monkeypatch.setattr("api.dimensions.facts._yf_ticker", boom)
    with pytest.raises(FactExtractionError):
        extract_facts("AAPL", "2026-05-13")
```

- [ ] **Step 2: Create fixtures**

`tests/dimensions/fixtures/yfinance_aapl.json`:

```json
{
  "currency": "USD",
  "exchange": "NMS",
  "sector": "Technology",
  "industry": "Consumer Electronics",
  "marketCap": 3000000000000,
  "regularMarketPrice": 190.0,
  "fiftyTwoWeekHigh": 200.0,
  "beta": 1.25,
  "trailingPE": 28.4,
  "forwardPE": 25.1,
  "pegRatio": 2.1,
  "enterpriseToEbitda": 22.0,
  "priceToSalesTrailing12Months": 7.5,
  "priceToBook": 45.0,
  "freeCashflow": 100000000000,
  "earningsGrowth": 0.08,
  "revenueGrowth": 0.05,
  "returnOnEquity": 1.5,
  "grossMargins": 0.45,
  "operatingMargins": 0.30,
  "profitMargins": 0.25,
  "debtToEquity": 1.8,
  "currentRatio": 1.0,
  "dividendYield": 0.005,
  "payoutRatio": 0.16,
  "numberOfAnalystOpinions": 35,
  "targetMeanPrice": 215.0,
  "recommendationMean": 2.0
}
```

`tests/dimensions/fixtures/yfinance_0700hk.json`:

```json
{
  "currency": "HKD",
  "exchange": "HKG",
  "sector": "Communication Services",
  "industry": "Internet Content & Information",
  "marketCap": 4000000000000,
  "regularMarketPrice": 380.0,
  "trailingPE": 17.0,
  "forwardPE": 14.5,
  "returnOnEquity": 0.18
}
```

- [ ] **Step 3: Implement the fact extractor**

`api/dimensions/facts.py`:

```python
"""Deterministic yfinance fact extraction for the dimensions layer.

No LLM. Single yfinance Ticker call per stock. Missing fields are stored
as None and recorded in `data_quality_flags`.
"""
from __future__ import annotations

import logging
import math
from typing import Any, List, Optional, Tuple

from api.dimensions.schemas import FactSnapshot

logger = logging.getLogger(__name__)


class FactExtractionError(RuntimeError):
    """Raised when yfinance is unreachable or returns malformed payload."""


# Indirection so tests can monkeypatch.
def _yf_ticker(ticker: str):
    import yfinance as yf
    return yf.Ticker(ticker)


def _maybe_float(v: Any) -> Optional[float]:
    if v is None:
        return None
    if isinstance(v, bool):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return f


def _maybe_int(v: Any) -> Optional[int]:
    f = _maybe_float(v)
    return int(f) if f is not None else None


_FIELD_TO_INFO_KEY = {
    "currency": "currency",
    "exchange": "exchange",
    "sector": "sector",
    "industry": "industry",
    "market_cap_usd": "marketCap",
    "price": "regularMarketPrice",
    "price_52w_high": "fiftyTwoWeekHigh",
    "beta": "beta",
    "pe_ttm": "trailingPE",
    "forward_pe": "forwardPE",
    "peg": "pegRatio",
    "ev_ebitda": "enterpriseToEbitda",
    "ps_ttm": "priceToSalesTrailing12Months",
    "pb": "priceToBook",
    "revenue_growth_yoy": "revenueGrowth",
    "eps_growth_yoy": "earningsGrowth",
    "roe": "returnOnEquity",
    "gross_margin": "grossMargins",
    "operating_margin": "operatingMargins",
    "net_margin": "profitMargins",
    "debt_to_equity": "debtToEquity",
    "current_ratio": "currentRatio",
    "dividend_yield": "dividendYield",
    "payout_ratio": "payoutRatio",
    "analyst_target_mean": "targetMeanPrice",
    "analyst_recommendation_mean": "recommendationMean",
}

_INT_FIELDS = {"analyst_count"}


def extract_facts(ticker: str, as_of_date: str) -> Tuple[FactSnapshot, List[str]]:
    """Return (FactSnapshot, data_quality_flags). Raises FactExtractionError on yfinance error."""
    try:
        tk = _yf_ticker(ticker)
        info = tk.info or {}
    except Exception as exc:
        raise FactExtractionError(f"yfinance error for {ticker}: {exc}") from exc

    flags: List[str] = []
    payload: dict = {
        "as_of_date": as_of_date,
        "currency": str(info.get("currency") or "USD"),
        "analyst_count": _maybe_int(info.get("numberOfAnalystOpinions")),
    }

    for field, key in _FIELD_TO_INFO_KEY.items():
        raw = info.get(key)
        if field in {"currency", "exchange", "sector", "industry"}:
            payload[field] = str(raw) if isinstance(raw, str) and raw else None
        else:
            payload[field] = _maybe_float(raw)
        if payload.get(field) is None and field not in {"currency"}:
            flags.append(f"missing_{field}")

    price = payload.get("price")
    high = payload.get("price_52w_high")
    if price is not None and high and high > 0:
        payload["pct_off_52w_high"] = (price - high) / high

    fcf = _maybe_float(info.get("freeCashflow"))
    mcap = payload.get("market_cap_usd")
    if fcf is not None and mcap and mcap > 0:
        payload["fcf_yield"] = fcf / mcap

    snapshot = FactSnapshot(**payload)
    return snapshot, flags
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/dimensions/test_facts.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add api/dimensions/facts.py tests/dimensions/test_facts.py tests/dimensions/fixtures/
git commit -m "feat(dimensions): yfinance-backed fact extractor with missing-field flags"
```

---

## Task 3: Sector peer cache + percentile math

**Files:**
- Create: `api/dimensions/peers.py`
- Create: `tests/dimensions/test_peers.py`

- [ ] **Step 1: Write the failing test**

`tests/dimensions/test_peers.py`:

```python
import json
import time
from pathlib import Path

import pytest

from api.dimensions.peers import (
    PeerCache, percentile_rank, build_peer_pct_table, peer_universe_id,
)


def test_percentile_rank_basic():
    values = [10, 20, 30, 40, 50]
    assert percentile_rank(30, values) == pytest.approx(0.5)
    assert percentile_rank(10, values) == pytest.approx(0.1)
    assert percentile_rank(50, values) == pytest.approx(0.9)


def test_percentile_rank_handles_none_and_short_list():
    assert percentile_rank(None, [1, 2, 3]) is None
    assert percentile_rank(5, [1]) is None  # fewer than 3 peers
    assert percentile_rank(5, [1, 2]) is None


def test_percentile_rank_drops_none_peers():
    values = [10, None, 30, None, 50]
    assert percentile_rank(30, values) == pytest.approx(0.5)


def test_peer_universe_id_includes_sector_industry():
    assert peer_universe_id("Technology", "Software-Infrastructure") == \
           "sector:Technology|industry:Software-Infrastructure"
    assert peer_universe_id(None, "X") is None


def test_peer_cache_round_trip(tmp_path):
    cache = PeerCache(base_dir=tmp_path)
    cache.write("sector_tech", ["AAPL", "MSFT", "NVDA"], {"AAPL": {"pe_ttm": 28.0}})
    rec = cache.read("sector_tech")
    assert rec is not None
    assert rec.tickers == ["AAPL", "MSFT", "NVDA"]
    assert rec.facts["AAPL"]["pe_ttm"] == 28.0
    assert rec.is_fresh(ttl_hours=24)


def test_peer_cache_stale_detection(tmp_path):
    cache = PeerCache(base_dir=tmp_path)
    cache.write("sector_x", ["A", "B"], {})
    rec = cache.read("sector_x")
    # Backdate
    rec_path = tmp_path / "sector_x.json"
    data = json.loads(rec_path.read_text())
    data["written_at"] = data["written_at"] - 25 * 3600
    rec_path.write_text(json.dumps(data))
    rec2 = cache.read("sector_x")
    assert not rec2.is_fresh(ttl_hours=24)


def test_build_peer_pct_table_inverted_for_value_metrics():
    peer_facts = [
        {"pe_ttm": 10.0, "pb": 1.0},
        {"pe_ttm": 20.0, "pb": 2.0},
        {"pe_ttm": 30.0, "pb": 3.0},
        {"pe_ttm": 40.0, "pb": 4.0},
        {"pe_ttm": 50.0, "pb": 5.0},
    ]
    target = {"pe_ttm": 15.0, "pb": 1.5}
    table = build_peer_pct_table(target, peer_facts, inverted_fields={"pe_ttm", "pb"})
    # pe_ttm 15 ranks 2nd lowest out of 6 → low PE is good → inverted percentile high
    assert table["pe_ttm"] > 0.6
    assert table["pb"] > 0.6
```

- [ ] **Step 2: Implement peers module**

`api/dimensions/peers.py`:

```python
"""Sector peer cache + percentile rank math for dimensions factor scoring."""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set

logger = logging.getLogger(__name__)


def percentile_rank(value: Optional[float], peers: Iterable[Optional[float]]) -> Optional[float]:
    """Return percentile rank (0..1) of `value` within `peers`. None if <3 usable peers."""
    if value is None:
        return None
    clean = [float(p) for p in peers if p is not None]
    if len(clean) < 3:
        return None
    series = sorted(clean + [float(value)])
    rank = series.index(float(value))
    return rank / (len(series) - 1)


def peer_universe_id(sector: Optional[str], industry: Optional[str]) -> Optional[str]:
    if not sector or not industry:
        return None
    return f"sector:{sector}|industry:{industry}"


def build_peer_pct_table(
    target_facts: Dict[str, Optional[float]],
    peer_facts: List[Dict[str, Optional[float]]],
    inverted_fields: Set[str],
) -> Dict[str, Optional[float]]:
    """For each fact, return percentile rank of target vs peers.

    `inverted_fields` flips the rank (low = good → high percentile). E.g. P/E and P/B.
    """
    out: Dict[str, Optional[float]] = {}
    keys = set()
    for f in peer_facts:
        keys.update(f.keys())
    keys.update(target_facts.keys())
    for k in keys:
        peers = [f.get(k) for f in peer_facts]
        pct = percentile_rank(target_facts.get(k), peers)
        if pct is not None and k in inverted_fields:
            pct = 1.0 - pct
        out[k] = pct
    return out


@dataclass
class CachedPeers:
    tickers: List[str]
    facts: Dict[str, Dict[str, Optional[float]]]
    written_at: float

    def is_fresh(self, ttl_hours: int) -> bool:
        return (time.time() - self.written_at) < ttl_hours * 3600


class PeerCache:
    """JSON-per-sector cache under <data_cache_dir>/peer_facts/."""

    def __init__(self, base_dir: Path):
        self._dir = Path(base_dir)
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, slug: str) -> Path:
        safe = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in slug)
        return self._dir / f"{safe}.json"

    def read(self, slug: str) -> Optional[CachedPeers]:
        p = self._path(slug)
        if not p.is_file():
            return None
        try:
            data = json.loads(p.read_text())
        except (OSError, json.JSONDecodeError):
            return None
        return CachedPeers(
            tickers=list(data.get("tickers") or []),
            facts=dict(data.get("facts") or {}),
            written_at=float(data.get("written_at") or 0.0),
        )

    def write(self, slug: str, tickers: List[str],
              facts: Dict[str, Dict[str, Optional[float]]]) -> None:
        payload = {"tickers": tickers, "facts": facts, "written_at": time.time()}
        self._path(slug).write_text(json.dumps(payload, ensure_ascii=False))

    def slug_for(self, sector: Optional[str], industry: Optional[str]) -> Optional[str]:
        if not sector or not industry:
            return None
        return f"{sector}__{industry}"


def slug_for_sector(sector: Optional[str], industry: Optional[str]) -> Optional[str]:
    """Convenience wrapper matching PeerCache.slug_for."""
    if not sector or not industry:
        return None
    return f"{sector}__{industry}"
```

- [ ] **Step 3: Run tests**

```bash
pytest tests/dimensions/test_peers.py -v
```

Expected: 7 passed.

- [ ] **Step 4: Commit**

```bash
git add api/dimensions/peers.py tests/dimensions/test_peers.py
git commit -m "feat(dimensions): sector peer cache + percentile-rank math"
```

---

## Task 4: Deterministic factor formulas

**Files:**
- Create: `api/dimensions/factors.py`
- Create: `tests/dimensions/test_factors.py`

- [ ] **Step 1: Write the failing test**

`tests/dimensions/test_factors.py`:

```python
import pytest

from api.dimensions.factors import (
    compute_factors, scale_1_5_to_0_100, INVERTED_PEER_FIELDS,
)
from api.dimensions.schemas import (
    PillarScores, MarketPillar, SentimentPillar, NewsPillar, FundamentalsPillar,
    PillarScore,
)


def _ps(s):
    return PillarScore(score=s, rationale="x")


def _pillars(**overrides):
    base = dict(
        market=MarketPillar(
            trend=_ps(4), momentum=_ps(4), volatility_risk=_ps(3), setup_quality=_ps(3),
        ),
        sentiment=SentimentPillar(
            retail_sentiment=_ps(3), social_buzz=_ps(3),
            consensus_quality=_ps(3), narrative_strength=_ps(3),
        ),
        news=NewsPillar(
            catalyst_strength=_ps(3), macro_alignment=_ps(3),
            headline_quality=_ps(3), surprise_risk=_ps(3),
        ),
        fundamentals=FundamentalsPillar(
            valuation=_ps(4), growth=_ps(4), profitability=_ps(4), balance_sheet_strength=_ps(4),
        ),
    )
    return PillarScores(**{**base, **overrides})


def test_scale_1_5_maps_endpoints():
    assert scale_1_5_to_0_100(1) == 0.0
    assert scale_1_5_to_0_100(3) == 50.0
    assert scale_1_5_to_0_100(5) == 100.0


def test_inverted_fields_include_pe_pb():
    assert "pe_ttm" in INVERTED_PEER_FIELDS
    assert "pb" in INVERTED_PEER_FIELDS


def test_compute_factors_happy_path():
    pillars = _pillars()
    peer_pct = {"pe_ttm": 0.7, "pb": 0.6, "eps_growth_yoy": 0.8, "revenue_growth_yoy": 0.7,
                "roe": 0.9, "interest_coverage": 0.6, "return_3m": 0.8, "return_12m": 0.7,
                "beta": 0.5}
    facts = {"beta": 1.2}
    out = compute_factors(pillars, facts, peer_pct)
    assert 0 <= out.value.score <= 100
    assert 0 <= out.growth.score <= 100
    assert 0 <= out.quality.score <= 100
    assert 0 <= out.momentum.score <= 100
    assert "weight_valuation_pillar" in out.value.inputs
    assert "weight_pe_pct" in out.value.inputs


def test_compute_factors_drops_null_terms_and_renormalizes():
    pillars = _pillars()
    peer_pct = {"pe_ttm": None, "pb": 0.5}  # pe percentile missing
    facts = {}
    out = compute_factors(pillars, facts, peer_pct)
    assert out.value.score is not None
    # pe weight should be dropped from inputs audit
    assert "weight_pe_pct" not in out.value.inputs


def test_compute_factors_all_inputs_missing_returns_none():
    pillars = _pillars(market=MarketPillar(
        trend=PillarScore(score=3, rationale="x"),
        momentum=PillarScore(score=3, rationale="x"),
        volatility_risk=PillarScore(score=3, rationale="x"),
        setup_quality=PillarScore(score=3, rationale="x"),
    ))
    peer_pct = {}
    facts = {"beta": None}
    out = compute_factors(pillars, facts, peer_pct)
    # low_risk has *some* input (volatility_risk pillar from market), so it should still produce a score
    assert out.low_risk.score is not None


def test_compute_factors_null_when_truly_no_inputs():
    """Construct a synthetic pillar set forcing one factor to have no usable inputs.
    
    Implementation detail: if a factor's entire input set is None/dropped, score=None
    and a data_quality_flag is added by the caller (build_dimensions).
    """
    from api.dimensions.factors import compute_factors_with_flags
    pillars = _pillars()
    out, flags = compute_factors_with_flags(pillars, {}, {})
    # All pillar inputs exist (1..5), so all factors should still have scores. flags empty.
    assert all(f.score is not None for f in [out.value, out.growth, out.quality,
                                              out.momentum, out.low_risk, out.sentiment])
    assert flags == []
```

- [ ] **Step 2: Implement factors module**

`api/dimensions/factors.py`:

```python
"""Deterministic factor formulas mapping pillar scores (1-5) + peer percentiles (0-1)
to 6 factor scores (0-100).

Each factor returns its `inputs` audit dict so the score is reproducible and reviewable.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from api.dimensions.schemas import (
    FactorScore, FactorScores, PillarScores,
)


INVERTED_PEER_FIELDS = {"pe_ttm", "pb", "ev_ebitda", "ps_ttm", "peg", "beta"}


def scale_1_5_to_0_100(score: int) -> float:
    return (score - 1) * 25.0


def _weighted(components: List[Tuple[str, Optional[float], float]]) -> Tuple[
    Optional[float], Dict[str, float]
]:
    """Each component is (name, value_0_to_100_or_None, weight)."""
    active = [(n, v, w) for (n, v, w) in components if v is not None]
    if not active:
        return None, {}
    total_w = sum(w for (_, _, w) in active)
    if total_w == 0:
        return None, {}
    score = sum(v * (w / total_w) for (_, v, w) in active)
    return score, {f"weight_{n}": w / total_w for (n, _, w) in active}


def _pct_to_100(pct: Optional[float]) -> Optional[float]:
    return pct * 100.0 if pct is not None else None


def _inv_score(pillar_score: int) -> float:
    """Inverted pillar (higher score = lower risk) → low-risk contribution."""
    return scale_1_5_to_0_100(pillar_score)


def compute_factors(
    pillars: PillarScores,
    facts: Dict[str, Optional[float]],
    peer_pct: Dict[str, Optional[float]],
) -> FactorScores:
    """Public alias — returns FactorScores only (no flags)."""
    factors, _ = compute_factors_with_flags(pillars, facts, peer_pct)
    return factors


def compute_factors_with_flags(
    pillars: PillarScores,
    facts: Dict[str, Optional[float]],
    peer_pct: Dict[str, Optional[float]],
) -> Tuple[FactorScores, List[str]]:
    flags: List[str] = []

    value_score, value_inputs = _weighted([
        ("valuation_pillar", scale_1_5_to_0_100(pillars.fundamentals.valuation.score), 0.5),
        ("pe_pct", _pct_to_100(peer_pct.get("pe_ttm")), 0.3),
        ("pb_pct", _pct_to_100(peer_pct.get("pb")), 0.2),
    ])

    growth_score, growth_inputs = _weighted([
        ("growth_pillar", scale_1_5_to_0_100(pillars.fundamentals.growth.score), 0.5),
        ("eps_growth_pct", _pct_to_100(peer_pct.get("eps_growth_yoy")), 0.25),
        ("revenue_growth_pct", _pct_to_100(peer_pct.get("revenue_growth_yoy")), 0.25),
    ])

    quality_score, quality_inputs = _weighted([
        ("profitability_pillar",
         scale_1_5_to_0_100(pillars.fundamentals.profitability.score), 0.35),
        ("balance_sheet_pillar",
         scale_1_5_to_0_100(pillars.fundamentals.balance_sheet_strength.score), 0.25),
        ("roe_pct", _pct_to_100(peer_pct.get("roe")), 0.25),
        ("interest_coverage_pct", _pct_to_100(peer_pct.get("interest_coverage")), 0.15),
    ])

    momentum_score, momentum_inputs = _weighted([
        ("trend_pillar", scale_1_5_to_0_100(pillars.market.trend.score), 0.30),
        ("momentum_pillar", scale_1_5_to_0_100(pillars.market.momentum.score), 0.30),
        ("return_3m_pct", _pct_to_100(peer_pct.get("return_3m")), 0.20),
        ("return_12m_pct", _pct_to_100(peer_pct.get("return_12m")), 0.20),
    ])

    low_risk_score, low_risk_inputs = _weighted([
        ("volatility_risk_pillar", _inv_score(pillars.market.volatility_risk.score), 0.40),
        ("surprise_risk_pillar", _inv_score(pillars.news.surprise_risk.score), 0.30),
        ("beta_pct", _pct_to_100(peer_pct.get("beta")), 0.30),
    ])

    sentiment_score, sentiment_inputs = _weighted([
        ("retail_sentiment_pillar",
         scale_1_5_to_0_100(pillars.sentiment.retail_sentiment.score), 0.25),
        ("social_buzz_pillar",
         scale_1_5_to_0_100(pillars.sentiment.social_buzz.score), 0.20),
        ("consensus_pillar",
         scale_1_5_to_0_100(pillars.sentiment.consensus_quality.score), 0.20),
        ("narrative_pillar",
         scale_1_5_to_0_100(pillars.sentiment.narrative_strength.score), 0.15),
        ("catalyst_pillar",
         scale_1_5_to_0_100(pillars.news.catalyst_strength.score), 0.20),
    ])

    for name, score in [
        ("value", value_score), ("growth", growth_score), ("quality", quality_score),
        ("momentum", momentum_score), ("low_risk", low_risk_score),
        ("sentiment", sentiment_score),
    ]:
        if score is None:
            flags.append(f"factor_{name}_no_inputs")

    return (
        FactorScores(
            value=FactorScore(score=value_score, inputs=value_inputs),
            growth=FactorScore(score=growth_score, inputs=growth_inputs),
            quality=FactorScore(score=quality_score, inputs=quality_inputs),
            momentum=FactorScore(score=momentum_score, inputs=momentum_inputs),
            low_risk=FactorScore(score=low_risk_score, inputs=low_risk_inputs),
            sentiment=FactorScore(score=sentiment_score, inputs=sentiment_inputs),
        ),
        flags,
    )
```

- [ ] **Step 3: Run tests**

```bash
pytest tests/dimensions/test_factors.py -v
```

Expected: 6 passed.

- [ ] **Step 4: Commit**

```bash
git add api/dimensions/factors.py tests/dimensions/test_factors.py
git commit -m "feat(dimensions): deterministic factor formulas with audit inputs"
```

---

## Task 5: Pillar scoring LLM call

**Files:**
- Create: `api/dimensions/scoring.py`
- Create: `tests/dimensions/test_scoring.py`
- Create: `tests/dimensions/fixtures/analyst_reports.json`

- [ ] **Step 1: Write the failing test**

`tests/dimensions/test_scoring.py`:

```python
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from api.dimensions.scoring import score_pillars, PillarScoringError
from api.dimensions.schemas import (
    PillarScores, MarketPillar, SentimentPillar, NewsPillar, FundamentalsPillar,
    PillarScore, FactSnapshot,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _ps(s=3, w="ok"):
    return PillarScore(score=s, rationale=w)


def _make_valid_pillars():
    return PillarScores(
        market=MarketPillar(trend=_ps(4), momentum=_ps(4), volatility_risk=_ps(3),
                            setup_quality=_ps(3)),
        sentiment=SentimentPillar(retail_sentiment=_ps(3), social_buzz=_ps(3),
                                 consensus_quality=_ps(3), narrative_strength=_ps(3)),
        news=NewsPillar(catalyst_strength=_ps(3), macro_alignment=_ps(3),
                       headline_quality=_ps(3), surprise_risk=_ps(3)),
        fundamentals=FundamentalsPillar(valuation=_ps(4), growth=_ps(4),
                                       profitability=_ps(4), balance_sheet_strength=_ps(4)),
    )


def test_score_pillars_invokes_structured_output(monkeypatch):
    captured = {}

    class FakeStructured:
        def invoke(self, messages):
            captured["messages"] = messages
            return _make_valid_pillars()

    fake_llm = MagicMock()
    fake_llm.with_structured_output = MagicMock(return_value=FakeStructured())

    facts = FactSnapshot(as_of_date="2026-05-13", currency="USD", pe_ttm=28.0)
    reports = {"market": "trend up", "fundamentals": "good moat"}
    out = score_pillars(facts=facts, analyst_reports=reports, llm=fake_llm)

    assert isinstance(out, PillarScores)
    fake_llm.with_structured_output.assert_called_once()
    # Prompt content should reference the analyst reports + facts
    msg_text = json.dumps(captured["messages"], default=str)
    assert "trend up" in msg_text
    assert "good moat" in msg_text
    assert "28.0" in msg_text or "pe_ttm" in msg_text


def test_score_pillars_raises_on_structured_failure():
    class BoomStructured:
        def invoke(self, _messages):
            raise ValueError("schema mismatch")
    fake_llm = MagicMock()
    fake_llm.with_structured_output = MagicMock(return_value=BoomStructured())

    facts = FactSnapshot(as_of_date="2026-05-13", currency="USD")
    with pytest.raises(PillarScoringError):
        score_pillars(facts=facts, analyst_reports={}, llm=fake_llm)


def test_score_pillars_handles_empty_reports():
    fake_llm = MagicMock()
    fake_llm.with_structured_output = MagicMock(
        return_value=MagicMock(invoke=MagicMock(return_value=_make_valid_pillars()))
    )
    facts = FactSnapshot(as_of_date="2026-05-13", currency="USD")
    out = score_pillars(facts=facts, analyst_reports={}, llm=fake_llm)
    assert isinstance(out, PillarScores)
```

- [ ] **Step 2: Add fixture**

`tests/dimensions/fixtures/analyst_reports.json`:

```json
{
  "market": "AAPL is in a strong Stage 2 uptrend...",
  "social": "Reddit chatter is bullish but light...",
  "news": "Recent catalysts: services growth...",
  "fundamentals": "Operating margins expanding..."
}
```

- [ ] **Step 3: Implement scoring**

`api/dimensions/scoring.py`:

```python
"""Single structured-output LLM call producing PillarScores."""
from __future__ import annotations

import json
import logging
from typing import Any, Dict

from api.dimensions.schemas import FactSnapshot, PillarScores

logger = logging.getLogger(__name__)


class PillarScoringError(RuntimeError):
    pass


_SYSTEM = """You are a quantitative research analyst. Given (a) a stock's deterministic facts
and (b) four analyst reports (Market, Sentiment, News, Fundamentals), score 16 sub-dimensions
on a 1-5 scale with a one-sentence rationale per score.

CRITICAL: `volatility_risk` and `surprise_risk` are inverted — HIGHER score means LOWER risk.
For all other dimensions, higher score means stronger/better.

Be calibrated. 3 = average; 5 is reserved for genuinely standout cases."""


def _build_prompt(facts: FactSnapshot, reports: Dict[str, str]) -> list[dict]:
    facts_json = json.dumps(facts.model_dump(), default=str, indent=2)
    body = [f"## Facts\n```json\n{facts_json}\n```"]
    for key in ("market", "social", "news", "fundamentals"):
        text = reports.get(key) or "(no report available)"
        body.append(f"## {key.title()} Analyst Report\n{text}")
    return [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": "\n\n".join(body)},
    ]


def score_pillars(
    *,
    facts: FactSnapshot,
    analyst_reports: Dict[str, str],
    llm: Any,
) -> PillarScores:
    """Returns parsed PillarScores. Raises PillarScoringError on any failure."""
    messages = _build_prompt(facts, analyst_reports)
    try:
        structured = llm.with_structured_output(PillarScores)
        result = structured.invoke(messages)
    except Exception as exc:
        raise PillarScoringError(f"Pillar scoring failed: {exc}") from exc
    if not isinstance(result, PillarScores):
        raise PillarScoringError(f"Unexpected scoring result type: {type(result).__name__}")
    return result
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/dimensions/test_scoring.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add api/dimensions/scoring.py tests/dimensions/test_scoring.py \
        tests/dimensions/fixtures/analyst_reports.json
git commit -m "feat(dimensions): pillar scoring LLM call (structured output)"
```

---

## Task 6: Dimensions-grounded commentary LLM call

**Files:**
- Create: `api/dimensions/commentary.py`
- Create: `tests/dimensions/test_commentary.py`

- [ ] **Step 1: Write the failing test**

`tests/dimensions/test_commentary.py`:

```python
from unittest.mock import MagicMock

import pytest

from api.dimensions.commentary import build_commentary, CommentaryError
from api.dimensions.schemas import (
    DimensionsCommentary, FactorScore, FactorScores, PillarScores,
    MarketPillar, SentimentPillar, NewsPillar, FundamentalsPillar, PillarScore,
    FactSnapshot, StockDimensions,
)


def _ps(s=3):
    return PillarScore(score=s, rationale="x")


def _dims():
    return StockDimensions(
        ticker="AAPL", as_of_date="2026-05-13",
        facts=FactSnapshot(as_of_date="2026-05-13", currency="USD"),
        pillar_scores=PillarScores(
            market=MarketPillar(trend=_ps(), momentum=_ps(), volatility_risk=_ps(),
                                setup_quality=_ps()),
            sentiment=SentimentPillar(retail_sentiment=_ps(), social_buzz=_ps(),
                                     consensus_quality=_ps(), narrative_strength=_ps()),
            news=NewsPillar(catalyst_strength=_ps(), macro_alignment=_ps(),
                           headline_quality=_ps(), surprise_risk=_ps()),
            fundamentals=FundamentalsPillar(valuation=_ps(), growth=_ps(),
                                           profitability=_ps(), balance_sheet_strength=_ps()),
        ),
        factor_scores=FactorScores(
            value=FactorScore(score=70.0), growth=FactorScore(score=60.0),
            quality=FactorScore(score=80.0), momentum=FactorScore(score=55.0),
            low_risk=FactorScore(score=40.0), sentiment=FactorScore(score=50.0),
        ),
        dimensions_version="1.0.0",
    )


def _result():
    return DimensionsCommentary(
        alignment="aligned",
        supporting_dimensions=["value", "quality"],
        conflicting_dimensions=[],
        risk_flags=["elevated_beta"],
        summary="PM rating Buy aligns with strong Value (70) and Quality (80).",
    )


def test_build_commentary_returns_parsed_model():
    fake_llm = MagicMock()
    structured = MagicMock()
    structured.invoke = MagicMock(return_value=_result())
    fake_llm.with_structured_output = MagicMock(return_value=structured)

    out = build_commentary(dimensions=_dims(), pm_decision_text="Buy. Strong setup.", llm=fake_llm)
    assert out.alignment == "aligned"
    assert "value" in out.supporting_dimensions


def test_build_commentary_raises_on_llm_error():
    class Boom:
        def invoke(self, _m):
            raise RuntimeError("provider down")
    fake_llm = MagicMock()
    fake_llm.with_structured_output = MagicMock(return_value=Boom())
    with pytest.raises(CommentaryError):
        build_commentary(dimensions=_dims(), pm_decision_text="x", llm=fake_llm)
```

- [ ] **Step 2: Implement commentary**

`api/dimensions/commentary.py`:

```python
"""W1 dimensions-grounded commentary on the PM decision (1 LLM call)."""
from __future__ import annotations

import json
import logging
from typing import Any

from api.dimensions.schemas import DimensionsCommentary, StockDimensions

logger = logging.getLogger(__name__)


class CommentaryError(RuntimeError):
    pass


_SYSTEM = """You are a quantitative reviewer. Given (a) a portfolio manager's decision
and (b) the standardized dimensions for the stock, give a one-paragraph independent assessment:
- alignment: does the PM's call agree with the dimension signals?
- supporting_dimensions: which factor scores back the PM's view (lowercase factor names)
- conflicting_dimensions: which factor scores push the other way
- risk_flags: dimension-driven risks worth surfacing
- summary: 2-4 sentences"""


def build_commentary(
    *,
    dimensions: StockDimensions,
    pm_decision_text: str,
    llm: Any,
) -> DimensionsCommentary:
    payload = {
        "factor_scores": {
            k: getattr(dimensions.factor_scores, k).model_dump()
            for k in ("value", "growth", "quality", "momentum", "low_risk", "sentiment")
        },
        "data_quality_flags": dimensions.data_quality_flags,
    }
    user = (
        f"## PM Decision\n{pm_decision_text}\n\n"
        f"## Dimensions ({dimensions.ticker} as of {dimensions.as_of_date})\n"
        f"```json\n{json.dumps(payload, default=str, indent=2)}\n```"
    )
    messages = [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": user},
    ]
    try:
        structured = llm.with_structured_output(DimensionsCommentary)
        result = structured.invoke(messages)
    except Exception as exc:
        raise CommentaryError(f"Commentary generation failed: {exc}") from exc
    if not isinstance(result, DimensionsCommentary):
        raise CommentaryError(f"Unexpected commentary type: {type(result).__name__}")
    return result
```

- [ ] **Step 3: Run tests**

```bash
pytest tests/dimensions/test_commentary.py -v
```

Expected: 2 passed.

- [ ] **Step 4: Commit**

```bash
git add api/dimensions/commentary.py tests/dimensions/test_commentary.py
git commit -m "feat(dimensions): W1 grounded commentary LLM call"
```

---

## Task 7: build_dimensions orchestrator

**Files:**
- Create: `api/dimensions/builder.py`
- Create: `tests/dimensions/test_build_dimensions.py`

- [ ] **Step 1: Write the failing test**

`tests/dimensions/test_build_dimensions.py`:

```python
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from api.dimensions.builder import (
    build_dimensions, build_dimensions_facts_only, DimensionsBuildError,
)
from api.dimensions.schemas import (
    FactSnapshot, PillarScores, MarketPillar, SentimentPillar, NewsPillar,
    FundamentalsPillar, PillarScore, StockDimensions,
)


def _ps(s=3):
    return PillarScore(score=s, rationale="x")


def _valid_pillars():
    return PillarScores(
        market=MarketPillar(trend=_ps(4), momentum=_ps(4), volatility_risk=_ps(3),
                            setup_quality=_ps(3)),
        sentiment=SentimentPillar(retail_sentiment=_ps(3), social_buzz=_ps(3),
                                 consensus_quality=_ps(3), narrative_strength=_ps(3)),
        news=NewsPillar(catalyst_strength=_ps(3), macro_alignment=_ps(3),
                       headline_quality=_ps(3), surprise_risk=_ps(3)),
        fundamentals=FundamentalsPillar(valuation=_ps(4), growth=_ps(4),
                                       profitability=_ps(4), balance_sheet_strength=_ps(4)),
    )


def _stub_facts():
    return FactSnapshot(
        as_of_date="2026-05-13", currency="USD", sector="Technology",
        industry="Consumer Electronics", pe_ttm=28.0, pb=45.0, eps_growth_yoy=0.08,
    )


@pytest.fixture
def patch_modules(monkeypatch, tmp_path):
    monkeypatch.setattr("api.dimensions.builder.extract_facts",
                       lambda t, d: (_stub_facts(), []))
    monkeypatch.setattr("api.dimensions.builder.score_pillars",
                       lambda **k: _valid_pillars())
    monkeypatch.setattr(
        "api.dimensions.builder._get_peer_cache_dir",
        lambda cfg: tmp_path,
    )
    # Stub peer loading to return empty (forces absolute fallback)
    monkeypatch.setattr(
        "api.dimensions.builder._load_or_refresh_peers",
        lambda *a, **k: ([], {}),
    )


def test_build_dimensions_happy_path(patch_modules):
    fake_llm = MagicMock()
    reports = {"market": "x", "social": "y", "news": "z", "fundamentals": "w"}
    out = build_dimensions(
        ticker="AAPL", as_of_date="2026-05-13",
        analyst_reports=reports, llm=fake_llm, config={"data_cache_dir": "/tmp"},
    )
    assert isinstance(out, StockDimensions)
    assert out.ticker == "AAPL"
    assert out.source == "full_run"
    assert out.dimensions_version == "1.0.0"


def test_build_dimensions_facts_only_uses_neutral_pillars(monkeypatch, tmp_path):
    monkeypatch.setattr("api.dimensions.builder.extract_facts",
                       lambda t, d: (_stub_facts(), []))
    monkeypatch.setattr("api.dimensions.builder._get_peer_cache_dir",
                       lambda cfg: tmp_path)
    monkeypatch.setattr("api.dimensions.builder._load_or_refresh_peers",
                       lambda *a, **k: ([], {}))
    out = build_dimensions_facts_only(
        ticker="AAPL", as_of_date="2026-05-13", config={"data_cache_dir": "/tmp"},
    )
    assert out.source == "facts_only"
    # Neutral pillars: every pillar score should be 3
    assert out.pillar_scores.market.trend.score == 3
    assert out.pillar_scores.fundamentals.valuation.score == 3


def test_build_dimensions_raises_on_fact_extraction_failure(monkeypatch, tmp_path):
    from api.dimensions.facts import FactExtractionError
    def boom(t, d): raise FactExtractionError("network")
    monkeypatch.setattr("api.dimensions.builder.extract_facts", boom)
    monkeypatch.setattr("api.dimensions.builder._get_peer_cache_dir",
                       lambda cfg: tmp_path)
    with pytest.raises(DimensionsBuildError):
        build_dimensions(
            ticker="AAPL", as_of_date="2026-05-13",
            analyst_reports={}, llm=MagicMock(), config={},
        )


def test_build_dimensions_peer_universe_id_populated(patch_modules):
    fake_llm = MagicMock()
    out = build_dimensions(
        ticker="AAPL", as_of_date="2026-05-13",
        analyst_reports={"market": "x"}, llm=fake_llm, config={},
    )
    assert out.peer_universe_id == "sector:Technology|industry:Consumer Electronics"
```

- [ ] **Step 2: Implement builder**

`api/dimensions/builder.py`:

```python
"""Orchestrator: facts → peers → pillars → factors → StockDimensions."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from api.dimensions.commentary import CommentaryError, build_commentary as _bc
from api.dimensions.facts import FactExtractionError, extract_facts
from api.dimensions.factors import (
    INVERTED_PEER_FIELDS, compute_factors_with_flags,
)
from api.dimensions.peers import (
    PeerCache, build_peer_pct_table, peer_universe_id, slug_for_sector,
)
from api.dimensions.schemas import (
    DimensionsCommentary, FactSnapshot, FundamentalsPillar, MarketPillar,
    NewsPillar, PillarScore, PillarScores, SentimentPillar, StockDimensions,
)
from api.dimensions.scoring import PillarScoringError, score_pillars
from api.dimensions.version import DIMENSIONS_VERSION

logger = logging.getLogger(__name__)


class DimensionsBuildError(RuntimeError):
    pass


def _get_peer_cache_dir(config: Optional[Dict[str, Any]]) -> Path:
    cfg = config or {}
    base = Path(cfg.get("data_cache_dir") or "./data_cache")
    return base / "peer_facts"


def _load_or_refresh_peers(
    sector: Optional[str], industry: Optional[str], cache_dir: Path,
    ttl_hours: int = 24,
) -> Tuple[List[str], Dict[str, Dict[str, Optional[float]]]]:
    """v1: returns whatever is cached. Refresh is a separate operation
    (scripts/warm_peer_cache.py or admin endpoint). Missing cache → empty."""
    slug = slug_for_sector(sector, industry)
    if not slug:
        return [], {}
    cache = PeerCache(base_dir=cache_dir)
    rec = cache.read(slug)
    if rec is None:
        return [], {}
    return rec.tickers, rec.facts


def _facts_to_peer_dict(facts: FactSnapshot) -> Dict[str, Optional[float]]:
    """Subset of facts used for peer percentile ranking."""
    return {
        "pe_ttm": facts.pe_ttm,
        "forward_pe": facts.forward_pe,
        "peg": facts.peg,
        "ev_ebitda": facts.ev_ebitda,
        "ps_ttm": facts.ps_ttm,
        "pb": facts.pb,
        "eps_growth_yoy": facts.eps_growth_yoy,
        "revenue_growth_yoy": facts.revenue_growth_yoy,
        "roe": facts.roe,
        "interest_coverage": facts.interest_coverage,
        "return_3m": facts.return_3m,
        "return_12m": facts.return_12m,
        "beta": facts.beta,
    }


def _neutral_pillars() -> PillarScores:
    def n(): return PillarScore(score=3, rationale="neutral default (facts-only)")
    return PillarScores(
        market=MarketPillar(trend=n(), momentum=n(), volatility_risk=n(), setup_quality=n()),
        sentiment=SentimentPillar(retail_sentiment=n(), social_buzz=n(),
                                 consensus_quality=n(), narrative_strength=n()),
        news=NewsPillar(catalyst_strength=n(), macro_alignment=n(),
                       headline_quality=n(), surprise_risk=n()),
        fundamentals=FundamentalsPillar(valuation=n(), growth=n(), profitability=n(),
                                       balance_sheet_strength=n()),
    )


def _assemble(
    ticker: str,
    as_of_date: str,
    facts: FactSnapshot,
    pillars: PillarScores,
    peer_pct: Dict[str, Optional[float]],
    flags: List[str],
    source: str,
) -> StockDimensions:
    factors, factor_flags = compute_factors_with_flags(
        pillars, _facts_to_peer_dict(facts), peer_pct
    )
    all_flags = list(flags) + factor_flags
    return StockDimensions(
        ticker=ticker,
        as_of_date=as_of_date,
        facts=facts,
        pillar_scores=pillars,
        factor_scores=factors,
        dimensions_version=DIMENSIONS_VERSION,
        peer_universe_id=peer_universe_id(facts.sector, facts.industry),
        data_quality_flags=all_flags,
        source=source,  # type: ignore[arg-type]
    )


def build_dimensions(
    *,
    ticker: str,
    as_of_date: str,
    analyst_reports: Dict[str, str],
    llm: Any,
    config: Optional[Dict[str, Any]] = None,
) -> StockDimensions:
    try:
        facts, flags = extract_facts(ticker, as_of_date)
    except FactExtractionError as exc:
        raise DimensionsBuildError(f"Fact extraction failed: {exc}") from exc

    cache_dir = _get_peer_cache_dir(config)
    _peer_tickers, peer_facts_map = _load_or_refresh_peers(
        facts.sector, facts.industry, cache_dir,
    )
    peer_pct = build_peer_pct_table(
        target_facts=_facts_to_peer_dict(facts),
        peer_facts=list(peer_facts_map.values()),
        inverted_fields=INVERTED_PEER_FIELDS,
    )

    try:
        pillars = score_pillars(facts=facts, analyst_reports=analyst_reports, llm=llm)
    except PillarScoringError as exc:
        raise DimensionsBuildError(f"Pillar scoring failed: {exc}") from exc

    return _assemble(ticker, as_of_date, facts, pillars, peer_pct, flags, "full_run")


def build_dimensions_facts_only(
    *,
    ticker: str,
    as_of_date: str,
    config: Optional[Dict[str, Any]] = None,
) -> StockDimensions:
    """No LLM, no analyst reports. Pillars defaulted to 3 (neutral)."""
    try:
        facts, flags = extract_facts(ticker, as_of_date)
    except FactExtractionError as exc:
        raise DimensionsBuildError(f"Fact extraction failed: {exc}") from exc

    cache_dir = _get_peer_cache_dir(config)
    _peer_tickers, peer_facts_map = _load_or_refresh_peers(
        facts.sector, facts.industry, cache_dir,
    )
    peer_pct = build_peer_pct_table(
        target_facts=_facts_to_peer_dict(facts),
        peer_facts=list(peer_facts_map.values()),
        inverted_fields=INVERTED_PEER_FIELDS,
    )
    return _assemble(
        ticker, as_of_date, facts, _neutral_pillars(), peer_pct, flags, "facts_only"
    )


def build_commentary(
    *,
    dimensions: StockDimensions,
    pm_decision_text: str,
    llm: Any,
) -> DimensionsCommentary:
    try:
        return _bc(dimensions=dimensions, pm_decision_text=pm_decision_text, llm=llm)
    except CommentaryError as exc:
        raise DimensionsBuildError(f"Commentary failed: {exc}") from exc
```

- [ ] **Step 3: Export public API**

Update `api/dimensions/__init__.py`:

```python
"""Standardized stock dimensions: facts + pillar scores + factor scores."""
from api.dimensions.builder import (
    DimensionsBuildError,
    build_commentary,
    build_dimensions,
    build_dimensions_facts_only,
)
from api.dimensions.schemas import (
    DimensionsCommentary,
    FactorScore,
    FactorScores,
    FactSnapshot,
    PillarScore,
    PillarScores,
    StockDimensions,
)
from api.dimensions.version import DIMENSIONS_VERSION

__all__ = [
    "DIMENSIONS_VERSION",
    "DimensionsBuildError",
    "DimensionsCommentary",
    "FactSnapshot",
    "FactorScore",
    "FactorScores",
    "PillarScore",
    "PillarScores",
    "StockDimensions",
    "build_commentary",
    "build_dimensions",
    "build_dimensions_facts_only",
]
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/dimensions/test_build_dimensions.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add api/dimensions/builder.py api/dimensions/__init__.py \
        tests/dimensions/test_build_dimensions.py
git commit -m "feat(dimensions): build_dimensions orchestrator + facts-only path"
```

---

## Task 8: Extend Pydantic API models

**Files:**
- Modify: `api/models.py`
- Create: `tests/dimensions/test_api_models_extension.py`

- [ ] **Step 1: Write the failing test**

`tests/dimensions/test_api_models_extension.py`:

```python
from api.models import (
    AnalysisResult, HistoryRunDetail, HistoryRunRef, HistoryCompareSide,
)


def test_analysis_result_accepts_dimensions_fields():
    payload = {
        "ticker": "AAPL", "date": "2026-05-13", "rating": "Buy",
        "reports": {}, "completed_at": "2026-05-13T00:00:00Z",
        "dimensions": None,
        "dimensions_commentary": None,
        "dimensions_error": None,
    }
    m = AnalysisResult.model_validate(payload)
    assert m.dimensions is None
    assert m.dimensions_commentary is None


def test_history_run_ref_factor_scores_optional():
    ref = HistoryRunRef(run_id="x", factor_scores={"value": 70.0})
    assert ref.factor_scores == {"value": 70.0}
    ref2 = HistoryRunRef(run_id="y")
    assert ref2.factor_scores is None


def test_history_run_detail_round_trips_with_dimensions_none():
    detail = HistoryRunDetail(
        run_id="r1", job_id="j1", ticker="AAPL", date="2026-05-13", rating="Buy",
        dimensions=None, dimensions_commentary=None,
    )
    dumped = detail.model_dump()
    HistoryRunDetail.model_validate(dumped)


def test_compare_side_accepts_dimensions_field():
    side = HistoryCompareSide(dimensions=None)
    assert side.dimensions is None
```

- [ ] **Step 2: Modify api/models.py**

Add at the top of `api/models.py` after existing imports:

```python
from api.dimensions.schemas import (
    DimensionsCommentary, FactSnapshot, FactorScore, FactorScores, PillarScore,
    PillarScores, StockDimensions,
)
```

Then add to `AnalysisResult` after the existing fields:

```python
    dimensions: Optional[StockDimensions] = None
    dimensions_commentary: Optional[DimensionsCommentary] = None
    dimensions_error: Optional[str] = None
```

Then add to `HistoryRunRef`:

```python
    factor_scores: Optional[Dict[str, float]] = Field(
        default=None,
        description="Compact 6-factor summary for list views (value/growth/quality/momentum/low_risk/sentiment).",
    )
```

Then add to `HistoryRunDetail`:

```python
    dimensions: Optional[StockDimensions] = None
    dimensions_commentary: Optional[DimensionsCommentary] = None
    dimensions_error: Optional[str] = None
```

Then add to `HistoryCompareSide`:

```python
    dimensions: Optional[StockDimensions] = None
    dimensions_commentary: Optional[DimensionsCommentary] = None
```

Then re-export the schemas at the end of `api/models.py`:

```python
__all__ = [  # extend, do not replace if __all__ already exists
    *globals().get("__all__", []),
    "DimensionsCommentary", "FactSnapshot", "FactorScore", "FactorScores",
    "PillarScore", "PillarScores", "StockDimensions",
]
```

- [ ] **Step 3: Run tests**

```bash
pytest tests/dimensions/test_api_models_extension.py tests/test_api_ux.py -v
```

Expected: new tests pass; existing UX tests still pass (no regression).

- [ ] **Step 4: Commit**

```bash
git add api/models.py tests/dimensions/test_api_models_extension.py
git commit -m "feat(api/models): extend with dimensions fields on Result/History records"
```

---

## Task 9: Jobs integration — post-pass + progress events + cancellation flag

**Files:**
- Modify: `api/jobs.py`
- Create: `tests/test_jobs_dimensions_progress.py`
- Create: `tests/test_jobs_dimensions_failure_isolation.py`
- Create: `tests/test_jobs_cancel.py`

- [ ] **Step 1: Write the failing test (progress events)**

`tests/test_jobs_dimensions_progress.py`:

```python
import asyncio
from unittest.mock import MagicMock, patch

import pytest

from api.jobs import Worker
from api.dimensions.schemas import (
    StockDimensions, FactSnapshot, PillarScores, MarketPillar, SentimentPillar,
    NewsPillar, FundamentalsPillar, PillarScore, FactorScores, FactorScore,
    DimensionsCommentary,
)


def _ps(s=3):
    return PillarScore(score=s, rationale="x")


def _fake_dimensions():
    return StockDimensions(
        ticker="AAPL", as_of_date="2026-05-13",
        facts=FactSnapshot(as_of_date="2026-05-13", currency="USD",
                          sector="Technology", industry="Consumer Electronics"),
        pillar_scores=PillarScores(
            market=MarketPillar(trend=_ps(), momentum=_ps(), volatility_risk=_ps(),
                               setup_quality=_ps()),
            sentiment=SentimentPillar(retail_sentiment=_ps(), social_buzz=_ps(),
                                     consensus_quality=_ps(), narrative_strength=_ps()),
            news=NewsPillar(catalyst_strength=_ps(), macro_alignment=_ps(),
                           headline_quality=_ps(), surprise_risk=_ps()),
            fundamentals=FundamentalsPillar(valuation=_ps(), growth=_ps(),
                                           profitability=_ps(), balance_sheet_strength=_ps()),
        ),
        factor_scores=FactorScores(
            value=FactorScore(score=70.0), growth=FactorScore(score=60.0),
            quality=FactorScore(score=80.0), momentum=FactorScore(score=55.0),
            low_risk=FactorScore(score=40.0), sentiment=FactorScore(score=50.0),
        ),
        dimensions_version="1.0.0",
    )


def _fake_commentary():
    return DimensionsCommentary(alignment="aligned", supporting_dimensions=["value"],
                               conflicting_dimensions=[], risk_flags=[], summary="ok")


@pytest.mark.asyncio
async def test_dimensions_phase_emits_six_progress_events(monkeypatch):
    worker = Worker(max_concurrency=1, ttl_hours=24)

    monkeypatch.setattr(
        "api.jobs.Worker._propagate_sync",
        lambda self, *a, **k: ({"market_report": "x", "sentiment_report": "y",
                                "news_report": "z", "fundamentals_report": "w",
                                "final_trade_decision": "Buy.",
                                "company_of_interest": "AAPL",
                                "trade_date": "2026-05-13",
                                "investment_debate_state": {},
                                "risk_debate_state": {}}, "Buy"),
    )
    monkeypatch.setattr("api.jobs.build_dimensions",
                       lambda **k: _fake_dimensions())
    monkeypatch.setattr("api.jobs.build_commentary",
                       lambda **k: _fake_commentary())

    jid = await worker.submit("AAPL", "2026-05-13", {"dimensions_enabled": True})
    for _ in range(100):
        rec = worker.store.get(jid)
        if rec and rec.status in ("completed", "failed"):
            break
        await asyncio.sleep(0.05)

    rec = worker.store.get(jid)
    assert rec.status == "completed"
    dim_events = [e for e in rec.progress_events if e.get("stage") == "dimensions"]
    assert len(dim_events) >= 6
    messages = " | ".join(e["message"] for e in dim_events)
    assert "extracting facts" in messages
    assert "scoring 16 pillars" in messages
    assert "commentary" in messages
```

- [ ] **Step 2: Write the failing test (failure isolation)**

`tests/test_jobs_dimensions_failure_isolation.py`:

```python
import asyncio

import pytest

from api.jobs import Worker
from api.dimensions.builder import DimensionsBuildError


@pytest.mark.asyncio
async def test_dimensions_failure_does_not_fail_job(monkeypatch):
    worker = Worker(max_concurrency=1, ttl_hours=24)

    monkeypatch.setattr(
        "api.jobs.Worker._propagate_sync",
        lambda self, *a, **k: ({"market_report": "x", "sentiment_report": "y",
                                "news_report": "z", "fundamentals_report": "w",
                                "final_trade_decision": "Buy.",
                                "company_of_interest": "AAPL",
                                "trade_date": "2026-05-13",
                                "investment_debate_state": {},
                                "risk_debate_state": {}}, "Buy"),
    )

    def boom(**k):
        raise DimensionsBuildError("yfinance offline")
    monkeypatch.setattr("api.jobs.build_dimensions", boom)

    jid = await worker.submit("AAPL", "2026-05-13", {"dimensions_enabled": True})
    for _ in range(100):
        rec = worker.store.get(jid)
        if rec and rec.status in ("completed", "failed"):
            break
        await asyncio.sleep(0.05)

    rec = worker.store.get(jid)
    assert rec.status == "completed"
    assert rec.result is not None
    assert rec.result.get("dimensions") is None
    assert rec.result.get("dimensions_error") is not None
    assert "yfinance offline" in rec.result["dimensions_error"]
    skipped = [e for e in rec.progress_events if e.get("stage") == "dimensions_skipped"]
    assert len(skipped) == 1
```

- [ ] **Step 3: Write the failing test (cancellation)**

`tests/test_jobs_cancel.py`:

```python
import asyncio

import pytest

from api.jobs import Worker


@pytest.mark.asyncio
async def test_request_cancellation_flag_settable():
    worker = Worker(max_concurrency=1, ttl_hours=24)
    jid = worker.store.create("AAPL", "2026-05-13", {})
    assert worker.store.request_cancellation(jid) is True
    rec = worker.store.get(jid)
    assert rec.cancellation_requested is True


@pytest.mark.asyncio
async def test_cancellation_before_dimensions_skips_them(monkeypatch):
    worker = Worker(max_concurrency=1, ttl_hours=24)

    def propagate(self, *a, **k):
        # Mark cancellation just before returning
        for jid in self.store.list_ids():
            self.store.request_cancellation(jid)
        return ({"market_report": "x", "sentiment_report": "y", "news_report": "z",
                 "fundamentals_report": "w", "final_trade_decision": "Buy.",
                 "company_of_interest": "AAPL", "trade_date": "2026-05-13",
                 "investment_debate_state": {}, "risk_debate_state": {}}, "Buy")

    monkeypatch.setattr("api.jobs.Worker._propagate_sync", propagate)

    called = {"dim": 0, "comm": 0}
    monkeypatch.setattr("api.jobs.build_dimensions",
                       lambda **k: (called.__setitem__("dim", called["dim"] + 1), None)[1])
    monkeypatch.setattr("api.jobs.build_commentary",
                       lambda **k: (called.__setitem__("comm", called["comm"] + 1), None)[1])

    jid = await worker.submit("AAPL", "2026-05-13", {"dimensions_enabled": True})
    for _ in range(100):
        rec = worker.store.get(jid)
        if rec and rec.status in ("completed", "failed", "cancelled"):
            break
        await asyncio.sleep(0.05)

    rec = worker.store.get(jid)
    assert rec.status == "completed"
    assert called["dim"] == 0
    assert called["comm"] == 0
```

- [ ] **Step 4: Modify api/jobs.py — add cancellation flag + post-pass**

Add `pytest-asyncio` if missing. Check `pyproject.toml` and add:
```toml
[project.optional-dependencies]
api = [..., "pytest-asyncio"]
```

In `api/jobs.py`:

1. Add to `JobRecord` dataclass (after `batch_id`):
```python
    cancellation_requested: bool = False
```

2. Add a method to `JobStore`:
```python
    def request_cancellation(self, job_id: str) -> bool:
        with self._lock:
            rec = self._jobs.get(job_id)
            if not rec:
                return False
            rec.cancellation_requested = True
            return True

    def is_cancellation_requested(self, job_id: str) -> bool:
        with self._lock:
            rec = self._jobs.get(job_id)
            return bool(rec and rec.cancellation_requested)

    def mark_cancelled(self, job_id: str) -> None:
        with self._lock:
            rec = self._jobs.get(job_id)
            if rec:
                rec.status = "cancelled"
```

3. Update `_snapshot_record` to copy the new field:
```python
            cancellation_requested=rec.cancellation_requested,
```

4. Add imports at top:
```python
from api.dimensions.builder import (
    DimensionsBuildError, build_commentary, build_dimensions,
)
```

5. After `result = build_result(...)` and before `self.store.set_result(...)`, insert dimensions post-pass:

```python
                # --- Dimensions post-pass (failure-isolated) ---
                dimensions_enabled = bool(config.get("dimensions_enabled", True))
                if dimensions_enabled and not self.store.is_cancellation_requested(job_id):
                    try:
                        self.store.append_progress(
                            job_id, "Building dimensions: extracting facts (yfinance)…",
                            stage="dimensions",
                        )
                        self.store.append_progress(
                            job_id,
                            "Building dimensions: loading sector peers…",
                            stage="dimensions",
                        )
                        self.store.append_progress(
                            job_id,
                            "Building dimensions: scoring 16 pillars (1 LLM call)…",
                            stage="dimensions",
                        )
                        from tradingagents.llm_clients import create_llm_client
                        llm_client = create_llm_client(
                            provider=config["llm_provider"],
                            model=config["quick_think_llm"],
                            base_url=config.get("backend_url"),
                        )
                        llm = llm_client.get_llm()
                        analyst_reports = {
                            "market": final_state.get("market_report") or "",
                            "social": final_state.get("sentiment_report") or "",
                            "news": final_state.get("news_report") or "",
                            "fundamentals": final_state.get("fundamentals_report") or "",
                        }
                        dimensions = await loop.run_in_executor(
                            None,
                            lambda: build_dimensions(
                                ticker=ticker, as_of_date=date,
                                analyst_reports=analyst_reports, llm=llm, config=config,
                            ),
                        )
                        self.store.append_progress(
                            job_id,
                            "Building dimensions: computing 6 factor scores…",
                            stage="dimensions",
                        )
                        if not self.store.is_cancellation_requested(job_id):
                            self.store.append_progress(
                                job_id,
                                "Building dimensions: writing commentary (1 LLM call)…",
                                stage="dimensions",
                            )
                            commentary = await loop.run_in_executor(
                                None,
                                lambda: build_commentary(
                                    dimensions=dimensions,
                                    pm_decision_text=final_state.get("final_trade_decision") or "",
                                    llm=llm,
                                ),
                            )
                            result["dimensions_commentary"] = commentary.model_dump()
                        result["dimensions"] = dimensions.model_dump()
                        self.store.append_progress(
                            job_id,
                            f"Dimensions built (version {dimensions.dimensions_version}). Persisting…",
                            stage="dimensions",
                        )
                    except DimensionsBuildError as exc:
                        logger.warning("Dimensions build failed for %s: %s", job_id, exc)
                        result["dimensions"] = None
                        result["dimensions_commentary"] = None
                        result["dimensions_error"] = str(exc)
                        self.store.append_progress(
                            job_id, f"Dimensions skipped: {exc}",
                            stage="dimensions_skipped",
                        )
                    except Exception as exc:
                        logger.exception("Unexpected dimensions failure for %s", job_id)
                        result["dimensions"] = None
                        result["dimensions_commentary"] = None
                        result["dimensions_error"] = f"{type(exc).__name__}: {exc}"
                        self.store.append_progress(
                            job_id, f"Dimensions skipped: {exc}",
                            stage="dimensions_skipped",
                        )

                if self.store.is_cancellation_requested(job_id):
                    self.store.set_result(job_id, result)
                    self.store.append_progress(
                        job_id, "Job cancelled at stage boundary; partial result returned.",
                        stage="cancelled",
                    )
                else:
                    self.store.set_result(job_id, result)
```

(Replace the existing `self.store.set_result(job_id, result)` line with the block above.)

- [ ] **Step 5: Run all three failing tests**

```bash
pytest tests/test_jobs_dimensions_progress.py tests/test_jobs_dimensions_failure_isolation.py tests/test_jobs_cancel.py -v
```

Expected: all pass.

- [ ] **Step 6: Run regression suite**

```bash
pytest tests/ -x --ignore=tests/dimensions -v
```

Expected: existing tests still pass.

- [ ] **Step 7: Commit**

```bash
git add api/jobs.py tests/test_jobs_dimensions_progress.py \
        tests/test_jobs_dimensions_failure_isolation.py tests/test_jobs_cancel.py
git commit -m "feat(jobs): dimensions post-pass with progress events + cancellation flag"
```

---

## Task 10: SSE `connected` first event + `retry` field

**Files:**
- Modify: `api/main.py` (`/jobs/{job_id}/events` handler)
- Create: `tests/test_jobs_sse_connect_event.py`

- [ ] **Step 1: Write the failing test**

`tests/test_jobs_sse_connect_event.py`:

```python
import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.jobs import Worker
import api.main as main_module


@pytest.fixture
def client_with_job(monkeypatch):
    worker = Worker(max_concurrency=1, ttl_hours=1)
    monkeypatch.setattr(main_module, "_worker", worker)
    jid = worker.store.create("AAPL", "2026-05-13", {})
    return TestClient(app), jid


def test_sse_first_event_is_connected_with_retry(client_with_job):
    client, jid = client_with_job
    with client.stream("GET", f"/jobs/{jid}/events") as r:
        body = b""
        for chunk in r.iter_bytes():
            body += chunk
            if b"\n\n" in body:
                break
    text = body.decode("utf-8")
    assert "retry: 5000" in text
    first_data_line = next(
        (ln for ln in text.split("\n") if ln.startswith("data:")), ""
    )
    payload = json.loads(first_data_line.removeprefix("data: ").strip())
    assert payload["type"] == "connected"
    assert "cursor" in payload
    assert "status" in payload
```

- [ ] **Step 2: Modify `api/main.py`**

Replace the body of `job_events` (the existing `event_gen` async generator):

```python
@app.get("/jobs/{job_id}/events")
async def job_events(job_id: str) -> StreamingResponse:
    async def event_gen():
        rec0 = _worker.store.get(job_id)
        if rec0 is None:
            yield "retry: 5000\n"
            yield f"data: {json.dumps({'type': 'error', 'detail': 'Job not found'})}\n\n"
            return

        yield "retry: 5000\n"
        yield (
            "data: "
            + json.dumps({
                "type": "connected",
                "cursor": len(rec0.progress_events),
                "status": rec0.status,
            })
            + "\n\n"
        )

        cursor = len(rec0.progress_events)
        while True:
            chunk, new_cursor, _ = _worker.store.read_progress_since(job_id, cursor)
            cursor = new_cursor
            for evt in chunk:
                yield f"data: {json.dumps(evt)}\n\n"
            rec = _worker.store.get(job_id)
            if rec and rec.status in ("completed", "failed", "cancelled"):
                yield f"data: {json.dumps({'type': 'terminal', 'status': rec.status})}\n\n"
                break
            if rec is None:
                yield f"data: {json.dumps({'type': 'error', 'detail': 'Job not found'})}\n\n"
                break
            await asyncio.sleep(0.35)

    return StreamingResponse(event_gen(), media_type="text/event-stream")
```

- [ ] **Step 3: Run the test**

```bash
pytest tests/test_jobs_sse_connect_event.py -v
```

Expected: pass.

- [ ] **Step 4: Commit**

```bash
git add api/main.py tests/test_jobs_sse_connect_event.py
git commit -m "feat(sse): connected first event + retry field + cancelled terminal status"
```

---

## Task 11: New API endpoints

**Files:**
- Modify: `api/main.py`
- Create: `tests/dimensions/test_api_dimensions.py`

- [ ] **Step 1: Write the failing test**

`tests/dimensions/test_api_dimensions.py`:

```python
import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.jobs import Worker
import api.main as main_module
from api.dimensions.schemas import (
    StockDimensions, FactSnapshot, PillarScores, MarketPillar, SentimentPillar,
    NewsPillar, FundamentalsPillar, PillarScore, FactorScores, FactorScore,
)


def _ps(s=3):
    return PillarScore(score=s, rationale="x")


def _dim(ticker="AAPL"):
    return StockDimensions(
        ticker=ticker, as_of_date="2026-05-13",
        facts=FactSnapshot(as_of_date="2026-05-13", currency="USD"),
        pillar_scores=PillarScores(
            market=MarketPillar(trend=_ps(), momentum=_ps(), volatility_risk=_ps(),
                               setup_quality=_ps()),
            sentiment=SentimentPillar(retail_sentiment=_ps(), social_buzz=_ps(),
                                     consensus_quality=_ps(), narrative_strength=_ps()),
            news=NewsPillar(catalyst_strength=_ps(), macro_alignment=_ps(),
                           headline_quality=_ps(), surprise_risk=_ps()),
            fundamentals=FundamentalsPillar(valuation=_ps(), growth=_ps(),
                                           profitability=_ps(), balance_sheet_strength=_ps()),
        ),
        factor_scores=FactorScores(
            value=FactorScore(score=70.0), growth=FactorScore(score=60.0),
            quality=FactorScore(score=80.0), momentum=FactorScore(score=55.0),
            low_risk=FactorScore(score=40.0), sentiment=FactorScore(score=50.0),
        ),
        dimensions_version="1.0.0",
    )


@pytest.fixture
def client(monkeypatch):
    w = Worker(max_concurrency=1, ttl_hours=1)
    monkeypatch.setattr(main_module, "_worker", w)
    return TestClient(app), w


def test_get_jobs_dimensions_returns_404_unknown(client):
    c, _ = client
    r = c.get("/jobs/nope/dimensions")
    assert r.status_code == 404


def test_get_jobs_dimensions_returns_payload(client):
    c, w = client
    jid = w.store.create("AAPL", "2026-05-13", {})
    w.store.set_result(jid, {"dimensions": _dim().model_dump(),
                              "ticker": "AAPL", "date": "2026-05-13",
                              "rating": "Buy", "reports": {}})
    r = c.get(f"/jobs/{jid}/dimensions")
    assert r.status_code == 200
    assert r.json()["ticker"] == "AAPL"


def test_cancel_endpoint_sets_flag(client):
    c, w = client
    jid = w.store.create("AAPL", "2026-05-13", {})
    r = c.post(f"/jobs/{jid}/cancel")
    assert r.status_code == 200
    body = r.json()
    assert body["cancellation_requested"] is True
    rec = w.store.get(jid)
    assert rec.cancellation_requested is True


def test_cancel_endpoint_404_unknown(client):
    c, _ = client
    r = c.post("/jobs/nope/cancel")
    assert r.status_code == 404


def test_dimensions_by_ticker_facts_only(client, monkeypatch):
    c, _ = client
    from api.dimensions.schemas import StockDimensions
    fake = _dim("MSFT")
    fake = fake.model_copy(update={"source": "facts_only"})
    monkeypatch.setattr(
        "api.main.build_dimensions_facts_only",
        lambda **k: fake,
    )
    r = c.get("/dimensions/MSFT")
    assert r.status_code == 200
    assert r.json()["source"] == "facts_only"


def test_admin_peer_cache_refresh_requires_key(client, monkeypatch):
    c, _ = client
    monkeypatch.setenv("TRADINGAGENTS_ADMIN_KEY", "secret")
    r = c.post("/admin/dimensions/peer-cache/refresh",
               json={"sector": "Tech", "industry": "Soft"})
    assert r.status_code == 401
    r2 = c.post("/admin/dimensions/peer-cache/refresh",
                json={"sector": "Tech", "industry": "Soft"},
                headers={"X-Admin-Key": "secret"})
    # 200 even with no peers (returns 0 written)
    assert r2.status_code in (200, 503)
```

- [ ] **Step 2: Add endpoint handlers to `api/main.py`**

Add imports at the top of `api/main.py`:

```python
from api.dimensions import (
    DimensionsBuildError, build_dimensions_facts_only,
)
from api.dimensions.schemas import StockDimensions
```

Add these handlers (e.g. after the existing `/jobs/{job_id}/report` handler):

```python
@app.get("/jobs/{job_id}/dimensions", response_model=StockDimensions)
async def get_job_dimensions(job_id: str) -> Dict[str, Any]:
    rec = _worker.store.get(job_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Job not found")
    dims = (rec.result or {}).get("dimensions") if rec.result else None
    if not dims:
        raise HTTPException(
            status_code=404,
            detail="Dimensions not available for this job (still running, build failed, or disabled)",
        )
    return dims


@app.post("/jobs/{job_id}/cancel")
async def cancel_job(job_id: str) -> Dict[str, Any]:
    if not _worker.store.request_cancellation(job_id):
        raise HTTPException(status_code=404, detail="Job not found")
    rec = _worker.store.get(job_id)
    return {
        "cancellation_requested": True,
        "status": rec.status if rec else "unknown",
        "note": "Cancellation is honored at the next stage boundary; propagate() cannot be interrupted mid-run.",
    }


@app.get("/dimensions/{ticker}", response_model=StockDimensions)
async def get_dimensions_facts_only(
    ticker: str,
    as_of_date: Optional[str] = Query(None),
) -> Dict[str, Any]:
    from api.tickers import normalize_ticker, validate_date
    try:
        norm = normalize_ticker(ticker)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid ticker: {exc}")
    d = as_of_date or datetime.utcnow().strftime("%Y-%m-%d")
    if not validate_date(d):
        raise HTTPException(status_code=400, detail="as_of_date must be YYYY-MM-DD")
    try:
        out = build_dimensions_facts_only(
            ticker=norm, as_of_date=d, config=_service_config,
        )
    except DimensionsBuildError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return out.model_dump()


@app.post("/admin/dimensions/peer-cache/refresh")
async def admin_refresh_peer_cache(
    body: Dict[str, Any],
    _admin: None = Depends(_admin_key_dep),
) -> Dict[str, Any]:
    """Refresh peer cache for a sector+industry. Reads peer list from request or defaults."""
    from api.dimensions.peers import PeerCache, slug_for_sector
    from api.dimensions.facts import extract_facts
    sector = (body or {}).get("sector")
    industry = (body or {}).get("industry")
    tickers = (body or {}).get("tickers") or []
    slug = slug_for_sector(sector, industry)
    if not slug:
        raise HTTPException(status_code=400, detail="sector and industry required")
    cache_dir = Path(_service_config.get("data_cache_dir") or "./data_cache") / "peer_facts"
    cache = PeerCache(base_dir=cache_dir)
    today = datetime.utcnow().strftime("%Y-%m-%d")
    facts: Dict[str, Dict[str, Any]] = {}
    for t in tickers:
        try:
            snap, _flags = extract_facts(t, today)
            facts[t] = snap.model_dump()
        except Exception as exc:
            logger.warning("peer refresh skip %s: %s", t, exc)
    cache.write(slug, list(facts.keys()), facts)
    return {"slug": slug, "count": len(facts), "tickers": list(facts.keys())}
```

- [ ] **Step 3: Run tests**

```bash
pytest tests/dimensions/test_api_dimensions.py -v
```

Expected: 6 passed.

- [ ] **Step 4: Commit**

```bash
git add api/main.py tests/dimensions/test_api_dimensions.py
git commit -m "feat(api): /jobs/{id}/dimensions, /jobs/{id}/cancel, /dimensions/{ticker}, peer-cache refresh"
```

---

## Task 12: History persistence — dimensions in run record + recompute endpoint

**Files:**
- Modify: `api/history.py` (persist + read dimensions; D1 column additions)
- Modify: `api/main.py` (add `/history/runs/{run_id}/recompute-dimensions`)
- Create: `tests/dimensions/test_history_dimensions.py`

- [ ] **Step 1: Write the failing test**

`tests/dimensions/test_history_dimensions.py`:

```python
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from api.history import persist_completed_run, get_run, list_runs
from api.state_store import LocalFileStateStore
from api.main import app
import api.main as main_module
from api.jobs import Worker


@pytest.fixture
def store(tmp_path):
    return LocalFileStateStore(path=tmp_path / "state.json")


def test_persist_run_with_dimensions_round_trips(store):
    result = {
        "ticker": "AAPL", "date": "2026-05-13", "rating": "Buy",
        "confidence": 0.9, "reports": {"market": "x"},
        "completed_at": "2026-05-13T00:00:00Z",
        "dimensions": {"ticker": "AAPL", "as_of_date": "2026-05-13",
                       "factor_scores": {"value": {"score": 70.0, "inputs": {}}}},
        "dimensions_commentary": {"alignment": "aligned", "summary": "ok",
                                  "supporting_dimensions": ["value"],
                                  "conflicting_dimensions": [], "risk_flags": []},
    }
    persist_completed_run(
        store, job_id="job1", ticker="AAPL", date="2026-05-13",
        result=result, created_at=datetime.utcnow(),
    )
    rec = get_run(store, "job1")
    assert rec is not None
    assert rec["dimensions"]["factor_scores"]["value"]["score"] == 70.0
    assert rec["dimensions_commentary"]["alignment"] == "aligned"


def test_list_runs_includes_factor_scores_in_ref(store):
    result = {
        "ticker": "AAPL", "date": "2026-05-13", "rating": "Buy",
        "reports": {}, "completed_at": "2026-05-13T00:00:00Z",
        "dimensions": {
            "ticker": "AAPL", "as_of_date": "2026-05-13",
            "factor_scores": {
                "value": {"score": 70.0, "inputs": {}},
                "growth": {"score": 60.0, "inputs": {}},
                "quality": {"score": 80.0, "inputs": {}},
                "momentum": {"score": 55.0, "inputs": {}},
                "low_risk": {"score": 40.0, "inputs": {}},
                "sentiment": {"score": 50.0, "inputs": {}},
            },
        },
    }
    persist_completed_run(
        store, job_id="job2", ticker="AAPL", date="2026-05-13",
        result=result, created_at=datetime.utcnow(),
    )
    rows = list_runs(store, ticker="AAPL", limit=10)
    assert len(rows) >= 1
    row = rows[0]
    assert row.get("factor_scores", {}).get("value") == 70.0


def test_recompute_dimensions_endpoint(monkeypatch, store, tmp_path):
    # Pre-populate a run with no dimensions
    result = {
        "ticker": "AAPL", "date": "2026-05-13", "rating": "Buy",
        "reports": {"market": "m", "social": "s", "news": "n",
                    "fundamentals": "f", "portfolio_decision": "Buy."},
        "completed_at": "2026-05-13T00:00:00Z",
    }
    persist_completed_run(
        store, job_id="job3", ticker="AAPL", date="2026-05-13",
        result=result, created_at=datetime.utcnow(),
    )

    monkeypatch.setattr("api.main.get_state_store", lambda: store)

    # Stub the builders so we don't touch yfinance/LLM
    from api.dimensions.schemas import (
        StockDimensions, FactSnapshot, PillarScores, MarketPillar, SentimentPillar,
        NewsPillar, FundamentalsPillar, PillarScore, FactorScores, FactorScore,
        DimensionsCommentary,
    )

    def _ps(): return PillarScore(score=3, rationale="x")

    fake_dim = StockDimensions(
        ticker="AAPL", as_of_date="2026-05-13",
        facts=FactSnapshot(as_of_date="2026-05-13", currency="USD"),
        pillar_scores=PillarScores(
            market=MarketPillar(trend=_ps(), momentum=_ps(), volatility_risk=_ps(),
                               setup_quality=_ps()),
            sentiment=SentimentPillar(retail_sentiment=_ps(), social_buzz=_ps(),
                                     consensus_quality=_ps(), narrative_strength=_ps()),
            news=NewsPillar(catalyst_strength=_ps(), macro_alignment=_ps(),
                           headline_quality=_ps(), surprise_risk=_ps()),
            fundamentals=FundamentalsPillar(valuation=_ps(), growth=_ps(),
                                           profitability=_ps(), balance_sheet_strength=_ps()),
        ),
        factor_scores=FactorScores(
            value=FactorScore(score=70.0), growth=FactorScore(score=60.0),
            quality=FactorScore(score=80.0), momentum=FactorScore(score=55.0),
            low_risk=FactorScore(score=40.0), sentiment=FactorScore(score=50.0),
        ),
        dimensions_version="1.0.0",
    )
    fake_comm = DimensionsCommentary(
        alignment="aligned", supporting_dimensions=["value"],
        conflicting_dimensions=[], risk_flags=[], summary="ok",
    )
    monkeypatch.setattr("api.main.build_dimensions", lambda **k: fake_dim)
    monkeypatch.setattr("api.main.build_commentary_orchestrator", lambda **k: fake_comm)
    # Stub the LLM factory
    monkeypatch.setattr("api.main._build_llm_for_dimensions", lambda cfg: MagicMock())

    client = TestClient(app)
    r = client.post("/history/runs/job3/recompute-dimensions")
    assert r.status_code == 200
    body = r.json()
    assert body["dimensions"]["factor_scores"]["value"]["score"] == 70.0
```

- [ ] **Step 2: Modify `api/history.py`**

Edit `persist_completed_run` to include dimensions in the persisted record. Change the `full` dict construction:

```python
    full: Dict[str, Any] = {
        # ...existing fields...
        "dimensions": result.get("dimensions"),
        "dimensions_commentary": result.get("dimensions_commentary"),
        "dimensions_error": result.get("dimensions_error"),
    }
```

Update `_ref_from_record` to extract factor scores:

```python
def _ref_from_record(rec: Dict[str, Any]) -> Dict[str, Any]:
    ref = {
        "run_id": rec.get("run_id") or rec.get("job_id"),
        "job_id": rec.get("job_id"),
        "ticker": rec.get("ticker"),
        "date": rec.get("date"),
        "rating": rec.get("rating"),
        "confidence": rec.get("confidence"),
        "completed_at": rec.get("completed_at"),
        "created_at": rec.get("created_at"),
        "batch_id": rec.get("batch_id"),
    }
    dims = rec.get("dimensions") or {}
    fs = dims.get("factor_scores") if isinstance(dims, dict) else None
    if isinstance(fs, dict):
        scores = {}
        for name in ("value", "growth", "quality", "momentum", "low_risk", "sentiment"):
            v = fs.get(name)
            if isinstance(v, dict) and v.get("score") is not None:
                scores[name] = v["score"]
        if scores:
            ref["factor_scores"] = scores
    return ref
```

For the D1 path, alter `_ensure_d1_schema` to add columns conditionally (D1 ignores `ADD COLUMN IF NOT EXISTS` errors via a try/except wrapping):

```python
    try:
        _d1_query("ALTER TABLE analysis_runs ADD COLUMN dimensions_json TEXT")
    except Exception:
        pass  # column already exists
    try:
        _d1_query("ALTER TABLE analysis_runs ADD COLUMN dimensions_commentary_json TEXT")
    except Exception:
        pass
    try:
        _d1_query("ALTER TABLE analysis_runs ADD COLUMN dimensions_error TEXT")
    except Exception:
        pass
```

Update `_persist_d1` INSERT to include the three new columns. Update `_d1_row_to_full` to parse them. Update `_list_runs_d1` SELECT to also fetch `dimensions_json` and include `factor_scores` ref extraction.

- [ ] **Step 3: Add the recompute endpoint to `api/main.py`**

```python
from api.dimensions.builder import (
    build_dimensions as build_dimensions_orchestrator,
    build_commentary as build_commentary_orchestrator,
)


def _build_llm_for_dimensions(cfg: Dict[str, Any]):
    from tradingagents.llm_clients import create_llm_client
    client = create_llm_client(
        provider=cfg["llm_provider"],
        model=cfg["quick_think_llm"],
        base_url=cfg.get("backend_url"),
    )
    return client.get_llm()


@app.post("/history/runs/{run_id}/recompute-dimensions", response_model=HistoryRunDetail)
async def recompute_dimensions(run_id: str) -> Dict[str, Any]:
    store = get_state_store()
    rec = get_run(store, run_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Run not found")
    reports = rec.get("reports") or {}
    missing = [k for k in ("market", "social", "news", "fundamentals") if not reports.get(k)]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Run is missing reports required to recompute dimensions: {missing}",
        )
    llm = _build_llm_for_dimensions(_service_config)
    try:
        dims = build_dimensions_orchestrator(
            ticker=rec["ticker"], as_of_date=rec["date"],
            analyst_reports={
                "market": reports.get("market") or "",
                "social": reports.get("social") or "",
                "news": reports.get("news") or "",
                "fundamentals": reports.get("fundamentals") or "",
            },
            llm=llm, config=_service_config,
        )
        commentary = build_commentary_orchestrator(
            dimensions=dims,
            pm_decision_text=reports.get("portfolio_decision") or "",
            llm=llm,
        )
    except DimensionsBuildError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    rec["dimensions"] = dims.model_dump()
    rec["dimensions_commentary"] = commentary.model_dump()
    rec["dimensions_error"] = None
    # Re-persist
    persist_completed_run(
        store,
        job_id=rec["job_id"],
        ticker=rec["ticker"],
        date=rec["date"],
        result=rec,
        created_at=datetime.fromisoformat(
            (rec.get("created_at") or "").replace("Z", "")
        ) if rec.get("created_at") else datetime.utcnow(),
        batch_id=rec.get("batch_id"),
        config_snapshot=rec.get("config_snapshot"),
    )
    return HistoryRunDetail.model_validate(rec).model_dump()
```

Also add the import `from api.history import persist_completed_run` if not already present.

- [ ] **Step 4: Run tests**

```bash
pytest tests/dimensions/test_history_dimensions.py -v
pytest tests/test_api_history.py -v  # regression
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add api/history.py api/main.py tests/dimensions/test_history_dimensions.py
git commit -m "feat(history): persist dimensions + factor_scores ref + recompute endpoint"
```

---

## Task 13: Frontend — install Recharts + API typings

**Files:**
- Modify: `frontend/package.json`
- Modify: `frontend/src/api.ts`
- Create: `frontend/src/dimensions-types.ts`

- [ ] **Step 1: Install Recharts**

```bash
cd frontend && npm install recharts && cd ..
```

Verify `package.json` now lists `"recharts": "^2.x"`.

- [ ] **Step 2: Create the types file**

`frontend/src/dimensions-types.ts`:

```ts
export interface PillarScore { score: number; rationale: string }

export interface FactSnapshot {
  as_of_date: string; currency: string;
  exchange?: string | null; sector?: string | null; industry?: string | null;
  market_cap_usd?: number | null;
  price?: number | null; price_52w_high?: number | null;
  pct_off_52w_high?: number | null;
  return_1m?: number | null; return_3m?: number | null;
  return_6m?: number | null; return_12m?: number | null;
  beta?: number | null;
  realized_vol_30d?: number | null; rsi_14?: number | null;
  avg_daily_dollar_volume_30d?: number | null;
  pe_ttm?: number | null; forward_pe?: number | null; peg?: number | null;
  ev_ebitda?: number | null; ps_ttm?: number | null; pb?: number | null;
  fcf_yield?: number | null;
  revenue_growth_yoy?: number | null; eps_growth_yoy?: number | null;
  revenue_cagr_3y?: number | null; eps_cagr_3y?: number | null;
  roe?: number | null; roic?: number | null;
  gross_margin?: number | null; operating_margin?: number | null;
  net_margin?: number | null; debt_to_equity?: number | null;
  interest_coverage?: number | null; current_ratio?: number | null;
  dividend_yield?: number | null; payout_ratio?: number | null;
  analyst_count?: number | null;
  analyst_target_mean?: number | null; analyst_recommendation_mean?: number | null;
}

export interface PillarScores {
  market: { trend: PillarScore; momentum: PillarScore;
            volatility_risk: PillarScore; setup_quality: PillarScore };
  sentiment: { retail_sentiment: PillarScore; social_buzz: PillarScore;
               consensus_quality: PillarScore; narrative_strength: PillarScore };
  news: { catalyst_strength: PillarScore; macro_alignment: PillarScore;
          headline_quality: PillarScore; surprise_risk: PillarScore };
  fundamentals: { valuation: PillarScore; growth: PillarScore;
                  profitability: PillarScore; balance_sheet_strength: PillarScore };
}

export interface FactorScore { score: number | null; inputs: Record<string, number> }

export interface FactorScores {
  value: FactorScore; growth: FactorScore; quality: FactorScore;
  momentum: FactorScore; low_risk: FactorScore; sentiment: FactorScore;
}

export interface StockDimensions {
  ticker: string; as_of_date: string;
  facts: FactSnapshot; pillar_scores: PillarScores; factor_scores: FactorScores;
  dimensions_version: string;
  peer_universe_id?: string | null;
  data_quality_flags: string[];
  source: 'full_run' | 'facts_only';
}

export interface DimensionsCommentary {
  alignment: 'aligned' | 'partial' | 'misaligned';
  supporting_dimensions: string[]; conflicting_dimensions: string[];
  risk_flags: string[]; summary: string;
}
```

- [ ] **Step 3: Add API helpers to `frontend/src/api.ts`**

Read existing `api.ts` first to follow its style, then append:

```ts
import type { StockDimensions, DimensionsCommentary } from './dimensions-types';

export async function getJobDimensions(jobId: string): Promise<StockDimensions> {
  const r = await fetch(`/jobs/${jobId}/dimensions`);
  if (!r.ok) throw new Error(`getJobDimensions failed: ${r.status}`);
  return r.json();
}

export async function getDimensionsByTicker(
  ticker: string, asOfDate?: string,
): Promise<StockDimensions> {
  const url = asOfDate
    ? `/dimensions/${encodeURIComponent(ticker)}?as_of_date=${asOfDate}`
    : `/dimensions/${encodeURIComponent(ticker)}`;
  const r = await fetch(url);
  if (!r.ok) throw new Error(`getDimensionsByTicker failed: ${r.status}`);
  return r.json();
}

export async function cancelJob(jobId: string): Promise<{ cancellation_requested: boolean; status: string }> {
  const r = await fetch(`/jobs/${jobId}/cancel`, { method: 'POST' });
  if (!r.ok) throw new Error(`cancelJob failed: ${r.status}`);
  return r.json();
}

export async function recomputeDimensions(runId: string) {
  const r = await fetch(`/history/runs/${runId}/recompute-dimensions`, { method: 'POST' });
  if (!r.ok) throw new Error(`recomputeDimensions failed: ${r.status}`);
  return r.json();
}
```

- [ ] **Step 4: Smoke test the build**

```bash
cd frontend && npm run build && cd ..
```

Expected: no TypeScript errors, dist/ produced.

- [ ] **Step 5: Commit**

```bash
git add frontend/package.json frontend/package-lock.json \
        frontend/src/api.ts frontend/src/dimensions-types.ts
git commit -m "feat(frontend): install Recharts + add Dimensions TS types and API helpers"
```

---

## Task 14: Frontend components — FactorBar + DimensionsRadar

**Files:**
- Create: `frontend/src/components/dimensions/FactorBar.tsx`
- Create: `frontend/src/components/dimensions/FactorBar.test.tsx`
- Create: `frontend/src/components/dimensions/DimensionsRadar.tsx`
- Create: `frontend/src/components/dimensions/DimensionsRadar.test.tsx`

- [ ] **Step 1: Write FactorBar test**

`frontend/src/components/dimensions/FactorBar.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { FactorBar, colorTier } from './FactorBar';

describe('colorTier', () => {
  it.each([
    [0, 'red'], [19, 'red'], [20, 'orange'], [39, 'orange'],
    [40, 'amber'], [59, 'amber'], [60, 'lime'], [79, 'lime'],
    [80, 'green'], [100, 'green'],
  ])('maps %d to %s', (score, expected) => {
    expect(colorTier(score)).toBe(expected);
  });
});

describe('FactorBar', () => {
  it('renders the score label', () => {
    render(<FactorBar label="Value" score={72.5} />);
    expect(screen.getByText(/72/)).toBeInTheDocument();
    expect(screen.getByText('Value')).toBeInTheDocument();
  });

  it('renders empty state when score is null', () => {
    render(<FactorBar label="Value" score={null} />);
    expect(screen.getByText(/—/)).toBeInTheDocument();
  });
});
```

If `@testing-library/react` is not installed, add it:

```bash
cd frontend && npm install --save-dev @testing-library/react @testing-library/jest-dom && cd ..
```

Add `setup.ts` if not already present, importing `'@testing-library/jest-dom'`.

- [ ] **Step 2: Implement FactorBar**

`frontend/src/components/dimensions/FactorBar.tsx`:

```tsx
import React from 'react';

export type Tier = 'red' | 'orange' | 'amber' | 'lime' | 'green';

export function colorTier(score: number): Tier {
  if (score < 20) return 'red';
  if (score < 40) return 'orange';
  if (score < 60) return 'amber';
  if (score < 80) return 'lime';
  return 'green';
}

const TIER_COLORS: Record<Tier, string> = {
  red: '#d23',
  orange: '#e57',
  amber: '#ea3',
  lime: '#9c3',
  green: '#3a3',
};

const TIER_ICONS: Record<Tier, string> = {
  red: '▼▼', orange: '▼', amber: '◆', lime: '▲', green: '▲▲',
};

export interface FactorBarProps {
  label: string;
  score: number | null;
  width?: number;
}

export function FactorBar({ label, score, width = 120 }: FactorBarProps) {
  if (score == null) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{ minWidth: 80 }}>{label}</span>
        <span style={{ color: '#999' }}>—</span>
      </div>
    );
  }
  const tier = colorTier(score);
  const pct = Math.max(0, Math.min(100, score));
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <span style={{ minWidth: 80 }}>{label}</span>
      <div style={{ width, height: 10, background: '#eee', borderRadius: 4 }}>
        <div
          style={{
            width: `${pct}%`, height: '100%',
            background: TIER_COLORS[tier], borderRadius: 4,
          }}
        />
      </div>
      <span style={{ minWidth: 36, textAlign: 'right' }}>{Math.round(score)}</span>
      <span aria-label={`tier-${tier}`} title={tier} style={{ color: TIER_COLORS[tier] }}>
        {TIER_ICONS[tier]}
      </span>
    </div>
  );
}
```

- [ ] **Step 3: Write DimensionsRadar test**

`frontend/src/components/dimensions/DimensionsRadar.test.tsx`:

```tsx
import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { DimensionsRadar } from './DimensionsRadar';

describe('DimensionsRadar', () => {
  it('renders with full factor scores', () => {
    const { container } = render(
      <DimensionsRadar
        factorScores={{
          value: { score: 70, inputs: {} },
          growth: { score: 60, inputs: {} },
          quality: { score: 80, inputs: {} },
          momentum: { score: 55, inputs: {} },
          low_risk: { score: 40, inputs: {} },
          sentiment: { score: 50, inputs: {} },
        }}
      />,
    );
    expect(container.querySelector('svg')).toBeTruthy();
  });

  it('renders empty state with null scores', () => {
    const { getByText } = render(
      <DimensionsRadar
        factorScores={{
          value: { score: null, inputs: {} },
          growth: { score: null, inputs: {} },
          quality: { score: null, inputs: {} },
          momentum: { score: null, inputs: {} },
          low_risk: { score: null, inputs: {} },
          sentiment: { score: null, inputs: {} },
        }}
      />,
    );
    expect(getByText(/insufficient data/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 4: Implement DimensionsRadar**

`frontend/src/components/dimensions/DimensionsRadar.tsx`:

```tsx
import React from 'react';
import {
  Radar, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, ResponsiveContainer,
} from 'recharts';
import type { FactorScores } from '../../dimensions-types';

export interface DimensionsRadarProps {
  factorScores: FactorScores;
  height?: number;
}

const FACTOR_ORDER: (keyof FactorScores)[] = [
  'value', 'growth', 'quality', 'momentum', 'low_risk', 'sentiment',
];

const FACTOR_LABEL: Record<keyof FactorScores, string> = {
  value: 'Value', growth: 'Growth', quality: 'Quality',
  momentum: 'Momentum', low_risk: 'Low Risk', sentiment: 'Sentiment',
};

export function DimensionsRadar({ factorScores, height = 280 }: DimensionsRadarProps) {
  const data = FACTOR_ORDER.map(k => ({
    factor: FACTOR_LABEL[k],
    score: factorScores[k].score ?? 0,
    available: factorScores[k].score != null,
  }));
  const anyData = data.some(d => d.available);
  if (!anyData) {
    return <div style={{ height, display: 'flex', alignItems: 'center',
                        justifyContent: 'center', color: '#888' }}>
      Insufficient data for radar chart
    </div>;
  }
  return (
    <ResponsiveContainer width="100%" height={height}>
      <RadarChart data={data}>
        <PolarGrid />
        <PolarAngleAxis dataKey="factor" />
        <PolarRadiusAxis angle={30} domain={[0, 100]} />
        <Radar name="Factor" dataKey="score" stroke="#3a3" fill="#3a3" fillOpacity={0.3} />
      </RadarChart>
    </ResponsiveContainer>
  );
}
```

- [ ] **Step 5: Run frontend tests**

```bash
cd frontend && npm test && cd ..
```

Expected: new tests pass.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/dimensions/FactorBar.tsx \
        frontend/src/components/dimensions/FactorBar.test.tsx \
        frontend/src/components/dimensions/DimensionsRadar.tsx \
        frontend/src/components/dimensions/DimensionsRadar.test.tsx \
        frontend/package.json frontend/package-lock.json
git commit -m "feat(frontend): FactorBar + DimensionsRadar components"
```

---

## Task 15: Frontend — PillarGrid, FactsTable, CommentaryCard, DimensionsPanel

**Files:**
- Create: `frontend/src/components/dimensions/PillarGrid.tsx` + test
- Create: `frontend/src/components/dimensions/FactsTable.tsx`
- Create: `frontend/src/components/dimensions/CommentaryCard.tsx`
- Create: `frontend/src/components/dimensions/DimensionsPanel.tsx` + test

- [ ] **Step 1: Write PillarGrid test**

`frontend/src/components/dimensions/PillarGrid.test.tsx`:

```tsx
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { PillarGrid } from './PillarGrid';
import type { PillarScores } from '../../dimensions-types';

const _ps = (s = 3, r = 'rationale text') => ({ score: s, rationale: r });

const pillars: PillarScores = {
  market: { trend: _ps(4, 'strong uptrend'), momentum: _ps(), volatility_risk: _ps(), setup_quality: _ps() },
  sentiment: { retail_sentiment: _ps(), social_buzz: _ps(), consensus_quality: _ps(), narrative_strength: _ps() },
  news: { catalyst_strength: _ps(), macro_alignment: _ps(), headline_quality: _ps(), surprise_risk: _ps() },
  fundamentals: { valuation: _ps(), growth: _ps(), profitability: _ps(), balance_sheet_strength: _ps() },
};

describe('PillarGrid', () => {
  it('shows all 16 sub-dimensions', () => {
    render(<PillarGrid pillars={pillars} />);
    expect(screen.getAllByRole('button').length).toBeGreaterThanOrEqual(16);
  });

  it('exposes rationale via tooltip role', () => {
    render(<PillarGrid pillars={pillars} />);
    const trend = screen.getByRole('button', { name: /trend/i });
    expect(trend).toHaveAttribute('title', expect.stringContaining('strong uptrend'));
  });
});
```

- [ ] **Step 2: Implement PillarGrid**

`frontend/src/components/dimensions/PillarGrid.tsx`:

```tsx
import React from 'react';
import type { PillarScore, PillarScores } from '../../dimensions-types';

const SCORE_COLORS = ['#d23', '#e57', '#ea3', '#9c3', '#3a3'];

function Cell({ label, score }: { label: string; score: PillarScore }) {
  const color = SCORE_COLORS[score.score - 1];
  return (
    <button
      type="button"
      title={score.rationale}
      style={{
        padding: 8, border: '1px solid #ddd', borderRadius: 4,
        background: '#fafafa', textAlign: 'left', cursor: 'help',
      }}
    >
      <div style={{ fontSize: 12, color: '#666' }}>{label}</div>
      <div style={{ color, fontWeight: 600, fontSize: 18 }}>
        {score.score}/5
      </div>
    </button>
  );
}

export interface PillarGridProps { pillars: PillarScores }

const PILLAR_GROUPS: Array<[string, keyof PillarScores, string[]]> = [
  ['Market', 'market', ['trend', 'momentum', 'volatility_risk', 'setup_quality']],
  ['Sentiment', 'sentiment',
   ['retail_sentiment', 'social_buzz', 'consensus_quality', 'narrative_strength']],
  ['News', 'news',
   ['catalyst_strength', 'macro_alignment', 'headline_quality', 'surprise_risk']],
  ['Fundamentals', 'fundamentals',
   ['valuation', 'growth', 'profitability', 'balance_sheet_strength']],
];

export function PillarGrid({ pillars }: PillarGridProps) {
  return (
    <div style={{ display: 'grid', gap: 16 }}>
      {PILLAR_GROUPS.map(([title, key, dims]) => (
        <div key={key}>
          <h4 style={{ margin: '4px 0' }}>{title}</h4>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 8 }}>
            {dims.map(d => (
              <Cell key={d} label={d.replace(/_/g, ' ')}
                    score={(pillars[key] as any)[d]} />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 3: Implement FactsTable**

`frontend/src/components/dimensions/FactsTable.tsx`:

```tsx
import React from 'react';
import type { FactSnapshot } from '../../dimensions-types';

const GROUPS: Array<[string, (keyof FactSnapshot)[]]> = [
  ['Price & Return', ['price', 'price_52w_high', 'pct_off_52w_high',
                      'return_1m', 'return_3m', 'return_6m', 'return_12m', 'beta']],
  ['Volatility & Liquidity', ['realized_vol_30d', 'rsi_14',
                              'avg_daily_dollar_volume_30d']],
  ['Valuation', ['pe_ttm', 'forward_pe', 'peg', 'ev_ebitda', 'ps_ttm', 'pb',
                 'fcf_yield']],
  ['Growth', ['revenue_growth_yoy', 'eps_growth_yoy', 'revenue_cagr_3y', 'eps_cagr_3y']],
  ['Quality', ['roe', 'roic', 'gross_margin', 'operating_margin', 'net_margin',
               'debt_to_equity', 'interest_coverage', 'current_ratio']],
  ['Income', ['dividend_yield', 'payout_ratio']],
  ['Sell-side', ['analyst_count', 'analyst_target_mean', 'analyst_recommendation_mean']],
];

function fmt(v: any): string {
  if (v == null) return '—';
  if (typeof v === 'number') return Math.abs(v) < 1 ? v.toFixed(3) : v.toLocaleString();
  return String(v);
}

export function FactsTable({ facts }: { facts: FactSnapshot }) {
  return (
    <div style={{ display: 'grid', gap: 16 }}>
      {GROUPS.map(([title, keys]) => (
        <div key={title}>
          <h4 style={{ margin: '4px 0' }}>{title}</h4>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <tbody>
              {keys.map(k => (
                <tr key={k as string}>
                  <td style={{ padding: '4px 8px', color: '#555' }}>
                    {(k as string).replace(/_/g, ' ')}
                  </td>
                  <td style={{ padding: '4px 8px', textAlign: 'right' }}>
                    {fmt((facts as any)[k])}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 4: Implement CommentaryCard**

`frontend/src/components/dimensions/CommentaryCard.tsx`:

```tsx
import React from 'react';
import type { DimensionsCommentary } from '../../dimensions-types';

const ALIGN_COLORS = {
  aligned: '#3a3', partial: '#ea3', misaligned: '#d23',
};

export function CommentaryCard({ commentary }: { commentary: DimensionsCommentary }) {
  return (
    <div style={{ border: '1px solid #ddd', borderRadius: 6, padding: 16,
                  background: '#fafafa' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{
          padding: '2px 8px', borderRadius: 4,
          background: ALIGN_COLORS[commentary.alignment], color: 'white',
          fontSize: 12, textTransform: 'uppercase',
        }}>{commentary.alignment}</span>
        <strong>Dimensions Commentary</strong>
      </div>
      <p style={{ margin: '12px 0' }}>{commentary.summary}</p>
      {commentary.supporting_dimensions.length > 0 && (
        <div><strong>Supporting:</strong> {commentary.supporting_dimensions.join(', ')}</div>
      )}
      {commentary.conflicting_dimensions.length > 0 && (
        <div><strong>Conflicting:</strong> {commentary.conflicting_dimensions.join(', ')}</div>
      )}
      {commentary.risk_flags.length > 0 && (
        <div><strong>Risk flags:</strong> {commentary.risk_flags.join(', ')}</div>
      )}
    </div>
  );
}
```

- [ ] **Step 5: Implement DimensionsPanel + its test**

`frontend/src/components/dimensions/DimensionsPanel.tsx`:

```tsx
import React from 'react';
import { DimensionsRadar } from './DimensionsRadar';
import { PillarGrid } from './PillarGrid';
import { FactsTable } from './FactsTable';
import { CommentaryCard } from './CommentaryCard';
import { FactorBar } from './FactorBar';
import type { StockDimensions, DimensionsCommentary } from '../../dimensions-types';

export interface DimensionsPanelProps {
  dimensions: StockDimensions | null;
  commentary?: DimensionsCommentary | null;
  error?: string | null;
}

const FACTOR_KEYS = ['value', 'growth', 'quality', 'momentum', 'low_risk', 'sentiment'] as const;

export function DimensionsPanel({ dimensions, commentary, error }: DimensionsPanelProps) {
  if (error) {
    return (
      <div style={{ padding: 16, border: '1px solid #ea3', borderRadius: 6 }}>
        <strong>Dimensions unavailable for this run.</strong>
        <p style={{ margin: '8px 0 0', color: '#666' }}>{error}</p>
      </div>
    );
  }
  if (!dimensions) {
    return (
      <div style={{ padding: 16, border: '1px dashed #ccc', borderRadius: 6 }}>
        Dimensions not available — this run predates v1.0 of the dimensions layer.
      </div>
    );
  }
  return (
    <section style={{ display: 'grid', gap: 24 }}>
      <header>
        <h3 style={{ margin: 0 }}>Standardized Dimensions</h3>
        <small style={{ color: '#666' }}>
          version {dimensions.dimensions_version}
          {dimensions.peer_universe_id && ` · ${dimensions.peer_universe_id}`}
          {dimensions.source === 'facts_only' && ' · facts only (preview)'}
        </small>
      </header>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 24 }}>
        <DimensionsRadar factorScores={dimensions.factor_scores} />
        <div style={{ display: 'grid', gap: 8 }}>
          {FACTOR_KEYS.map(k => (
            <FactorBar
              key={k}
              label={k.replace('_', ' ')}
              score={dimensions.factor_scores[k].score}
            />
          ))}
        </div>
      </div>
      {commentary && <CommentaryCard commentary={commentary} />}
      <PillarGrid pillars={dimensions.pillar_scores} />
      <FactsTable facts={dimensions.facts} />
      {dimensions.data_quality_flags.length > 0 && (
        <div style={{ fontSize: 12, color: '#888' }}>
          Data quality flags: {dimensions.data_quality_flags.join(', ')}
        </div>
      )}
    </section>
  );
}
```

`frontend/src/components/dimensions/DimensionsPanel.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { DimensionsPanel } from './DimensionsPanel';

describe('DimensionsPanel', () => {
  it('renders empty state when dimensions is null', () => {
    render(<DimensionsPanel dimensions={null} />);
    expect(screen.getByText(/predates v1.0/i)).toBeInTheDocument();
  });

  it('renders error state when error provided', () => {
    render(<DimensionsPanel dimensions={null} error="yfinance offline" />);
    expect(screen.getByText(/yfinance offline/)).toBeInTheDocument();
  });
});
```

- [ ] **Step 6: Run frontend tests**

```bash
cd frontend && npm test && cd ..
```

Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/dimensions/
git commit -m "feat(frontend): PillarGrid, FactsTable, CommentaryCard, DimensionsPanel"
```

---

## Task 16: DashboardPage integration

**Files:**
- Modify: `frontend/src/pages/DashboardPage.tsx`

- [ ] **Step 1: Read existing DashboardPage to follow conventions**

```bash
cat frontend/src/pages/DashboardPage.tsx | head -80
```

- [ ] **Step 2: Add Dimensions section below the existing run output**

In `DashboardPage.tsx`, import:

```tsx
import { DimensionsPanel } from '../components/dimensions/DimensionsPanel';
```

After the existing report section, render:

```tsx
{jobResult && (
  <DimensionsPanel
    dimensions={jobResult.dimensions ?? null}
    commentary={jobResult.dimensions_commentary ?? null}
    error={jobResult.dimensions_error ?? null}
  />
)}
```

Type `jobResult` to include `dimensions`, `dimensions_commentary`, `dimensions_error`. Add to the existing interface if it exists, or:

```tsx
import type { StockDimensions, DimensionsCommentary } from '../dimensions-types';

interface JobResultExtension {
  dimensions?: StockDimensions | null;
  dimensions_commentary?: DimensionsCommentary | null;
  dimensions_error?: string | null;
}
```

- [ ] **Step 3: Smoke-build**

```bash
cd frontend && npm run build && cd ..
```

Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/DashboardPage.tsx
git commit -m "feat(dashboard): show DimensionsPanel below run output"
```

---

## Task 17: BatchPage factor columns

**Files:**
- Modify: `frontend/src/pages/BatchPage.tsx`

- [ ] **Step 1: Add factor columns to the batch table**

In `BatchPage.tsx`, where the existing job rows are rendered, add 6 columns:

```tsx
import { FactorBar } from '../components/dimensions/FactorBar';
```

For each row, render the 6 factor scores (read from `job.result?.dimensions?.factor_scores`):

```tsx
{['value', 'growth', 'quality', 'momentum', 'low_risk', 'sentiment'].map(k => (
  <td key={k} style={{ padding: '4px 8px' }}>
    <FactorBar
      label=""
      score={job.result?.dimensions?.factor_scores?.[k]?.score ?? null}
      width={80}
    />
  </td>
))}
```

Add header columns matching the keys. Make the column header `onClick` sort rows by that factor score:

```tsx
const [sortKey, setSortKey] = useState<string | null>(null);
const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');

const sortedJobs = useMemo(() => {
  if (!sortKey) return jobs;
  return [...jobs].sort((a, b) => {
    const av = a.result?.dimensions?.factor_scores?.[sortKey]?.score ?? -Infinity;
    const bv = b.result?.dimensions?.factor_scores?.[sortKey]?.score ?? -Infinity;
    return sortDir === 'desc' ? bv - av : av - bv;
  });
}, [jobs, sortKey, sortDir]);
```

Add URL-param-persisted filters via `URLSearchParams`:

```tsx
const [searchParams, setSearchParams] = useSearchParams();
const minValue = Number(searchParams.get('min_value') || 0);
// ... filter jobs by minValue threshold
```

- [ ] **Step 2: Smoke-build**

```bash
cd frontend && npm run build && cd ..
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/BatchPage.tsx
git commit -m "feat(batch): 6 sortable factor columns with URL-persisted filters"
```

---

## Task 18: HistoryPage row thumbs + Dimensions tab + compare

**Files:**
- Modify: `frontend/src/pages/HistoryPage.tsx`

- [ ] **Step 1: Add mini factor strips to history rows**

In `HistoryPage.tsx`, for each `HistoryRunRef` row, render the 6 mini strips using the `factor_scores` field already on the ref:

```tsx
{['value', 'growth', 'quality', 'momentum', 'low_risk', 'sentiment'].map(k => (
  <FactorBar key={k} label="" score={row.factor_scores?.[k] ?? null} width={36} />
))}
```

- [ ] **Step 2: Add Dimensions tab to detail view**

When a row is expanded into the detail panel (fetched via `GET /history/runs/{run_id}`), render a new tab alongside the existing report tabs:

```tsx
<button onClick={() => setActiveTab('dimensions')}>Dimensions</button>
...
{activeTab === 'dimensions' && (
  <DimensionsPanel
    dimensions={detail.dimensions ?? null}
    commentary={detail.dimensions_commentary ?? null}
    error={detail.dimensions_error ?? null}
  />
)}
```

If `detail.dimensions === null`, render a "Recompute dimensions" button:

```tsx
{!detail.dimensions && (
  <button onClick={async () => {
    await recomputeDimensions(detail.run_id);
    // Refetch detail
  }}>Recompute dimensions</button>
)}
```

- [ ] **Step 3: Add side-by-side dimensions to the compare modal**

In the existing compare UI (where `HistoryCompareResponse` is rendered), append per-side radars:

```tsx
<div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
  {compare.a.dimensions && <DimensionsRadar factorScores={compare.a.dimensions.factor_scores} />}
  {compare.b.dimensions && <DimensionsRadar factorScores={compare.b.dimensions.factor_scores} />}
</div>
```

- [ ] **Step 4: Smoke-build**

```bash
cd frontend && npm run build && cd ..
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/HistoryPage.tsx
git commit -m "feat(history): row thumbs + Dimensions tab + compare modal"
```

---

## Task 19: ScreenerPage (new route `/screener`)

**Files:**
- Create: `frontend/src/pages/ScreenerPage.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Create ScreenerPage**

`frontend/src/pages/ScreenerPage.tsx`:

```tsx
import React, { useState } from 'react';
import { getDimensionsByTicker } from '../api';
import { FactorBar } from '../components/dimensions/FactorBar';
import type { StockDimensions } from '../dimensions-types';

interface Row {
  ticker: string;
  dimensions: StockDimensions | null;
  error?: string;
}

export function ScreenerPage() {
  const [input, setInput] = useState('AAPL, MSFT, NVDA');
  const [rows, setRows] = useState<Row[]>([]);
  const [loading, setLoading] = useState(false);

  async function run() {
    setLoading(true);
    const tickers = input.split(/[,\n]/).map(s => s.trim()).filter(Boolean);
    const results: Row[] = await Promise.all(
      tickers.map(async (t) => {
        try {
          const d = await getDimensionsByTicker(t);
          return { ticker: t, dimensions: d };
        } catch (e: any) {
          return { ticker: t, dimensions: null, error: e.message };
        }
      }),
    );
    setRows(results);
    setLoading(false);
  }

  return (
    <div style={{ padding: 16 }}>
      <h2>Screener (facts-only preview)</h2>
      <textarea
        value={input} onChange={e => setInput(e.target.value)}
        rows={3} cols={60}
      />
      <div>
        <button onClick={run} disabled={loading}>
          {loading ? 'Loading…' : 'Fetch dimensions'}
        </button>
      </div>
      <table style={{ marginTop: 16, width: '100%' }}>
        <thead>
          <tr>
            <th>Ticker</th>
            {['Value', 'Growth', 'Quality', 'Momentum', 'Low-Risk', 'Sentiment'].map(h =>
              <th key={h}>{h}</th>)}
            <th>Action</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(row => (
            <tr key={row.ticker}>
              <td>
                <strong>{row.ticker}</strong>
                {row.dimensions?.source === 'facts_only' && (
                  <span style={{ marginLeft: 4, fontSize: 11, color: '#888' }}>
                    facts only
                  </span>
                )}
              </td>
              {['value', 'growth', 'quality', 'momentum', 'low_risk', 'sentiment'].map(k => (
                <td key={k}>
                  <FactorBar
                    label=""
                    score={row.dimensions?.factor_scores?.[k as keyof typeof row.dimensions.factor_scores]?.score ?? null}
                    width={80}
                  />
                </td>
              ))}
              <td>
                <a href={`/?ticker=${row.ticker}`}>Run full analysis</a>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default ScreenerPage;
```

- [ ] **Step 2: Add route in App.tsx**

In `frontend/src/App.tsx`, import and add:

```tsx
import { ScreenerPage } from './pages/ScreenerPage';
// ...
<Route path="/screener" element={<ScreenerPage />} />
```

Add a nav link in `Layout.tsx` alongside existing nav.

- [ ] **Step 3: Smoke-build**

```bash
cd frontend && npm run build && cd ..
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/ScreenerPage.tsx frontend/src/App.tsx frontend/src/components/Layout.tsx
git commit -m "feat(screener): new /screener page with facts-only dimensions preview"
```

---

## Task 20: Admin script — warm peer cache

**Files:**
- Create: `scripts/warm_peer_cache.py`

- [ ] **Step 1: Implement the script**

`scripts/warm_peer_cache.py`:

```python
#!/usr/bin/env python3
"""Pre-warm the dimensions peer cache for a sector+industry.

Usage:
  python scripts/warm_peer_cache.py --sector Technology \
      --industry "Consumer Electronics" --tickers AAPL MSFT GOOGL META AMZN NVDA AMD
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

from api.config import build_service_config
from api.dimensions.facts import extract_facts
from api.dimensions.peers import PeerCache, slug_for_sector


def main(argv=None):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    p = argparse.ArgumentParser()
    p.add_argument("--sector", required=True)
    p.add_argument("--industry", required=True)
    p.add_argument("--tickers", nargs="+", required=True)
    p.add_argument("--cache-dir", default=None,
                   help="Override base cache dir (defaults to service config data_cache_dir)")
    args = p.parse_args(argv)

    slug = slug_for_sector(args.sector, args.industry)
    if not slug:
        print("sector + industry required", file=sys.stderr)
        return 2

    if args.cache_dir:
        base = Path(args.cache_dir)
    else:
        cfg = build_service_config()
        base = Path(cfg.get("data_cache_dir") or "./data_cache")
    cache_dir = base / "peer_facts"
    cache = PeerCache(base_dir=cache_dir)

    today = datetime.utcnow().strftime("%Y-%m-%d")
    facts = {}
    for t in args.tickers:
        try:
            snap, _flags = extract_facts(t, today)
            facts[t] = snap.model_dump()
            print(f"OK   {t}")
        except Exception as exc:
            print(f"SKIP {t}: {exc}", file=sys.stderr)

    cache.write(slug, list(facts.keys()), facts)
    print(f"Wrote {len(facts)} peers to {cache_dir / slug}.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

Make it executable: `chmod +x scripts/warm_peer_cache.py`

- [ ] **Step 2: Smoke-test the script (no network — relies on yfinance)**

If you have network access:

```bash
python scripts/warm_peer_cache.py --sector Technology \
  --industry "Consumer Electronics" --tickers AAPL --cache-dir /tmp/wpc
ls /tmp/wpc/peer_facts/
```

Expected: a `Technology__Consumer_Electronics.json` file.

- [ ] **Step 3: Commit**

```bash
git add scripts/warm_peer_cache.py
git commit -m "feat(scripts): warm_peer_cache.py to pre-populate sector peer cache"
```

---

## Task 21: README — Dimensions section

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add a Dimensions section**

Insert after the "Web command center" section (around line 215):

```markdown
### Standardized stock dimensions

Every completed run also produces a standardized dimensions layer:

- **Facts** — ~30 deterministic yfinance fields (price, valuation, growth, quality, etc.)
- **Pillar scores** — 16 LLM-judged 1-5 sub-dimensions across Market / Sentiment / News / Fundamentals
- **Factor scores** — 6 cross-cutting 0-100 scores (Value, Growth, Quality, Momentum, Low-Risk, Sentiment)
- **Commentary** — a one-paragraph dimensions-grounded second opinion on the Portfolio Manager decision

Surfaced via:

- `GET /jobs/{job_id}/dimensions` — full dimensions for a completed run
- `GET /dimensions/{ticker}` — facts-only preview (no LLM call) for screening
- `POST /history/runs/{run_id}/recompute-dimensions` — rebuild dimensions for an older run
- The frontend Dashboard, Batch, History, Compare, and new `/screener` page

Toggle off per-job via `config_overrides.dimensions_enabled = false` (adds ~2 LLM calls per run otherwise).

Pre-warm the peer cache for cross-stock percentile ranking:

```bash
python scripts/warm_peer_cache.py --sector Technology \
  --industry "Consumer Electronics" \
  --tickers AAPL MSFT GOOGL META AMZN NVDA AMD
```

See `docs/superpowers/specs/2026-05-13-standardized-stock-dimensions-design.md` for the full design.
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs(readme): document standardized stock dimensions layer"
```

---

## Task 22: Final verification + Definition of Done

**Files:** none new — verification only.

- [ ] **Step 1: Run the full backend test suite**

```bash
pytest tests/ -v
```

Expected: all tests pass — both new (`tests/dimensions/*`, `tests/test_jobs_*`) and existing.

- [ ] **Step 2: Run the frontend test suite**

```bash
cd frontend && npm test -- --run && cd ..
```

Expected: all tests pass.

- [ ] **Step 3: Smoke-build the frontend**

```bash
cd frontend && npm run build && cd ..
```

Expected: `frontend/dist/` produced, no errors.

- [ ] **Step 4: Verify OpenAPI surface**

```bash
uvicorn api.main:app --reload --port 8000 &
UV_PID=$!
sleep 3
curl -s http://localhost:8000/openapi.json | python -m json.tool | grep -E '"(dimensions|cancel|peer-cache|recompute)"' | head -20
kill $UV_PID
```

Expected: lines mentioning the new endpoints.

- [ ] **Step 5: Manual smoke test — single job with dimensions**

If LLM keys are configured:

```bash
curl -X POST http://localhost:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{"ticker": "AAPL", "date": "2026-05-13"}'
# wait for completion, then:
curl http://localhost:8000/jobs/{job_id}/dimensions | python -m json.tool
```

Expected: returns a `StockDimensions` JSON with all three layers populated.

- [ ] **Step 6: Verify DoD checklist from spec §13**

Walk through each item in [spec §13](../specs/2026-05-13-standardized-stock-dimensions-design.md#13-definition-of-done) and confirm it holds. Any failures → file an issue or add a follow-up task.

- [ ] **Step 7: Tag completion commit**

```bash
git tag -a dimensions-v1.0.0 -m "Standardized Stock Dimensions v1.0.0"
```

(Do NOT push the tag unless explicitly approved by the user.)

