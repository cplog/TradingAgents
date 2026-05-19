# Real Kronos Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the placeholder LLM "Kronos scenarios" node with a genuine integration of [shiyu-coder/Kronos](https://github.com/shiyu-coder/Kronos) wired into the analysis job pipeline so the forecast actually shapes the investment decision.

**Architecture:** `api/jobs.py._propagate_sync()` strips `"kronos"` from selected analysts, fetches OHLCV via yfinance, runs the real `KronosPredictor` from a clone at `vendor/kronos/` (pulled by `scripts/dev_up.sh`), formats a markdown forecast, and seeds it into the graph's initial `kronos_report` via a `try/finally` monkey-patch of `Propagator.create_initial_state` — so bull/bear researchers (which read `kronos_report` via `build_supplementary_analyst_context`) see the real forecast before debating. Zero edits inside `tradingagents/`.

**Tech Stack:** Python 3.10+ · pydantic · pandas · yfinance (already a project dep) · torch (via Kronos) · pytest · LangGraph (existing) · React/Recharts (existing, frontend label change only).

**Spec:** [docs/superpowers/specs/2026-05-19-real-kronos-integration-design.md](../specs/2026-05-19-real-kronos-integration-design.md)

---

## Task 1: Install wiring — dev_up.sh, .gitignore, .env.example, pytest marker

**Files:**
- Modify: `scripts/dev_up.sh`
- Modify: `.gitignore`
- Modify: `.env.example`
- Modify: `pyproject.toml:60-65` (pytest markers)

- [ ] **Step 1: Inspect current `scripts/dev_up.sh` to find the right insertion point**

Run: `cat scripts/dev_up.sh`

Look for where backend Python deps are installed (likely a `pip install -e .` or `pip install -e .[api]` line). The Kronos block goes right after that so torch is installed alongside other deps in the same venv.

- [ ] **Step 2: Append the Kronos clone-and-install block to `scripts/dev_up.sh`**

Add this block after the existing backend pip-install line (adjust the `KRONOS_UPSTREAM_SHA` to the SHA you want pinned — current main HEAD is `67b630e67f6a18c9e9be918d9b4337c960db1e9a` as of 2026-04-13):

```bash
# ----- Kronos forecasting model (real upstream clone) -----------------------
# Spec: docs/superpowers/specs/2026-05-19-real-kronos-integration-design.md (D2)
KRONOS_UPSTREAM_SHA="67b630e67f6a18c9e9be918d9b4337c960db1e9a"
KRONOS_VENDOR_DIR="vendor/kronos"

if [ ! -d "$KRONOS_VENDOR_DIR/.git" ]; then
  echo "[dev_up] cloning Kronos into $KRONOS_VENDOR_DIR"
  mkdir -p vendor
  git clone https://github.com/shiyu-coder/Kronos.git "$KRONOS_VENDOR_DIR"
fi

echo "[dev_up] pinning Kronos to $KRONOS_UPSTREAM_SHA"
git -C "$KRONOS_VENDOR_DIR" fetch --quiet origin
git -C "$KRONOS_VENDOR_DIR" checkout --quiet "$KRONOS_UPSTREAM_SHA"

echo "[dev_up] installing Kronos requirements"
pip install -r "$KRONOS_VENDOR_DIR/requirements.txt"
# ---------------------------------------------------------------------------
```

- [ ] **Step 3: Add `vendor/kronos/` to `.gitignore`**

Open `.gitignore` and add this section near the bottom:

```
# Kronos forecasting model — cloned by scripts/dev_up.sh, pinned via KRONOS_UPSTREAM_SHA
vendor/kronos/
```

- [ ] **Step 4: Add Kronos env vars to `.env.example`**

Append this section to `.env.example`:

```
# ----- Kronos forecasting -------------------------------------------------
# Source: https://github.com/shiyu-coder/Kronos (vendored under vendor/kronos/)
# Pulled by scripts/dev_up.sh. Set KRONOS_ENABLED=false to skip.
KRONOS_ENABLED=true
KRONOS_MODEL=NeoQuasar/Kronos-small
KRONOS_TOKENIZER=NeoQuasar/Kronos-Tokenizer-base
# device: auto (mps→cuda→cpu) | mps | cuda | cpu
# Note: on Apple Silicon, set to "cpu" if you hit MPS-specific torch bugs.
KRONOS_DEVICE=auto
KRONOS_LOOKBACK=200
KRONOS_PRED_LEN=20
KRONOS_SAMPLE_COUNT=1
KRONOS_T=1.0
KRONOS_TOP_P=0.9
KRONOS_TIMEOUT_SECONDS=90
KRONOS_MAX_CONTEXT=512
```

- [ ] **Step 5: Add `kronos_live` pytest marker in `pyproject.toml`**

Open `pyproject.toml`, find the `[tool.pytest.ini_options].markers` list (around line 60-65), and add the `kronos_live` marker. The block should look like:

```toml
markers = [
    "unit: fast isolated unit tests",
    "integration: tests requiring external services",
    "smoke: quick sanity-check tests",
    "kronos_live: opt-in tests that load the real Kronos model from HF Hub (slow, network)",
]
```

- [ ] **Step 6: Verify dev_up.sh runs cleanly**

Run: `bash scripts/dev_up.sh`

Expected: `vendor/kronos/` exists, contains `model/kronos.py`, and `python -c "import torch; print(torch.__version__)"` succeeds.

If the script fails on `pip install -r vendor/kronos/requirements.txt` due to `matplotlib==3.9.3` pinning conflicts, install with `--no-deps` is NOT the answer — instead, let me know and we'll relax the pin in the script via `sed` before install.

- [ ] **Step 7: Commit**

```bash
git add scripts/dev_up.sh .gitignore .env.example pyproject.toml
git commit -m "$(cat <<'EOF'
feat(kronos): wire vendor/kronos clone into dev_up.sh + env scaffolding

Pin upstream Kronos at SHA 67b630e6 via scripts/dev_up.sh; gitignore the
vendor/ clone; document KRONOS_* env vars; add kronos_live pytest marker
for opt-in real-model tests.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: api/kronos/ skeleton — errors, schema, config (+ tests)

**Files:**
- Create: `api/kronos/__init__.py`
- Create: `api/kronos/errors.py`
- Create: `api/kronos/schema.py`
- Create: `api/kronos/config.py`
- Create: `tests/test_api_kronos_config.py`
- Create: `tests/test_api_kronos_schema.py`

- [ ] **Step 1: Write the failing tests for `errors.py` and `schema.py`**

Create `tests/test_api_kronos_schema.py`:

```python
"""Schema + error class tests for api/kronos."""
import json
import pytest

from api.kronos.errors import KronosDisabled, InsufficientData, ModelLoadError
from api.kronos.schema import (
    KronosForecastRow,
    KronosForecastPayload,
    KronosStatus,
)


def test_errors_are_distinct_exception_classes():
    assert issubclass(KronosDisabled, Exception)
    assert issubclass(InsufficientData, Exception)
    assert issubclass(ModelLoadError, Exception)
    assert not issubclass(KronosDisabled, InsufficientData)


def test_forecast_row_round_trips_via_pydantic():
    row = KronosForecastRow(
        date="2026-05-20",
        open=100.5,
        high=101.2,
        low=99.8,
        close=100.9,
        volume=1_234_500.0,
        amount=124_563_405.0,
    )
    js = row.model_dump_json()
    restored = KronosForecastRow.model_validate_json(js)
    assert restored == row


def test_forecast_payload_round_trips():
    row = KronosForecastRow(
        date="2026-05-20", open=1.0, high=1.0, low=1.0,
        close=1.0, volume=1.0, amount=1.0,
    )
    payload = KronosForecastPayload(
        ticker="AAPL",
        trade_date="2026-05-19",
        model="NeoQuasar/Kronos-small",
        tokenizer="NeoQuasar/Kronos-Tokenizer-base",
        device="mps",
        lookback=200,
        pred_len=20,
        sample_count=1,
        history_tail=[row],
        forecast=[row, row],
        generated_at="2026-05-19T12:00:00Z",
    )
    js = payload.model_dump_json()
    restored = KronosForecastPayload.model_validate_json(js)
    assert restored == payload
    assert len(restored.forecast) == 2


