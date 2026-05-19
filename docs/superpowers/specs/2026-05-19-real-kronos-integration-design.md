# Real Kronos Integration — Design

**Date:** 2026-05-19
**Status:** Spec, awaiting implementation plan
**Owner:** cplog
**Spec author:** Claude (brainstorming session)

---

## 1. Context and problem statement

The current "Kronos" analyst at [tradingagents/agents/analysts/kronos_analyst.py](../../../tradingagents/agents/analysts/kronos_analyst.py) is a LangChain LLM node that asks a model to write 3–5 scenario paragraphs from OHLCV/indicator tool output. Its docstring discloses that it is *not* the external Kronos ML model, but every user-visible surface — the dashboard tab labelled "Kronos scenarios" ([DashboardPage.tsx:50](../../../frontend/src/pages/DashboardPage.tsx#L50), [BatchPage.tsx:26](../../../frontend/src/pages/BatchPage.tsx#L26)), the CLI label "Kronos Scenario Analyst" ([cli/main.py:58](../../../cli/main.py#L58)), the state key `kronos_report`, and [PRODUCT.md](../../../PRODUCT.md)'s "Kronos forecasting … news-aware adjustments … confidence bands" — leads users to believe they are getting output from the real Kronos foundation model ([shiyu-coder/Kronos](https://github.com/shiyu-coder/Kronos), AAAI 2026).

This spec replaces the placeholder with a genuine integration of the upstream Kronos K-line forecasting model, wired into the multi-analyst job pipeline so the forecast actually influences the investment decision rather than merely appearing in the final report bundle.

## 2. Goals

- A real `KronosPredictor`-backed forecast is produced for every analysis job (when enabled).
- The forecast reaches the bull/bear researchers via the existing `kronos_report` state field, so it flows through the research debate → trader → risk → PM chain and meaningfully shapes the investment decision.
- Zero edits inside `tradingagents/` (fork-sync rule).
- Structured forecast payload (`final_state["kronos_forecast"]`) is persisted in the job's report blob so a future PR can render a chart without backend changes.
- Failure of the Kronos predictor never blocks an analysis job; it degrades silently with a typed status field.

## 3. Non-goals

- Frontend forecast chart (Recharts) — deferred to a follow-up PR; backend will populate the structured payload regardless.
- Probabilistic forecast bands (p10/p50/p90 across sampled paths) — first PR ships a single-path forecast (`sample_count=1`); band work is a follow-up PR.
- News-adjusted forecast prompting (PRODUCT.md §3, "alphaear-predictor: Kronos with news-aware adjustments") — deferred.
- Standalone `POST /api/kronos/forecast` endpoint — deferred.
- Rewriting or deleting the existing LLM "kronos_analyst" node inside `tradingagents/` — we leave the file untouched and skip it at the orchestration layer.
- Upstreaming an `initial_state_overrides` kwarg to `TradingAgentsGraph.propagate()` — deferred.

## 4. Decisions (locked during brainstorming)

| # | Decision | Notes |
|---|---|---|
| D1 | Kronos runs **inside the job pipeline** (not as a standalone endpoint). | One-shot multi-analyst UX from PRODUCT.md. |
| D2 | Kronos source is **cloned into `vendor/kronos/`** (gitignored) by `scripts/dev_up.sh`, pinned to a specific upstream SHA, with `pip install -r vendor/kronos/requirements.txt`. `api/kronos/predictor.py` does `sys.path.insert(0, "vendor/kronos")` then imports normally. Matches the README's install flow. | Reversed 2026-05-19 from the earlier "vendor source files into the repo" decision — simpler, no maintained patches, closer to upstream's documented path. |
| D3 | Default model: **NeoQuasar/Kronos-small** (24.7M) + tokenizer **NeoQuasar/Kronos-Tokenizer-base**. | Auto-detect device: `mps → cuda → cpu`. All env-overridable. |
| D4 | Default horizon: **lookback=200 daily bars, pred_len=20, sample_count=1**. | Single-path forecast for the first PR. Probabilistic band (p10/p50/p90) deferred to a follow-up PR — see §3 non-goals. |
| D5 | The existing LLM `kronos_analyst` node is **skipped** by stripping `"kronos"` from `selected_analysts` in `api/jobs.py`. | File on disk is left untouched. |
| D6 | Frontend scope this PR: **markdown-only**. UI label changes from "Kronos scenarios" to "Kronos forecast". Structured `kronos_forecast` payload still produced for follow-up chart work. | |
| D7 | Sequencing: **Kronos runs BEFORE `graph.propagate()`** and the forecast markdown is seeded into `initial_state["kronos_report"]` so bull/bear researchers consume it. | Confirmed via [agent_utils.py:56-72](../../../tradingagents/agents/utils/agent_utils.py#L56-L72). |
| D8 | Seed mechanism: **runtime monkey-patch** of `ta_graph.propagator.create_initial_state` inside `api/jobs.py`, wrapped in `try/finally`. | Zero edits inside `tradingagents/`. |
| D9 | OHLCV source: **yfinance directly**. | Already a project dependency. Region-routing duplication avoided. |

## 5. Architecture

### 5.1 Data flow with decision propagation

```
api/jobs._run(ticker, trade_date, config, analysts):

  1. selected = [a for a in analysts if a != "kronos"]              # D5

  2. ohlcv_df = await asyncio.to_thread(fetch_ohlcv,                 # D9
                  ticker, trade_date, lookback=200+buffer)

  3. try:
        payload = await asyncio.wait_for(
            asyncio.to_thread(KronosService.get().forecast,          # D2,D3,D4
                              ohlcv_df, cfg),
            timeout=cfg.timeout_seconds)
        kronos_md = forecast_to_markdown(payload, ticker, trade_date)
        kronos_status = "ok"
     except KronosDisabled:    kronos_md, payload, kronos_status = "", None, "disabled"
     except InsufficientData:  kronos_md, payload, kronos_status = warn_md, None, "insufficient_data"
     except ModelLoadError:    kronos_md, payload, kronos_status = "", None, "load_failed"
     except asyncio.TimeoutError: kronos_md, payload, kronos_status = "", None, "timeout"
     except Exception:         kronos_md, payload, kronos_status = "", None, "predict_failed"

  4. # Seed kronos_report into the graph's initial state             # D7, D8
     orig_create = ta_graph.propagator.create_initial_state
     def _seeded(company, date, past_context=""):
         s = orig_create(company, date, past_context=past_context)
         s["kronos_report"] = kronos_md
         return s
     ta_graph.propagator.create_initial_state = _seeded
     try:
         final_state = await asyncio.to_thread(
             ta_graph.propagate, ticker, trade_date)
     finally:
         ta_graph.propagator.create_initial_state = orig_create

  5. final_state["kronos_forecast"] = forecast_to_state(payload) if payload else None
     final_state["kronos_status"] = kronos_status

  6. # existing report build + persistence unchanged
```

Where the forecast actually moves the decision:

```
analysts run                                  ← (no kronos analyst — D5)
   ↓
bull_researcher  reads kronos_report ✓       ← seeded via build_supplementary_analyst_context
bear_researcher  reads kronos_report ✓
   ↓
research_manager → investment_plan
   ↓
trader → trader_investment_plan
   ↓
risk_debate (aggressive/conservative/neutral)
   ↓
PM → final_trade_decision                     ← Kronos signal embedded in the debate that produced this
```

Also seen by `dimensions_snapshot.py:62`, so the Kronos signal flows into the dimensions scoring as well.

### 5.2 Module layout

```
api/kronos/
  __init__.py            # public exports: KronosService, KronosConfig, forecast_to_markdown,
                         #                 forecast_to_state, KronosStatus, KronosForecastPayload
  config.py              # env loader → KronosConfig dataclass (frozen)
  schema.py              # Pydantic: KronosForecastRow, KronosForecastPayload, KronosStatus enum
  predictor.py           # KronosService singleton (lazy load, device pick, .forecast())
  formatter.py           # forecast_to_markdown(payload, ticker, trade_date) -> str
                         # forecast_to_state(payload) -> dict
  ohlcv.py               # fetch_ohlcv(ticker, trade_date, lookback) -> pd.DataFrame (yfinance)
  errors.py              # KronosDisabled, InsufficientData, ModelLoadError

vendor/
  kronos/                # cloned at install time by scripts/dev_up.sh (gitignored)
                         # pinned to upstream SHA — see KRONOS_UPSTREAM_SHA in dev_up.sh
                         # contains model/{__init__.py, kronos.py, module.py} + upstream
                         # requirements.txt (installed alongside ours)

.gitignore               # add vendor/kronos/
```

`api/kronos/predictor.py` runs `sys.path.insert(0, str(REPO_ROOT / "vendor" / "kronos"))` before `from model import Kronos, KronosTokenizer, KronosPredictor`. Path insertion is idempotent and happens only on first lazy load.

### 5.3 Module responsibilities

- **`KronosService`** ([predictor.py]) — process-singleton via `KronosService.get()`. Lazy-loads model and tokenizer on first call. Owns: model, tokenizer, device, config. Public method: `forecast(ohlcv_df: pd.DataFrame, cfg: KronosConfig) -> KronosForecastPayload`. Raises `ModelLoadError`, `InsufficientData`. Thread-safe via a single `threading.Lock` around the lazy init.

- **Formatter** ([formatter.py]) — pure functions, no I/O. Easy to test against DataFrame fixtures.
  - `forecast_to_markdown(payload, ticker, trade_date) -> str` — short narrative + Markdown table of `date | p10_close | p50_close | p90_close | model | horizon` + one-line probabilistic-forecast disclaimer.
  - `forecast_to_state(payload) -> dict` — JSON-serialisable shape consumable by a future Recharts chart.

- **Config** ([config.py]) — `KronosConfig` frozen dataclass, instantiated from env once per process. Follows the existing pattern in [api/config.py](../../../api/config.py).

- **OHLCV** ([ohlcv.py]) — `fetch_ohlcv(ticker, trade_date, lookback) -> pd.DataFrame` using yfinance. Returns DataFrame with columns `['open','high','low','close','volume','amount']` and a `timestamps` Series indexed appropriately. `amount` is always synthesised as `close * volume` (yfinance doesn't expose turnover-in-currency). Upstream Kronos accepts this — the README documents `volume` and `amount` as optional, and using `close * volume` is the standard A-share/HK proxy.

- **Errors** ([errors.py]) — domain exceptions classified into `KronosStatus`.

- **`api/jobs.py`** — adds ~30-50 lines: `_run_kronos_forecast()` helper + the monkey-patch block in `_run()`. No other changes.

### 5.4 Configuration (env)

| Variable | Default | Notes |
|---|---|---|
| `KRONOS_ENABLED` | `true` | Master kill switch. `false` → `KronosDisabled`. |
| `KRONOS_MODEL` | `NeoQuasar/Kronos-small` | HF repo id. |
| `KRONOS_TOKENIZER` | `NeoQuasar/Kronos-Tokenizer-base` | HF repo id. |
| `KRONOS_DEVICE` | `auto` | `auto`\|`mps`\|`cuda`\|`cpu`. `auto` → `mps → cuda → cpu`. |
| `KRONOS_LOOKBACK` | `200` | Daily bars of history fed to the model. |
| `KRONOS_PRED_LEN` | `20` | Daily bars forecast forward. |
| `KRONOS_SAMPLE_COUNT` | `1` | Forecast paths to average internally. Single-path in this PR; reserved for the follow-up band PR. |
| `KRONOS_T` | `1.0` | Sampling temperature. |
| `KRONOS_TOP_P` | `0.9` | Nucleus sampling. |
| `KRONOS_TIMEOUT_SECONDS` | `90` | Hard ceiling on a single forecast call. |
| `KRONOS_MAX_CONTEXT` | `512` | Match Kronos-small's training context. |

All documented in `.env.example`.

### 5.5 Schema

```python
class KronosForecastRow(BaseModel):
    date: str                 # ISO date
    open: float
    high: float
    low: float
    close: float
    volume: float
    amount: float

class KronosForecastPayload(BaseModel):
    ticker: str
    trade_date: str           # ISO date — anchor for the forecast
    model: str                # e.g. "NeoQuasar/Kronos-small"
    tokenizer: str
    device: str               # actually-used device, after auto-detect
    lookback: int
    pred_len: int
    sample_count: int         # = 1 in this PR; reserved for future band work
    history_tail: list[KronosForecastRow]   # last 20 actual bars for chart context
    forecast: list[KronosForecastRow]       # pred_len-long forward forecast (single path)
    generated_at: str                       # ISO timestamp of forecast

class KronosStatus(str, Enum):
    ok = "ok"
    disabled = "disabled"
    insufficient_data = "insufficient_data"
    load_failed = "load_failed"
    predict_failed = "predict_failed"
    timeout = "timeout"
```

### 5.6 Markdown output shape

```markdown
## Kronos forecast — AAPL on 2026-05-19

**Model:** NeoQuasar/Kronos-small · **Device:** mps · **History:** 200d · **Horizon:** 20d

Kronos forecasts the close drifting from $X (last actual) to $Y (day 20), a roughly
Z% move. The intraday range over the forecast horizon spans $A–$B. Forecasted total
volume over the horizon is W shares.

| Day | Date       |    open |    high |     low |   close |   volume |
|----:|------------|--------:|--------:|--------:|--------:|---------:|
|   1 | 2026-05-20 |    …    |    …    |    …    |    …    |    …     |
|   … | …          |    …    |    …    |    …    |    …    |    …     |
|  20 | 2026-06-16 |    …    |    …    |    …    |    …    |    …     |

*Single-path forecast from the Kronos foundation model (sample_count=1). Probabilistic bands across multiple sampled paths are coming in a follow-up PR. Not investment advice.*
```

The narrative paragraph is generated deterministically from the payload (no LLM call) so it's reproducible and cheap.

## 6. Error handling

| Condition | Behavior | `kronos_report` | `kronos_status` |
|---|---|---|---|
| `KRONOS_ENABLED=false` | Skip step 3 entirely. | `""` | `"disabled"` |
| Model load fails (network, HF down, OOM at load) | Log warning with stack. | `""` | `"load_failed"` |
| OHLCV fetch returns < `lookback` bars | Log warning. Set markdown to a 1-line note. | `"_Kronos forecast skipped: only N daily bars available, need ≥200._"` | `"insufficient_data"` |
| Inference raises | Log warning with stack. | `""` | `"predict_failed"` |
| Inference exceeds `KRONOS_TIMEOUT_SECONDS` | `asyncio.wait_for` cancels. | `""` | `"timeout"` |

**No silent failures.** Every skip path sets `kronos_status`. Jobs never fail because Kronos failed.

The monkey-patch's `try/finally` ensures `create_initial_state` is restored even if `propagate` raises — preserves graph instance integrity across jobs (the JobStore reuses a single `TradingAgentsGraph`).

## 7. Testing

| File | Type | What it covers |
|---|---|---|
| `tests/test_api_kronos_config.py` | unit | Env → `KronosConfig` parsing; auto-device resolution; bad values. |
| `tests/test_api_kronos_ohlcv.py` | unit | `fetch_ohlcv` happy path (mock yfinance), insufficient data, ticker variants (US/HK/A-share via .HK/.SS suffix). |
| `tests/test_api_kronos_predictor.py` | unit | `KronosService.forecast()` with `KronosPredictor` stubbed to return a deterministic DataFrame. Asserts payload shape, device fallback, lazy init thread safety. |
| `tests/test_api_kronos_formatter.py` | unit | `forecast_to_markdown` golden tests on fixture payloads; `forecast_to_state` JSON-serialisability; edge cases (NaN, single sample, very small price). |
| `tests/test_api_jobs_kronos_integration.py` | integration | `jobs._run()` with `KronosService` patched: verifies `kronos_report` is seeded into initial_state before propagate, `kronos_forecast` lands in final_state, `kronos_status` is set correctly across all failure modes, monkey-patch is restored on success and on failure. |
| `tests/test_api_kronos_live.py` | live, opt-in | Real model load + 1 forecast on synthetic OHLCV. Marked `@pytest.mark.kronos_live`, excluded from default CI. |

No live model tests in default CI (slow + needs HF network). Add `kronos_live` marker to `[tool.pytest.ini_options].markers` in `pyproject.toml`.

## 8. Files touched (final list)

**New files:**
- `api/kronos/__init__.py`
- `api/kronos/config.py`
- `api/kronos/schema.py`
- `api/kronos/predictor.py`
- `api/kronos/formatter.py`
- `api/kronos/ohlcv.py`
- `api/kronos/errors.py`
- `tests/test_api_kronos_config.py`
- `tests/test_api_kronos_ohlcv.py`
- `tests/test_api_kronos_predictor.py`
- `tests/test_api_kronos_formatter.py`
- `tests/test_api_jobs_kronos_integration.py`
- `tests/test_api_kronos_live.py`
- `docs/superpowers/specs/2026-05-19-real-kronos-integration-design.md` (this file)

**Modified files:**
- `api/jobs.py` — `_propagate_sync()` strips `"kronos"` from analysts, computes Kronos forecast, applies a `try/finally` monkey-patch on `graph.propagator.create_initial_state` to seed `kronos_report` before calling `graph.propagate()`, and merges `kronos_forecast` / `kronos_status` into the returned final_state.
- `pyproject.toml` — add `kronos_live` to pytest markers. (Kronos's own dependencies — torch, einops, huggingface_hub, safetensors — are pulled in via `pip install -r vendor/kronos/requirements.txt` at setup time, not added to our pyproject.)
- `.env.example` — add all `KRONOS_*` env vars.
- `scripts/dev_up.sh` — clone `shiyu-coder/Kronos` to `vendor/kronos/` pinned at `KRONOS_UPSTREAM_SHA`, then `pip install -r vendor/kronos/requirements.txt`.
- `.gitignore` — add `vendor/kronos/`.
- `frontend/src/utils/reportMarkdown.ts` — `"kronos": "Kronos scenarios"` → `"kronos": "Kronos forecast"`.
- `frontend/src/pages/DashboardPage.tsx` — same label change.
- `frontend/src/pages/BatchPage.tsx` — same label change.

**Files explicitly NOT touched:**
- Anything under `tradingagents/` — fork-sync rule.
- `tradingagents/agents/analysts/kronos_analyst.py` stays on disk but is never invoked.

## 9. Migration / rollout

- This is purely additive at the data-flow level: when `KRONOS_ENABLED=false` (or any failure mode), `kronos_report` remains empty exactly as before. Bull/bear researchers already handle empty supplementary reports gracefully ([agent_utils.py:69-71](../../../tradingagents/agents/utils/agent_utils.py#L69-L71): "(no supplementary analyst reports for this run)").
- Default-on: ship with `KRONOS_ENABLED=true`. Operators who don't want the model dependency can set `false` in their `.env`.
- First job after deployment incurs the model-load latency once; subsequent jobs reuse the warm `KronosService`.

## 10. Risks and mitigations

| Risk | Mitigation |
|---|---|
| HF Hub blocked or down on first job | `ModelLoadError` → `kronos_status="load_failed"` → empty `kronos_report` → job completes normally. |
| `torch` install too heavy for some users | Install is opt-in: a developer who doesn't run `scripts/dev_up.sh` doesn't get Kronos. Setting `KRONOS_ENABLED=false` is the runtime opt-out. |
| Apple Silicon MPS torch bug crashes inference | Auto-fallback to CPU is *not* automatic — user must set `KRONOS_DEVICE=cpu`. Document in `.env.example`. |
| Monkey-patch leaks across jobs if `try/finally` is bypassed | The `try/finally` is unconditional inside `_propagate_sync`. Integration test simulates a `propagate()` exception and asserts `propagator.create_initial_state` is restored. |
| Cloned `vendor/kronos/` drifts from a known-good SHA | `scripts/dev_up.sh` pins `KRONOS_UPSTREAM_SHA` and runs `git -C vendor/kronos checkout $KRONOS_UPSTREAM_SHA`. Updating Kronos = bump SHA in the script. |
| `vendor/kronos/` missing at runtime (developer skipped `dev_up.sh`) | `KronosService._ensure_loaded` raises `ModelLoadError("vendor/kronos not found — run scripts/dev_up.sh")`. Caught at the job runner → `kronos_status="load_failed"`. |
| `yfinance` rate limits or returns bad data for HK/A-share tickers | `InsufficientData` path covers it. `kronos_status="insufficient_data"`. Future work could fall back to akshare. |

## 11. Open questions for plan-writing phase

None — all material decisions are locked above. The implementation plan (writing-plans skill) should structure work into:

1. Install wiring — `scripts/dev_up.sh` clone-and-pip-install of upstream Kronos; `.gitignore`; `.env.example`; pytest marker.
2. `api/kronos/` skeleton (errors, schema, config) with tests.
3. `api/kronos/ohlcv.py` + tests.
4. `api/kronos/predictor.py` + tests (with stubbed `KronosPredictor`).
5. `api/kronos/formatter.py` + tests.
6. `api/kronos/__init__.py` public exports.
7. `api/jobs.py` integration + integration tests.
8. Frontend label rename.
9. Live smoke test (opt-in marker) + manual end-to-end run.

---

**Implementation status:** Shipped 2026-05-19 (commit `c6a20a9`, range `0aec6cb..c6a20a9`).