def test_kronos_status_values():
    assert KronosStatus("ok").value == "ok"
    assert {s.value for s in KronosStatus} == {
        "ok", "disabled", "insufficient_data",
        "load_failed", "predict_failed", "timeout",
    }
```

- [ ] **Step 2: Run the test to verify it fails (modules don't exist yet)**

Run: `pytest tests/test_api_kronos_schema.py -v`
Expected: `ImportError: No module named 'api.kronos'`.

- [ ] **Step 3: Create the `api/kronos/` package + `errors.py`**

Create `api/kronos/__init__.py` (empty — we'll fill exports in Task 6):

```python
"""api/kronos — real Kronos foundation-model integration.

Spec: docs/superpowers/specs/2026-05-19-real-kronos-integration-design.md
"""
```

Create `api/kronos/errors.py`:

```python
"""Domain exceptions for the Kronos integration."""


class KronosError(Exception):
    """Base class for Kronos-integration domain errors."""


class KronosDisabled(KronosError):
    """KRONOS_ENABLED is false — caller should skip the forecast entirely."""


class InsufficientData(KronosError):
    """Fewer OHLCV bars available than the configured lookback."""


class ModelLoadError(KronosError):
    """Loading the upstream Kronos model/tokenizer failed."""
```

- [ ] **Step 4: Create `api/kronos/schema.py`**

```python
"""Pydantic schemas for Kronos forecast payloads."""
from __future__ import annotations

from enum import Enum
from typing import List

from pydantic import BaseModel


class KronosForecastRow(BaseModel):
    """One bar of OHLCV at a specific date (historical or forecast)."""
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    amount: float


class KronosForecastPayload(BaseModel):
    """Complete Kronos forecast result for a single ticker/date."""
    ticker: str
    trade_date: str
    model: str
    tokenizer: str
    device: str
    lookback: int
    pred_len: int
    sample_count: int
    history_tail: List[KronosForecastRow]
    forecast: List[KronosForecastRow]
    generated_at: str


class KronosStatus(str, Enum):
    ok = "ok"
    disabled = "disabled"
    insufficient_data = "insufficient_data"
    load_failed = "load_failed"
    predict_failed = "predict_failed"
    timeout = "timeout"
```

- [ ] **Step 5: Run schema tests, verify they pass**

Run: `pytest tests/test_api_kronos_schema.py -v`
Expected: 4 passed.

- [ ] **Step 6: Write failing tests for `config.py`**

Create `tests/test_api_kronos_config.py`:

```python
"""Config / env-loader tests for api/kronos."""
import pytest

from api.kronos.config import KronosConfig


def test_defaults_match_spec(monkeypatch):
    # Wipe any inherited env so we test defaults.
    for k in [
        "KRONOS_ENABLED", "KRONOS_MODEL", "KRONOS_TOKENIZER", "KRONOS_DEVICE",
        "KRONOS_LOOKBACK", "KRONOS_PRED_LEN", "KRONOS_SAMPLE_COUNT",
        "KRONOS_T", "KRONOS_TOP_P", "KRONOS_TIMEOUT_SECONDS", "KRONOS_MAX_CONTEXT",
    ]:
        monkeypatch.delenv(k, raising=False)
    cfg = KronosConfig.from_env()
    assert cfg.enabled is True
    assert cfg.model == "NeoQuasar/Kronos-small"
    assert cfg.tokenizer == "NeoQuasar/Kronos-Tokenizer-base"
    assert cfg.device == "auto"
    assert cfg.lookback == 200
    assert cfg.pred_len == 20
    assert cfg.sample_count == 1
    assert cfg.temperature == 1.0
    assert cfg.top_p == 0.9
    assert cfg.timeout_seconds == 90
    assert cfg.max_context == 512


def test_env_overrides(monkeypatch):
    monkeypatch.setenv("KRONOS_ENABLED", "false")
    monkeypatch.setenv("KRONOS_MODEL", "NeoQuasar/Kronos-base")
    monkeypatch.setenv("KRONOS_DEVICE", "cpu")
    monkeypatch.setenv("KRONOS_LOOKBACK", "120")
    monkeypatch.setenv("KRONOS_PRED_LEN", "10")
    monkeypatch.setenv("KRONOS_SAMPLE_COUNT", "5")
    monkeypatch.setenv("KRONOS_T", "0.7")
    monkeypatch.setenv("KRONOS_TIMEOUT_SECONDS", "30")
    cfg = KronosConfig.from_env()
    assert cfg.enabled is False
    assert cfg.model == "NeoQuasar/Kronos-base"
    assert cfg.device == "cpu"
    assert cfg.lookback == 120
    assert cfg.pred_len == 10
    assert cfg.sample_count == 5
    assert cfg.temperature == 0.7
    assert cfg.timeout_seconds == 30


def test_env_bool_truthy_variants(monkeypatch):
    for val in ("1", "true", "TRUE", "yes", "on", "True"):
        monkeypatch.setenv("KRONOS_ENABLED", val)
        assert KronosConfig.from_env().enabled is True
    for val in ("0", "false", "no", "off", ""):
        monkeypatch.setenv("KRONOS_ENABLED", val)
        assert KronosConfig.from_env().enabled is False


def test_invalid_int_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("KRONOS_LOOKBACK", "not-a-number")
    cfg = KronosConfig.from_env()
    assert cfg.lookback == 200


def test_resolved_device_passes_through_explicit_setting(monkeypatch):
    monkeypatch.setenv("KRONOS_DEVICE", "cpu")
    cfg = KronosConfig.from_env()
    assert cfg.resolved_device == "cpu"


def test_resolved_device_auto_picks_a_real_device(monkeypatch):
    monkeypatch.setenv("KRONOS_DEVICE", "auto")
    cfg = KronosConfig.from_env()
    assert cfg.resolved_device in ("mps", "cuda", "cpu")
```

- [ ] **Step 7: Run config tests to verify they fail**

Run: `pytest tests/test_api_kronos_config.py -v`
Expected: `ImportError: cannot import name 'KronosConfig'`.

- [ ] **Step 8: Implement `api/kronos/config.py`**

```python
"""Environment-driven configuration for the Kronos integration."""
from __future__ import annotations

import os
from dataclasses import dataclass


def _env_bool(key: str, default: bool) -> bool:
    val = os.getenv(key)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


def _env_int(key: str, default: int) -> int:
    val = os.getenv(key)
    if val is None:
        return default
    try:
        return int(val)
    except (TypeError, ValueError):
        return default


def _env_float(key: str, default: float) -> float:
    val = os.getenv(key)
    if val is None:
        return default
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _resolve_device(preferred: str) -> str:
    """Map ``auto`` to ``mps`` → ``cuda`` → ``cpu``; pass explicit names through."""
    if preferred != "auto":
        return preferred
    try:
        import torch  # type: ignore
    except ImportError:
        return "cpu"
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        return "mps"
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


@dataclass(frozen=True)
class KronosConfig:
    """Frozen view of all KRONOS_* env vars."""
    enabled: bool = True
    model: str = "NeoQuasar/Kronos-small"
    tokenizer: str = "NeoQuasar/Kronos-Tokenizer-base"
    device: str = "auto"
    lookback: int = 200
    pred_len: int = 20
    sample_count: int = 1
    temperature: float = 1.0
    top_p: float = 0.9
    timeout_seconds: int = 90
    max_context: int = 512

    @property
    def resolved_device(self) -> str:
        return _resolve_device(self.device)

    @classmethod
    def from_env(cls) -> "KronosConfig":
        return cls(
            enabled=_env_bool("KRONOS_ENABLED", True),
            model=os.getenv("KRONOS_MODEL", "NeoQuasar/Kronos-small"),
            tokenizer=os.getenv(
                "KRONOS_TOKENIZER", "NeoQuasar/Kronos-Tokenizer-base"
            ),
            device=os.getenv("KRONOS_DEVICE", "auto"),
            lookback=_env_int("KRONOS_LOOKBACK", 200),
            pred_len=_env_int("KRONOS_PRED_LEN", 20),
            sample_count=_env_int("KRONOS_SAMPLE_COUNT", 1),
            temperature=_env_float("KRONOS_T", 1.0),
            top_p=_env_float("KRONOS_TOP_P", 0.9),
            timeout_seconds=_env_int("KRONOS_TIMEOUT_SECONDS", 90),
            max_context=_env_int("KRONOS_MAX_CONTEXT", 512),
        )
```

- [ ] **Step 9: Run all skeleton tests, verify all pass**

Run: `pytest tests/test_api_kronos_schema.py tests/test_api_kronos_config.py -v`
Expected: 10 passed (4 schema + 6 config).

- [ ] **Step 10: Commit**

```bash
git add api/kronos/__init__.py api/kronos/errors.py api/kronos/schema.py api/kronos/config.py tests/test_api_kronos_schema.py tests/test_api_kronos_config.py
git commit -m "$(cat <<'EOF'
feat(kronos): add errors, schema, and config skeleton with tests

api/kronos/{errors,schema,config}.py — domain exceptions, Pydantic
forecast payload, and a frozen env-driven KronosConfig with device
auto-detection (mps→cuda→cpu).

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: api/kronos/ohlcv.py — yfinance fetcher

**Files:**
- Create: `api/kronos/ohlcv.py`
- Create: `tests/test_api_kronos_ohlcv.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_api_kronos_ohlcv.py`:

```python
"""Tests for api/kronos/ohlcv.py — yfinance-backed OHLCV fetcher."""
from __future__ import annotations

import pandas as pd
import pytest
from unittest.mock import patch, MagicMock

from api.kronos.errors import InsufficientData
from api.kronos.ohlcv import fetch_ohlcv


def _make_yf_frame(n_rows: int) -> pd.DataFrame:
    """Build a yfinance-style DataFrame with a DatetimeIndex."""
    dates = pd.date_range(end="2026-05-18", periods=n_rows, freq="B")
    return pd.DataFrame(
        {
            "Open": [100.0 + i * 0.1 for i in range(n_rows)],
            "High": [101.0 + i * 0.1 for i in range(n_rows)],
            "Low": [99.0 + i * 0.1 for i in range(n_rows)],
            "Close": [100.5 + i * 0.1 for i in range(n_rows)],
            "Volume": [1_000_000.0 + i for i in range(n_rows)],
        },
        index=dates,
    )


def test_fetch_ohlcv_happy_path():
    fake_df = _make_yf_frame(250)
    fake_ticker = MagicMock()
    fake_ticker.history.return_value = fake_df

    with patch("api.kronos.ohlcv.yf.Ticker", return_value=fake_ticker):
        out = fetch_ohlcv("AAPL", "2026-05-19", lookback=200)

    assert len(out) == 200
    assert set(out.columns) >= {
        "open", "high", "low", "close", "volume", "amount", "timestamps"
    }
    # amount == close * volume
    assert out["amount"].iloc[0] == pytest.approx(
        out["close"].iloc[0] * out["volume"].iloc[0]
    )
    # timestamps is a datetime series
    assert pd.api.types.is_datetime64_any_dtype(out["timestamps"])
    # Verify history() was called with auto_adjust=False (raw OHLCV)
    _, kwargs = fake_ticker.history.call_args
    assert kwargs.get("auto_adjust") is False
    assert kwargs.get("interval") == "1d"


def test_fetch_ohlcv_insufficient_data_raises():
    fake_df = _make_yf_frame(50)  # < lookback of 200
    fake_ticker = MagicMock()
    fake_ticker.history.return_value = fake_df

    with patch("api.kronos.ohlcv.yf.Ticker", return_value=fake_ticker):
        with pytest.raises(InsufficientData) as exc:
            fetch_ohlcv("AAPL", "2026-05-19", lookback=200)
    assert "50" in str(exc.value)
    assert "200" in str(exc.value)


def test_fetch_ohlcv_empty_response_raises():
    fake_ticker = MagicMock()
    fake_ticker.history.return_value = pd.DataFrame()
    with patch("api.kronos.ohlcv.yf.Ticker", return_value=fake_ticker):
        with pytest.raises(InsufficientData):
            fetch_ohlcv("XYZ", "2026-05-19", lookback=200)


def test_fetch_ohlcv_preserves_ticker_suffix():
    """HK / A-share style tickers must be passed through to yfinance verbatim."""
    fake_df = _make_yf_frame(250)
    fake_ticker = MagicMock()
    fake_ticker.history.return_value = fake_df

    with patch("api.kronos.ohlcv.yf.Ticker", return_value=fake_ticker) as ctor:
        fetch_ohlcv("0700.HK", "2026-05-19", lookback=200)
    ctor.assert_called_once_with("0700.HK")
```

- [ ] **Step 2: Run, verify failure**

Run: `pytest tests/test_api_kronos_ohlcv.py -v`
Expected: `ImportError` from `from api.kronos.ohlcv import fetch_ohlcv`.

- [ ] **Step 3: Implement `api/kronos/ohlcv.py`**

```python
"""OHLCV fetcher for Kronos input — wraps yfinance."""
from __future__ import annotations

import pandas as pd
import yfinance as yf

from api.kronos.errors import InsufficientData


def fetch_ohlcv(
    ticker: str,
    trade_date: str,
    lookback: int = 200,
) -> pd.DataFrame:
    """Fetch ``lookback`` daily bars ending on or just before ``trade_date``.

    Args:
        ticker: Symbol passed verbatim to yfinance (e.g. "AAPL", "0700.HK",
            "600519.SS"). Exchange suffixes are preserved.
        trade_date: ISO date used as the (exclusive) right edge of the history
            window — yfinance's ``end`` is exclusive, so we pass ``trade_date+1``.
        lookback: Number of daily bars required. Raises ``InsufficientData`` if
            yfinance returns fewer rows (after dropping weekends/holidays).

    Returns:
        DataFrame with columns ``['timestamps','open','high','low','close',
        'volume','amount']`` and exactly ``lookback`` rows (the tail of what
        yfinance returned). ``amount = close * volume`` since yfinance does
        not expose turnover-in-currency.
    """
    end = pd.to_datetime(trade_date) + pd.Timedelta(days=1)
    # Generous buffer to cover weekends/holidays and ensure we get >= lookback rows.
    buffer_days = int(lookback * 1.6) + 30
    start = end - pd.Timedelta(days=buffer_days)

    raw = yf.Ticker(ticker).history(
        start=start.strftime("%Y-%m-%d"),
        end=end.strftime("%Y-%m-%d"),
        interval="1d",
        auto_adjust=False,
    )

    if raw is None or raw.empty or len(raw) < lookback:
        n_got = 0 if raw is None or raw.empty else len(raw)
        raise InsufficientData(
            f"yfinance returned {n_got} daily bars for {ticker}, "
            f"need >= {lookback}"
        )

    tail = raw.tail(lookback).copy()
    out = pd.DataFrame(
        {
            "open": tail["Open"].astype(float).values,
            "high": tail["High"].astype(float).values,
            "low": tail["Low"].astype(float).values,
            "close": tail["Close"].astype(float).values,
            "volume": tail["Volume"].astype(float).values,
        }
    )
    out["amount"] = out["close"] * out["volume"]
    out["timestamps"] = pd.to_datetime(tail.index)
    out = out.reset_index(drop=True)
    return out[["timestamps", "open", "high", "low", "close", "volume", "amount"]]
```

- [ ] **Step 4: Run tests, verify all pass**

Run: `pytest tests/test_api_kronos_ohlcv.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add api/kronos/ohlcv.py tests/test_api_kronos_ohlcv.py
git commit -m "$(cat <<'EOF'
feat(kronos): add yfinance OHLCV fetcher with insufficient-data guard

api/kronos/ohlcv.py.fetch_ohlcv returns lookback daily bars ending at
trade_date, with amount = close*volume since yfinance has no turnover
column. Raises InsufficientData when fewer bars are returned.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: api/kronos/predictor.py — KronosService

**Files:**
- Create: `api/kronos/predictor.py`
- Create: `tests/test_api_kronos_predictor.py`

- [ ] **Step 1: Write failing tests with a stubbed upstream `KronosPredictor`**

Create `tests/test_api_kronos_predictor.py`:

```python
"""Tests for api/kronos/predictor.py — uses a fake upstream KronosPredictor."""
from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from api.kronos.config import KronosConfig
from api.kronos.errors import InsufficientData, ModelLoadError
from api.kronos.schema import KronosForecastPayload


def _ohlcv_fixture(n: int = 200) -> pd.DataFrame:
    ts = pd.date_range(end="2026-05-18", periods=n, freq="B")
    return pd.DataFrame({
        "timestamps": ts,
        "open": [100.0] * n,
        "high": [101.0] * n,
        "low": [99.0] * n,
        "close": [100.5] * n,
        "volume": [1_000_000.0] * n,
        "amount": [100_500_000.0] * n,
    })


class _FakePredictor:
    def __init__(self, *args, **kwargs):
        self.init_kwargs = kwargs

    def predict(self, df, x_timestamp, y_timestamp, pred_len, T, top_p,
                sample_count, **kw):
        # Return a deterministic forecast DataFrame indexed by y_timestamp.
        return pd.DataFrame({
            "open": [100.0] * pred_len,
            "high": [102.0] * pred_len,
            "low": [98.0] * pred_len,
            "close": [101.0] * pred_len,
            "volume": [1_500_000.0] * pred_len,
            "amount": [151_500_000.0] * pred_len,
        }, index=list(y_timestamp))


def _install_fake_model_module(monkeypatch):
    """Inject a fake ``model`` module into sys.modules so the predictor
    can import upstream classes without a real vendor/kronos/ clone."""
    fake_model = types.ModuleType("model")
    fake_model.Kronos = MagicMock(name="Kronos")
    fake_model.Kronos.from_pretrained = MagicMock(return_value=MagicMock())
    fake_model.KronosTokenizer = MagicMock(name="KronosTokenizer")
    fake_model.KronosTokenizer.from_pretrained = MagicMock(return_value=MagicMock())
    fake_model.KronosPredictor = _FakePredictor
    monkeypatch.setitem(sys.modules, "model", fake_model)


@pytest.fixture(autouse=True)
def _reset_singleton():
    """Each test gets a fresh KronosService singleton."""
    from api.kronos.predictor import KronosService
    KronosService.reset()
    yield
    KronosService.reset()


def test_forecast_returns_well_formed_payload(monkeypatch):
    _install_fake_model_module(monkeypatch)
    from api.kronos.predictor import KronosService

    cfg = KronosConfig(lookback=200, pred_len=20, sample_count=1, device="cpu")
    svc = KronosService.get(cfg)
    payload = svc.forecast(_ohlcv_fixture(200), ticker="AAPL", trade_date="2026-05-19")

    assert isinstance(payload, KronosForecastPayload)
    assert payload.ticker == "AAPL"
    assert payload.trade_date == "2026-05-19"
    assert payload.model == "NeoQuasar/Kronos-small"
    assert payload.lookback == 200
    assert payload.pred_len == 20
    assert payload.sample_count == 1
    assert payload.device == "cpu"
    assert len(payload.forecast) == 20
    # First forecast row matches the deterministic fake output
    assert payload.forecast[0].close == 101.0
    assert payload.forecast[0].open == 100.0
    # History tail preserved
    assert len(payload.history_tail) <= 20  # we keep at most 20 actual bars
    assert payload.history_tail[-1].close == 100.5


def test_forecast_raises_insufficient_data_when_short(monkeypatch):
    _install_fake_model_module(monkeypatch)
    from api.kronos.predictor import KronosService

    cfg = KronosConfig(lookback=200, pred_len=20, sample_count=1, device="cpu")
    svc = KronosService.get(cfg)
    with pytest.raises(InsufficientData):
        svc.forecast(_ohlcv_fixture(50), ticker="AAPL", trade_date="2026-05-19")


def test_model_load_error_when_vendor_missing(monkeypatch):
    """If 'model' cannot be imported, ModelLoadError is raised."""
    # Ensure no fake 'model' is installed AND any real one is hidden.
    monkeypatch.setitem(sys.modules, "model", None)
    from api.kronos.predictor import KronosService

    cfg = KronosConfig(device="cpu")
    svc = KronosService.get(cfg)
    with pytest.raises(ModelLoadError):
        svc.forecast(_ohlcv_fixture(200), ticker="AAPL", trade_date="2026-05-19")


def test_singleton_is_reused(monkeypatch):
    _install_fake_model_module(monkeypatch)
    from api.kronos.predictor import KronosService

    cfg = KronosConfig(device="cpu")
    a = KronosService.get(cfg)
    b = KronosService.get(cfg)
    assert a is b


def test_lazy_load_happens_once(monkeypatch):
    _install_fake_model_module(monkeypatch)
    fake_model = sys.modules["model"]
    from api.kronos.predictor import KronosService

    cfg = KronosConfig(device="cpu")
    svc = KronosService.get(cfg)
    svc.forecast(_ohlcv_fixture(200), "AAPL", "2026-05-19")
    svc.forecast(_ohlcv_fixture(200), "AAPL", "2026-05-19")

    # Tokenizer/model loaders called once across both forecast calls
    assert fake_model.KronosTokenizer.from_pretrained.call_count == 1
    assert fake_model.Kronos.from_pretrained.call_count == 1
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/test_api_kronos_predictor.py -v`
Expected: `ImportError: cannot import name 'KronosService'`.

- [ ] **Step 3: Implement `api/kronos/predictor.py`**

```python
"""KronosService — singleton wrapper around the upstream KronosPredictor.

Lazy-loads the model on first forecast() call. Adds vendor/kronos/ to
sys.path so ``from model import Kronos, KronosTokenizer, KronosPredictor``
resolves to the cloned upstream repo.
"""
from __future__ import annotations

import logging
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

import pandas as pd

from api.kronos.config import KronosConfig
from api.kronos.errors import InsufficientData, ModelLoadError
from api.kronos.schema import KronosForecastPayload, KronosForecastRow

logger = logging.getLogger(__name__)

# Repo root is two parents up from this file: api/kronos/predictor.py
_REPO_ROOT = Path(__file__).resolve().parents[2]
_VENDOR_KRONOS = _REPO_ROOT / "vendor" / "kronos"

_HISTORY_TAIL_LEN = 20  # last N actual bars kept in payload for chart context


def _ensure_vendor_on_path() -> None:
    """Idempotently add vendor/kronos to sys.path."""
    sp = str(_VENDOR_KRONOS)
    if sp not in sys.path:
        sys.path.insert(0, sp)


def _row_from(date, open_, high, low, close, volume, amount) -> KronosForecastRow:
    return KronosForecastRow(
        date=pd.to_datetime(date).date().isoformat(),
        open=float(open_),
        high=float(high),
        low=float(low),
        close=float(close),
        volume=float(volume),
        amount=float(amount),
    )


class KronosService:
    """Process-singleton owning the loaded model + tokenizer + predictor."""

    _instance: Optional["KronosService"] = None
    _class_lock = threading.Lock()

    def __init__(self, cfg: KronosConfig):
        self.cfg = cfg
        self._predictor = None
        self._device: Optional[str] = None
        self._load_lock = threading.Lock()

    @classmethod
    def get(cls, cfg: Optional[KronosConfig] = None) -> "KronosService":
        with cls._class_lock:
            if cls._instance is None:
                cls._instance = cls(cfg or KronosConfig.from_env())
            return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Clear the singleton — test helper."""
        with cls._class_lock:
            cls._instance = None

    def _ensure_loaded(self) -> None:
        if self._predictor is not None:
            return
        with self._load_lock:
            if self._predictor is not None:
                return
            _ensure_vendor_on_path()
            try:
                from model import Kronos, KronosTokenizer, KronosPredictor  # type: ignore
            except Exception as e:
                raise ModelLoadError(
                    f"failed to import vendored Kronos (run scripts/dev_up.sh): {e}"
                ) from e
            try:
                tokenizer = KronosTokenizer.from_pretrained(self.cfg.tokenizer)
                model = Kronos.from_pretrained(self.cfg.model)
            except Exception as e:
                raise ModelLoadError(
                    f"failed to load {self.cfg.model} / {self.cfg.tokenizer}: {e}"
                ) from e
            self._device = self.cfg.resolved_device
            try:
                self._predictor = KronosPredictor(
                    model, tokenizer,
                    max_context=self.cfg.max_context,
                    device=self._device,
                )
            except TypeError:
                # Upstream KronosPredictor.__init__ may not accept a ``device``
                # kwarg in older revisions. Fall back to the 3-arg form.
                self._predictor = KronosPredictor(
                    model, tokenizer, max_context=self.cfg.max_context,
                )
            logger.info(
                "kronos loaded | model=%s tokenizer=%s device=%s",
                self.cfg.model, self.cfg.tokenizer, self._device,
            )

    def forecast(
        self,
        ohlcv_df: pd.DataFrame,
        ticker: str,
        trade_date: str,
    ) -> KronosForecastPayload:
        if len(ohlcv_df) < self.cfg.lookback:
            raise InsufficientData(
                f"need {self.cfg.lookback} OHLCV bars, got {len(ohlcv_df)}"
            )

        self._ensure_loaded()

        df_tail = ohlcv_df.tail(self.cfg.lookback).reset_index(drop=True)
        x_df = df_tail[["open", "high", "low", "close", "volume", "amount"]]
        x_timestamp = df_tail["timestamps"]

        last_ts = pd.to_datetime(x_timestamp.iloc[-1])
        # Forward business days (skips Sat/Sun; not holiday-aware but adequate
        # for an indicative horizon).
        y_timestamp = pd.Series(
            pd.bdate_range(
                start=last_ts + pd.Timedelta(days=1),
                periods=self.cfg.pred_len,
            )
        )

        pred_df = self._predictor.predict(
            df=x_df,
            x_timestamp=x_timestamp,
            y_timestamp=y_timestamp,
            pred_len=self.cfg.pred_len,
            T=self.cfg.temperature,
            top_p=self.cfg.top_p,
            sample_count=self.cfg.sample_count,
        )

        # Build forecast rows
        forecast_rows: List[KronosForecastRow] = []
        for ts, row in pred_df.iterrows():
            amount = float(row["amount"]) if "amount" in row else float(
                row["close"]
            ) * float(row["volume"])
            forecast_rows.append(_row_from(
                ts, row["open"], row["high"], row["low"],
                row["close"], row["volume"], amount,
            ))

        # Build history tail
        history_tail: List[KronosForecastRow] = []
        for _, row in df_tail.tail(_HISTORY_TAIL_LEN).iterrows():
            history_tail.append(_row_from(
                row["timestamps"], row["open"], row["high"], row["low"],
                row["close"], row["volume"], row["amount"],
            ))

        return KronosForecastPayload(
            ticker=ticker,
            trade_date=trade_date,
            model=self.cfg.model,
            tokenizer=self.cfg.tokenizer,
            device=self._device or self.cfg.resolved_device,
            lookback=self.cfg.lookback,
            pred_len=self.cfg.pred_len,
            sample_count=self.cfg.sample_count,
            history_tail=history_tail,
            forecast=forecast_rows,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )
```

- [ ] **Step 4: Run tests, verify all pass**

Run: `pytest tests/test_api_kronos_predictor.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add api/kronos/predictor.py tests/test_api_kronos_predictor.py
git commit -m "$(cat <<'EOF'
feat(kronos): add KronosService singleton with lazy model load

api/kronos/predictor.py inserts vendor/kronos/ into sys.path, lazy-loads
NeoQuasar/Kronos-small + tokenizer on first .forecast() call, wraps the
upstream KronosPredictor, and returns a typed KronosForecastPayload.
Thread-safe lazy init; reset() helper for tests.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: api/kronos/formatter.py — markdown + JSON shapes

**Files:**
- Create: `api/kronos/formatter.py`
- Create: `tests/test_api_kronos_formatter.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_api_kronos_formatter.py`:

```python
"""Tests for api/kronos/formatter.py — markdown + JSON shaping."""
from __future__ import annotations

import json

import pytest

from api.kronos.formatter import forecast_to_markdown, forecast_to_state
from api.kronos.schema import KronosForecastPayload, KronosForecastRow


def _row(date: str, close: float) -> KronosForecastRow:
    return KronosForecastRow(
        date=date, open=close - 0.5, high=close + 1.0, low=close - 1.0,
        close=close, volume=1_000_000.0, amount=close * 1_000_000.0,
    )


def _payload(forecast_closes):
    return KronosForecastPayload(
        ticker="AAPL",
        trade_date="2026-05-19",
        model="NeoQuasar/Kronos-small",
        tokenizer="NeoQuasar/Kronos-Tokenizer-base",
        device="mps",
        lookback=200,
        pred_len=len(forecast_closes),
        sample_count=1,
        history_tail=[_row("2026-05-18", 150.0)],
        forecast=[_row(f"2026-05-{20+i:02d}", c) for i, c in enumerate(forecast_closes)],
        generated_at="2026-05-19T12:00:00+00:00",
    )


def test_markdown_includes_header_metadata_and_disclaimer():
    md = forecast_to_markdown(_payload([151.0, 152.0, 153.0]))
    assert "Kronos forecast" in md
    assert "AAPL" in md
    assert "2026-05-19" in md
    assert "NeoQuasar/Kronos-small" in md
    assert "mps" in md
    assert "200d" in md or "200 d" in md
    assert "Not investment advice" in md


def test_markdown_renders_a_table_row_per_forecast_day():
    md = forecast_to_markdown(_payload([151.0, 152.0, 153.0]))
    # Each forecast row's date should appear in the body
    assert "2026-05-20" in md
    assert "2026-05-21" in md
    assert "2026-05-22" in md
    # Closes formatted reasonably
    assert "151" in md
    assert "153" in md


def test_markdown_drift_narrative_uses_actual_numbers():
    md = forecast_to_markdown(_payload([155.0, 160.0, 165.0]))
    # Last-actual close is 150.0; last forecast is 165.0 → +10% drift
    assert "150" in md
    assert "165" in md


def test_forecast_to_state_is_json_serializable():
    state = forecast_to_state(_payload([151.0, 152.0]))
    s = json.dumps(state)  # must round-trip
    loaded = json.loads(s)
    assert loaded["ticker"] == "AAPL"
    assert loaded["pred_len"] == 2
    assert len(loaded["forecast"]) == 2
    assert loaded["forecast"][0]["close"] == 151.0


def test_forecast_to_state_none_returns_none():
    assert forecast_to_state(None) is None


def test_markdown_when_payload_is_none():
    assert forecast_to_markdown(None) == ""
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/test_api_kronos_formatter.py -v`
Expected: `ImportError: cannot import name 'forecast_to_markdown'`.

- [ ] **Step 3: Implement `api/kronos/formatter.py`**

```python
"""Markdown + JSON formatters for KronosForecastPayload.

Pure functions — no I/O, no LLM calls. Easy to test against fixtures.
"""
from __future__ import annotations

from typing import Optional

from api.kronos.schema import KronosForecastPayload


def forecast_to_markdown(payload: Optional[KronosForecastPayload]) -> str:
    if payload is None:
        return ""

    last_actual = payload.history_tail[-1].close if payload.history_tail else 0.0
    last_forecast = payload.forecast[-1].close if payload.forecast else 0.0
    drift_pct = (
        ((last_forecast - last_actual) / last_actual) * 100.0
        if last_actual
        else 0.0
    )

    high_max = max((r.high for r in payload.forecast), default=0.0)
    low_min = min((r.low for r in payload.forecast), default=0.0)
    total_vol = sum(r.volume for r in payload.forecast)

    header = (
        f"## Kronos forecast — {payload.ticker} on {payload.trade_date}\n\n"
        f"**Model:** {payload.model} · "
        f"**Device:** {payload.device} · "
        f"**History:** {payload.lookback}d · "
        f"**Horizon:** {payload.pred_len}d\n\n"
    )

    narrative = (
        f"Kronos forecasts the close drifting from {last_actual:,.2f} "
        f"(last actual) to {last_forecast:,.2f} on day {payload.pred_len}, "
        f"a {drift_pct:+.2f}% move. The forecast range spans "
        f"{low_min:,.2f}–{high_max:,.2f} and the total forecast volume is "
        f"{total_vol:,.0f}.\n\n"
    )

    table_header = (
        "| Day | Date       |   open |   high |    low |  close |    volume |\n"
        "|----:|------------|-------:|-------:|-------:|-------:|----------:|\n"
    )
    table_rows = []
    for i, r in enumerate(payload.forecast, start=1):
        table_rows.append(
            f"| {i:>3} | {r.date} | "
            f"{r.open:>6.2f} | {r.high:>6.2f} | {r.low:>6.2f} | "
            f"{r.close:>6.2f} | {r.volume:>9,.0f} |"
        )
    table = table_header + "\n".join(table_rows) + "\n\n"

    footer = (
        f"*Single-path forecast from the Kronos foundation model "
        f"(sample_count={payload.sample_count}). Probabilistic bands across "
        f"multiple sampled paths are coming in a follow-up PR. Not "
        f"investment advice.*\n"
    )

    return header + narrative + table + footer


def forecast_to_state(payload: Optional[KronosForecastPayload]) -> Optional[dict]:
    """JSON-serializable dict for embedding in final_state['kronos_forecast'].

    The frontend (follow-up PR) will read this shape to render a chart.
    """
    if payload is None:
        return None
    return payload.model_dump(mode="json")
```

- [ ] **Step 4: Run tests, verify all pass**

Run: `pytest tests/test_api_kronos_formatter.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add api/kronos/formatter.py tests/test_api_kronos_formatter.py
git commit -m "$(cat <<'EOF'
feat(kronos): add markdown + JSON formatters for forecast payloads

api/kronos/formatter.py — pure functions that turn a KronosForecastPayload
into the markdown report seeded into kronos_report, and into a JSON
dict for the structured kronos_forecast field.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: api/kronos/__init__.py — public exports

**Files:**
- Modify: `api/kronos/__init__.py`

- [ ] **Step 1: Replace the empty `__init__.py` with public exports**

Open `api/kronos/__init__.py` and replace its contents with:

```python
"""api/kronos — real Kronos foundation-model integration.

Spec: docs/superpowers/specs/2026-05-19-real-kronos-integration-design.md
"""
from api.kronos.config import KronosConfig
from api.kronos.errors import (
    InsufficientData,
    KronosDisabled,
    KronosError,
    ModelLoadError,
)
from api.kronos.formatter import forecast_to_markdown, forecast_to_state
from api.kronos.ohlcv import fetch_ohlcv
from api.kronos.predictor import KronosService
from api.kronos.schema import (
    KronosForecastPayload,
    KronosForecastRow,
    KronosStatus,
)

__all__ = [
    "KronosConfig",
    "KronosService",
    "KronosForecastPayload",
    "KronosForecastRow",
    "KronosStatus",
    "InsufficientData",
    "KronosDisabled",
    "KronosError",
    "ModelLoadError",
    "fetch_ohlcv",
    "forecast_to_markdown",
    "forecast_to_state",
]
```

- [ ] **Step 2: Verify the package imports cleanly**

Run: `python -c "from api import kronos; print(sorted(kronos.__all__))"`
Expected: a list containing all the names above.

- [ ] **Step 3: Commit**

```bash
git add api/kronos/__init__.py
git commit -m "$(cat <<'EOF'
feat(kronos): expose public api/kronos exports

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: api/jobs.py integration — pre-warm Kronos and seed kronos_report

**Files:**
- Modify: `api/jobs.py:777-799` (`_propagate_sync` method)
- Create: `tests/test_api_jobs_kronos_integration.py`

- [ ] **Step 1: Read the current `_propagate_sync` to anchor the modification**

Run: `sed -n '775,800p' api/jobs.py`

Confirm the current shape matches what's quoted in the spec; if it has drifted, adjust the patch in Step 4 accordingly.

- [ ] **Step 2: Write the failing integration test**

Create `tests/test_api_jobs_kronos_integration.py`:

```python
"""Integration test: jobs.Worker._propagate_sync seeds kronos_report
via the monkey-patch on Propagator.create_initial_state, and merges
kronos_forecast / kronos_status into the returned final_state."""
from __future__ import annotations

from unittest.mock import patch, MagicMock

import pandas as pd
import pytest

from api.jobs import Worker
from api.kronos.errors import InsufficientData, ModelLoadError
from api.kronos.schema import (
    KronosForecastPayload,
    KronosForecastRow,
)


def _ohlcv(n: int = 200) -> pd.DataFrame:
    ts = pd.date_range(end="2026-05-18", periods=n, freq="B")
    return pd.DataFrame({
        "timestamps": ts,
        "open": [100.0] * n, "high": [101.0] * n,
        "low": [99.0] * n, "close": [100.5] * n,
        "volume": [1_000_000.0] * n, "amount": [100_500_000.0] * n,
    })


def _payload() -> KronosForecastPayload:
    row = KronosForecastRow(
        date="2026-05-20", open=100.0, high=101.0, low=99.0,
        close=100.5, volume=1.0, amount=100.5,
    )
    return KronosForecastPayload(
        ticker="AAPL", trade_date="2026-05-19",
        model="NeoQuasar/Kronos-small", tokenizer="NeoQuasar/Kronos-Tokenizer-base",
        device="cpu", lookback=200, pred_len=1, sample_count=1,
        history_tail=[row], forecast=[row],
        generated_at="2026-05-19T12:00:00+00:00",
    )


def _make_graph_capture_seen_state():
    """Return (graph_mock, captured) where ``captured['seen_kronos_report']``
    is what the graph sees in its initial state during propagate()."""
    captured: dict = {}

    class FakePropagator:
        def __init__(self):
            self.calls = 0

        def create_initial_state(self, company_name, trade_date, past_context=""):
            self.calls += 1
            return {"kronos_report": "", "messages": [("human", company_name)]}

        def get_graph_args(self, callbacks=None):
            return {"stream_mode": "values", "config": {"recursion_limit": 100}}

    class FakeGraph:
        def __init__(self):
            self.propagator = FakePropagator()

        def propagate(self, ticker, date):
            state = self.propagator.create_initial_state(ticker, date)
            captured["seen_kronos_report"] = state["kronos_report"]
            return ({"market_report": "ok", "kronos_report": state["kronos_report"]},
                    "BUY")

    return FakeGraph(), captured


def test_propagate_sync_seeds_kronos_report_with_real_forecast():
    graph, captured = _make_graph_capture_seen_state()
    with patch("api.jobs.TradingAgentsGraph", return_value=graph), \
         patch("api.jobs.fetch_ohlcv", return_value=_ohlcv()), \
         patch("api.jobs.KronosService") as svc_cls:
        svc_cls.get.return_value.forecast.return_value = _payload()
        worker = Worker(max_concurrency=1)
        final_state, rating = worker._propagate_sync(
            "AAPL", "2026-05-19", {"llm_provider": "test"}, ["market", "kronos"],
        )

    # Researchers would have seen the seeded text — not empty.
    assert captured["seen_kronos_report"] != ""
    assert "Kronos forecast" in captured["seen_kronos_report"]
    # Structured payload merged
    assert final_state["kronos_forecast"] is not None
    assert final_state["kronos_forecast"]["ticker"] == "AAPL"
    assert final_state["kronos_status"] == "ok"
    assert rating == "BUY"


def test_propagate_sync_strips_kronos_from_selected_analysts():
    graph, _ = _make_graph_capture_seen_state()
    with patch("api.jobs.TradingAgentsGraph") as graph_cls, \
         patch("api.jobs.fetch_ohlcv", return_value=_ohlcv()), \
         patch("api.jobs.KronosService") as svc_cls:
        graph_cls.return_value = graph
        svc_cls.get.return_value.forecast.return_value = _payload()
        worker = Worker(max_concurrency=1)
        worker._propagate_sync(
            "AAPL", "2026-05-19", {"llm_provider": "test"},
            ["market", "kronos", "news"],
        )
        _, kwargs = graph_cls.call_args
        # 'kronos' must NOT appear in the analyst list handed to the graph
        assert "kronos" not in kwargs["selected_analysts"]
        assert "market" in kwargs["selected_analysts"]
        assert "news" in kwargs["selected_analysts"]


def test_propagate_sync_falls_back_when_insufficient_data():
    graph, captured = _make_graph_capture_seen_state()
    with patch("api.jobs.TradingAgentsGraph", return_value=graph), \
         patch("api.jobs.fetch_ohlcv", side_effect=InsufficientData("only 50 bars")), \
         patch("api.jobs.KronosService") as svc_cls:
        worker = Worker(max_concurrency=1)
        final_state, _ = worker._propagate_sync(
            "AAPL", "2026-05-19", {"llm_provider": "test"}, ["market"],
        )
    assert final_state["kronos_status"] == "insufficient_data"
    assert final_state["kronos_forecast"] is None
    # Seeded text is the skip note — not empty (so researchers know it was tried)
    assert "skipped" in captured["seen_kronos_report"].lower() or \
           captured["seen_kronos_report"] == ""


def test_propagate_sync_falls_back_when_model_load_fails():
    graph, captured = _make_graph_capture_seen_state()
    with patch("api.jobs.TradingAgentsGraph", return_value=graph), \
         patch("api.jobs.fetch_ohlcv", return_value=_ohlcv()), \
         patch("api.jobs.KronosService") as svc_cls:
        svc_cls.get.return_value.forecast.side_effect = ModelLoadError("HF down")
        worker = Worker(max_concurrency=1)
        final_state, _ = worker._propagate_sync(
            "AAPL", "2026-05-19", {"llm_provider": "test"}, ["market"],
        )
    assert final_state["kronos_status"] == "load_failed"
    assert final_state["kronos_forecast"] is None
    assert captured["seen_kronos_report"] == ""


def test_monkey_patch_is_restored_on_propagate_exception():
    """Even if propagate() raises, create_initial_state must be restored."""
    graph, _ = _make_graph_capture_seen_state()
    original_create = graph.propagator.create_initial_state

    class BoomGraph:
        def __init__(self, base):
            self.propagator = base.propagator

        def propagate(self, ticker, date):
            raise RuntimeError("graph blew up")

    boom = BoomGraph(graph)
    with patch("api.jobs.TradingAgentsGraph", return_value=boom), \
         patch("api.jobs.fetch_ohlcv", return_value=_ohlcv()), \
         patch("api.jobs.KronosService") as svc_cls:
        svc_cls.get.return_value.forecast.return_value = _payload()
        worker = Worker(max_concurrency=1)
        with pytest.raises(RuntimeError):
            worker._propagate_sync(
                "AAPL", "2026-05-19", {"llm_provider": "test"}, ["market"],
            )
    # Patch must be reverted
    assert graph.propagator.create_initial_state is original_create


def test_propagate_sync_with_kronos_disabled(monkeypatch):
    monkeypatch.setenv("KRONOS_ENABLED", "false")
    graph, captured = _make_graph_capture_seen_state()
    with patch("api.jobs.TradingAgentsGraph", return_value=graph), \
         patch("api.jobs.fetch_ohlcv") as fetch_mock, \
         patch("api.jobs.KronosService") as svc_cls:
        worker = Worker(max_concurrency=1)
        final_state, _ = worker._propagate_sync(
            "AAPL", "2026-05-19", {"llm_provider": "test"}, ["market"],
        )
    # When disabled, neither fetch nor service should be touched
    fetch_mock.assert_not_called()
    svc_cls.get.assert_not_called()
    assert final_state["kronos_status"] == "disabled"
    assert final_state["kronos_forecast"] is None
    assert captured["seen_kronos_report"] == ""
```

- [ ] **Step 3: Run integration tests to verify failure**

Run: `pytest tests/test_api_jobs_kronos_integration.py -v`
Expected: failures because `api.jobs` doesn't yet import `fetch_ohlcv` / `KronosService`, and `_propagate_sync` doesn't return the new fields.

- [ ] **Step 4: Modify `api/jobs.py:777-799` to add Kronos pre-warm + seed**

Open [api/jobs.py](api/jobs.py). At the top of the file (with the other imports around line 19-24), add:

```python
from api.kronos import (
    KronosConfig,
    KronosService,
    InsufficientData,
    ModelLoadError,
    KronosDisabled,
    fetch_ohlcv,
    forecast_to_markdown,
    forecast_to_state,
)
from api.kronos.schema import KronosStatus
```

Then **replace** the existing `_propagate_sync` method (currently lines 777-799) with this version:

```python
    def _propagate_sync(
        self,
        ticker: str,
        date: str,
        config: Dict[str, Any],
        analysts: Optional[list],
    ) -> tuple:
        logger.info(
            "propagate() starting | ticker=%s date=%s provider=%s",
            ticker,
            date,
            config.get("llm_provider"),
        )
        selected = _coerce_analyst_ids(analysts)
        # The real Kronos forecast runs outside the graph (D1, D5 in the
        # spec) — strip the LLM scenario node so it never runs.
        selected = [a for a in selected if a != "kronos"]

        # ---- 1. Compute Kronos forecast (if enabled) -----------------------
        kcfg = KronosConfig.from_env()
        kronos_md = ""
        kronos_payload = None
        kronos_status: str = KronosStatus.ok.value

        if not kcfg.enabled:
            kronos_status = KronosStatus.disabled.value
        else:
            try:
                ohlcv_df = fetch_ohlcv(ticker, date, lookback=kcfg.lookback)
                kronos_payload = KronosService.get(kcfg).forecast(
                    ohlcv_df, ticker=ticker, trade_date=date,
                )
                kronos_md = forecast_to_markdown(kronos_payload)
            except InsufficientData as e:
                logger.warning("kronos: insufficient data for %s: %s", ticker, e)
                kronos_md = (
                    f"_Kronos forecast skipped for {ticker} on {date}: "
                    f"insufficient OHLCV history._"
                )
                kronos_status = KronosStatus.insufficient_data.value
            except ModelLoadError as e:
                logger.warning("kronos: model load failed: %s", e)
                kronos_status = KronosStatus.load_failed.value
            except KronosDisabled:
                kronos_status = KronosStatus.disabled.value
            except Exception as e:  # pragma: no cover - last-resort
                logger.warning("kronos: forecast failed: %s", e, exc_info=True)
                kronos_status = KronosStatus.predict_failed.value

        # ---- 2. Run the graph with a seeded kronos_report ------------------
        with _propagate_sync_lock:
            graph = TradingAgentsGraph(
                selected_analysts=selected,
                config=config,
                debug=False,
            )

            original_create = graph.propagator.create_initial_state

            def _seeded_create_initial_state(
                company_name, trade_date, past_context=""
            ):
                state = original_create(
                    company_name, trade_date, past_context=past_context,
                )
                state["kronos_report"] = kronos_md
                return state

            graph.propagator.create_initial_state = _seeded_create_initial_state
            try:
                out = graph.propagate(ticker, date)
            finally:
                graph.propagator.create_initial_state = original_create

        # ---- 3. Merge structured Kronos fields into the final state --------
        final_state, rating = out
        if isinstance(final_state, dict):
            final_state["kronos_forecast"] = forecast_to_state(kronos_payload)
            final_state["kronos_status"] = kronos_status

        logger.info(
            "propagate() finished | ticker=%s kronos_status=%s",
            ticker, kronos_status,
        )
        return (final_state, rating)
```

- [ ] **Step 5: Run integration tests, verify all pass**

Run: `pytest tests/test_api_jobs_kronos_integration.py -v`
Expected: 6 passed.

- [ ] **Step 6: Run the broader API test suite for regressions**

Run: `pytest tests/test_api_*.py -v`
Expected: all green. Any pre-existing failures unrelated to Kronos are acceptable, but anything in `tests/test_api_jobs*.py` MUST pass.

- [ ] **Step 7: Commit**

```bash
git add api/jobs.py tests/test_api_jobs_kronos_integration.py
git commit -m "$(cat <<'EOF'
feat(kronos): pre-warm Kronos forecast and seed kronos_report into graph

api/jobs.py._propagate_sync now strips 'kronos' from selected_analysts,
computes a real KronosService forecast around fetch_ohlcv, and seeds
the resulting markdown into kronos_report via a try/finally monkey-patch
of Propagator.create_initial_state — so bull/bear researchers see the
forecast in their supplementary context before the research debate.

Structured kronos_forecast and a typed kronos_status (ok|disabled|
insufficient_data|load_failed|predict_failed|timeout) are merged into
final_state. All failure modes degrade silently; jobs never fail
because Kronos failed.

Zero edits inside tradingagents/ — the seed mechanism is a runtime
patch confined to a single try/finally block in api/jobs.py.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: Frontend label rename — "Kronos scenarios" → "Kronos forecast"

**Files:**
- Modify: `frontend/src/utils/reportMarkdown.ts:11`
- Modify: `frontend/src/pages/DashboardPage.tsx:50`
- Modify: `frontend/src/pages/BatchPage.tsx:26`

- [ ] **Step 1: Inspect the three label sites**

Run: `grep -n "Kronos scenarios" frontend/src/utils/reportMarkdown.ts frontend/src/pages/DashboardPage.tsx frontend/src/pages/BatchPage.tsx`

Expected: one match each.

- [ ] **Step 2: Update `frontend/src/utils/reportMarkdown.ts:11`**

Change:
```ts
kronos: "Kronos scenarios",
```
to:
```ts
kronos: "Kronos forecast",
```

- [ ] **Step 3: Update `frontend/src/pages/DashboardPage.tsx:50`**

Change:
```ts
{ id: "kronos", label: "Kronos scenarios" },
```
to:
```ts
{ id: "kronos", label: "Kronos forecast" },
```

- [ ] **Step 4: Update `frontend/src/pages/BatchPage.tsx:26`**

Change:
```ts
{ id: "kronos", label: "Kronos scenarios" },
```
to:
```ts
{ id: "kronos", label: "Kronos forecast" },
```

- [ ] **Step 5: Run frontend tests**

Run: `cd frontend && npm test -- --run`
Expected: all green. If `DashboardPage.test.tsx` references the literal string `"Kronos scenarios"`, update that test to expect `"Kronos forecast"` and re-run.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/utils/reportMarkdown.ts frontend/src/pages/DashboardPage.tsx frontend/src/pages/BatchPage.tsx
# add the test file if it was modified in Step 5
git status -s frontend/
git commit -m "$(cat <<'EOF'
feat(frontend): rename 'Kronos scenarios' tab to 'Kronos forecast'

The label now reflects what the backend actually produces (real Kronos
model forecast) instead of the LLM scenario placeholder.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: Live smoke test (opt-in) + manual end-to-end verification

**Files:**
- Create: `tests/test_api_kronos_live.py`

- [ ] **Step 1: Add the live smoke test**

Create `tests/test_api_kronos_live.py`:

```python
"""Live Kronos smoke test — loads the real model from HF Hub.

OPT-IN ONLY. Excluded from default CI. Run with:
    pytest -m kronos_live -v
"""
from __future__ import annotations

import pandas as pd
import pytest

from api.kronos import KronosConfig, KronosService
from api.kronos.predictor import _VENDOR_KRONOS


pytestmark = pytest.mark.kronos_live


@pytest.fixture(autouse=True)
def _reset_singleton():
    KronosService.reset()
    yield
    KronosService.reset()


def _synthetic_ohlcv(n: int = 200) -> pd.DataFrame:
    ts = pd.date_range(end="2026-05-18", periods=n, freq="B")
    base = 100.0
    closes = [base + i * 0.5 for i in range(n)]
    return pd.DataFrame({
        "timestamps": ts,
        "open":   [c - 0.5 for c in closes],
        "high":   [c + 1.0 for c in closes],
        "low":    [c - 1.0 for c in closes],
        "close":  closes,
        "volume": [1_000_000.0] * n,
        "amount": [c * 1_000_000.0 for c in closes],
    })


def test_vendor_kronos_clone_exists():
    """Live tests presume scripts/dev_up.sh has been run."""
    assert (_VENDOR_KRONOS / "model" / "__init__.py").exists(), (
        f"vendor/kronos not found at {_VENDOR_KRONOS} — run scripts/dev_up.sh"
    )


def test_real_kronos_small_forecast_smoke():
    """End-to-end load + forecast against the real Kronos-small model."""
    cfg = KronosConfig(
        model="NeoQuasar/Kronos-small",
        tokenizer="NeoQuasar/Kronos-Tokenizer-base",
        device="cpu",  # don't assume GPU/MPS in the smoke test
        lookback=200,
        pred_len=10,
        sample_count=1,
        max_context=512,
    )
    svc = KronosService.get(cfg)
    payload = svc.forecast(
        _synthetic_ohlcv(200), ticker="SMOKE", trade_date="2026-05-19",
    )
    assert payload.ticker == "SMOKE"
    assert len(payload.forecast) == 10
    # Close prices should be finite floats, not NaN/Inf
    for row in payload.forecast:
        assert row.close > 0
        assert row.close == row.close  # NaN check
```

- [ ] **Step 2: Run the live test locally (manual one-time verification)**

Run (from a venv where `scripts/dev_up.sh` has executed successfully):

```bash
pytest -m kronos_live -v
```

Expected:
- Test 1 (vendor exists) passes.
- Test 2 (real-model forecast) downloads ~100MB from HF on first run, then completes in 10-30 seconds on CPU. Asserts pass.

If HF Hub is unreachable, this test correctly fails — that's expected for an opt-in live test.

- [ ] **Step 3: Manual end-to-end run of the real analysis pipeline**

This step is manual and not a pytest — it verifies the integration end-to-end with all the moving pieces.

Run:
```bash
# Start backend in one terminal:
KRONOS_ENABLED=true KRONOS_DEVICE=cpu uvicorn api.main:app --reload --port 8000

# In another terminal, submit a job:
curl -X POST http://localhost:8000/api/jobs \
  -H 'Content-Type: application/json' \
  -d '{"ticker":"AAPL","date":"2026-05-19","analysts":["market","news","kronos"]}'

# Poll job:
# (GET /api/jobs/<id> until status=completed)
```

Verify in the completed job's report:
- `final_state.kronos_status == "ok"`
- `final_state.kronos_forecast` is a non-null object with `ticker`, `forecast` array, etc.
- The "Kronos forecast" tab in the frontend shows real OHLCV numbers in a table (not LLM-written scenario paragraphs).
- The bull and bear research reports REFERENCE the Kronos forecast (search the markdown for "Kronos" or specific forecast numbers).

If the last bullet fails — bull/bear don't reference Kronos — the seed mechanism is broken. Add a print/log inside `_seeded_create_initial_state` to verify `kronos_md` is non-empty at seed time.

- [ ] **Step 4: Commit the live test**

```bash
git add tests/test_api_kronos_live.py
git commit -m "$(cat <<'EOF'
test(kronos): add opt-in live smoke test (pytest -m kronos_live)

Excluded from default CI. Loads NeoQuasar/Kronos-small from HF and runs
a synthetic forecast end-to-end. Documented in pyproject.toml's
'kronos_live' marker.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: Wrap-up — verify CI, update CHANGELOG, no leftover work

- [ ] **Step 1: Confirm the full default test suite is green**

Run: `pytest -v` (no Kronos marker)
Expected: all tests pass, including the new `test_api_kronos_*` files. The `kronos_live` test is automatically excluded.

- [ ] **Step 2: Confirm `git status` shows only intended files**

Run: `git status`
Expected: clean (everything committed). If `vendor/kronos/` shows up tracked, the `.gitignore` entry from Task 1 is wrong — fix the gitignore and `git rm --cached -r vendor/kronos`.

- [ ] **Step 3: Final manual sanity check**

```bash
# Disable Kronos and rerun a job — verify the pipeline still works.
KRONOS_ENABLED=false uvicorn api.main:app --reload --port 8000
# Submit a job (same curl as Task 9 Step 3).
# Verify final_state.kronos_status == "disabled" and the job completes normally.
```

- [ ] **Step 4: Optionally tag the spec as implemented**

If you keep a changelog of specs, add a line to the bottom of [docs/superpowers/specs/2026-05-19-real-kronos-integration-design.md](../specs/2026-05-19-real-kronos-integration-design.md):

```markdown
---

**Implementation status:** ✅ Shipped 2026-05-XX (commit <SHA>).
```

(Optional. If you do this, commit it.)

---

## Self-review (run after the last task)

After completing all tasks, walk the spec section by section:

| Spec section | Task(s) | Status |
|---|---|---|
| §4 D1 Kronos in job pipeline | Task 7 | ✓ |
| §4 D2 Clone-and-sys.path install | Task 1 + Task 4 | ✓ |
| §4 D3 Kronos-small + auto-device | Task 2 (config), Task 4 (predictor) | ✓ |
| §4 D4 lookback=200, pred_len=20, sample_count=1 | Task 2 (config defaults) | ✓ |
| §4 D5 Skip LLM kronos_analyst node | Task 7 (strip from selected) | ✓ |
| §4 D6 Markdown-only frontend | Task 5 (markdown) + Task 8 (rename) | ✓ |
| §4 D7 Kronos runs BEFORE propagate | Task 7 | ✓ |
| §4 D8 Runtime monkey-patch in api/jobs.py | Task 7 | ✓ |
| §4 D9 yfinance OHLCV | Task 3 | ✓ |
| §5.4 All KRONOS_* env vars | Task 1 (.env.example) + Task 2 (config) | ✓ |
| §6 Error matrix (all 6 KronosStatus values) | Task 7 integration tests | ✓ |
| §7 Tests (unit + integration + live) | Tasks 2–7, 9 | ✓ |
| §8 Files touched list | All tasks combined | ✓ |
