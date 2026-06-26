"""Daily Barbell Trend Cloud (BTC) signal engine for overnight dip hunting."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from typing import Any

import pandas as pd
import yfinance as yf

from .akshare_monitor import get_spot_for_ticker
from .config import get_config
from .stockstats_utils import load_ohlcv, yf_retry
from .vendor_errors import DataVendorUnavailable

CLOUD_LAYERS = (
    ("short", 5, 10),
    ("mid", 10, 21),
    ("struct", 21, 55),
)
ATR_PERIOD = 14
AMPLITUDE_MAX_PCT = 8.0


@dataclass
class OvernightSignal:
    ticker: str
    score: int
    threshold: int
    triggered: bool
    change_pct: float | None
    amplitude_pct: float | None
    bias_6: float | None
    bias_3: float | None
    structural_support_touch: bool
    wide_range: bool
    volume_spike: bool
    flags: dict[str, bool] = field(default_factory=dict)
    cloud: dict[str, Any] = field(default_factory=dict)
    as_of: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    def to_markdown(self) -> str:
        lines = [
            f"## Overnight Signal — {self.ticker}",
            "",
            f"- **Score:** {self.score} / 100 (threshold {self.threshold})",
            f"- **Triggered:** {'yes' if self.triggered else 'no'}",
            f"- **Change today:** {self._fmt(self.change_pct, '%')}",
            f"- **Amplitude:** {self._fmt(self.amplitude_pct, '%')}",
            f"- **BIAS(6):** {self._fmt(self.bias_6, '%')}",
            f"- **BIAS(3):** {self._fmt(self.bias_3, '%')}",
            f"- **Structural cloud support:** {'yes' if self.structural_support_touch else 'no'}",
            f"- **Wide range (> {AMPLITUDE_MAX_PCT}%):** {'yes' if self.wide_range else 'no'}",
            f"- **Volume spike (>1.5× 20d avg):** {'yes' if self.volume_spike else 'no'}",
            "",
            "### Score breakdown",
        ]
        for k, v in self.flags.items():
            lines.append(f"- {k}: {'+points' if v else '—'}")
        return "\n".join(lines)

    @staticmethod
    def _fmt(val: float | None, suffix: str = "") -> str:
        if val is None:
            return "n/a"
        return f"{val:.2f}{suffix}"


def _ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def _atr(df: pd.DataFrame, period: int = ATR_PERIOD) -> pd.Series:
    high = df["High"]
    low = df["Low"]
    close = df["Close"]
    prev_close = close.shift(1)
    tr = pd.concat(
        [
            (high - low).abs(),
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.rolling(period, min_periods=1).mean()


def _bias(close: pd.Series, n: int) -> float | None:
    if len(close) < n:
        return None
    sma = close.rolling(n).mean().iloc[-1]
    if sma == 0 or pd.isna(sma):
        return None
    return float((close.iloc[-1] - sma) / sma * 100)


def _cloud_lower(df: pd.DataFrame, fast: int, slow: int) -> float | None:
    if len(df) < slow:
        return None
    close = df["Close"]
    fast_e = _ema(close, fast).iloc[-1]
    slow_e = _ema(close, slow).iloc[-1]
    atr = _atr(df).iloc[-1]
    if pd.isna(atr):
        return None
    return float(min(fast_e, slow_e) - 1.5 * atr)


def _daily_amplitude_pct(df: pd.DataFrame) -> float | None:
    if df.empty:
        return None
    row = df.iloc[-1]
    close = float(row["Close"])
    if close == 0:
        return None
    return float((float(row["High"]) - float(row["Low"])) / close * 100)


def scan_watchlist_panic_candidates(
    tickers: list[str],
    min_drop_pct: float = -10.0,
) -> list[dict[str, Any]]:
    """Watchlist-only panic scan via yfinance when AKShare full-market scan is unavailable."""
    out: list[dict[str, Any]] = []
    for raw in tickers:
        sym = str(raw).strip().upper()
        if not sym:
            continue
        change_pct, amplitude_pct = _fetch_change_pct_yfinance(sym)
        if change_pct is None or change_pct > min_drop_pct:
            continue
        out.append(
            {
                "ticker": sym,
                "akshare_code": None,
                "name": sym,
                "change_pct": change_pct,
                "amplitude_pct": amplitude_pct,
                "last_price": None,
                "source": "yfinance",
            }
        )
    out.sort(key=lambda row: row["change_pct"])
    return out


def _fetch_change_pct_yfinance(ticker: str) -> tuple[float | None, float | None]:
    """Return (change_pct, amplitude_proxy) from yfinance fast_info/info."""
    try:
        t = yf.Ticker(ticker.upper())
        info = yf_retry(lambda: getattr(t, "fast_info", None) or t.info)
        if not info:
            return None, None
        price = info.get("lastPrice") or info.get("regularMarketPrice")
        prev = info.get("previousClose") or info.get("regularMarketPreviousClose")
        if price is None or prev is None or prev == 0:
            return None, None
        change = float((float(price) - float(prev)) / float(prev) * 100)
        day_high = info.get("dayHigh") or info.get("regularMarketDayHigh")
        day_low = info.get("dayLow") or info.get("regularMarketDayLow")
        amp = None
        if day_high is not None and day_low is not None and price:
            amp = float((float(day_high) - float(day_low)) / float(price) * 100)
        return change, amp
    except Exception:
        return None, None


def compute_overnight_signal(
    ticker: str,
    trade_date: str | None = None,
    spot: dict[str, Any] | None = None,
) -> OvernightSignal:
    """Compute daily BTC score for one ticker."""
    cfg = get_config()
    threshold = int(cfg.get("monitor_signal_threshold", 75))
    sym = ticker.strip().upper()
    as_of = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    td = trade_date or date.today().isoformat()

    df = load_ohlcv(sym, td)
    if df is None or len(df) < 30:
        raise DataVendorUnavailable(f"daily_signals: insufficient OHLCV for {sym}")

    change_pct = None
    amplitude_pct = _daily_amplitude_pct(df)
    if spot:
        change_pct = spot.get("change_pct")
        if spot.get("amplitude_pct") is not None:
            amplitude_pct = spot.get("amplitude_pct")
    else:
        ak_spot = get_spot_for_ticker(sym)
        if ak_spot:
            change_pct = ak_spot.get("change_pct")
            if ak_spot.get("amplitude_pct") is not None:
                amplitude_pct = ak_spot.get("amplitude_pct")
    if change_pct is None:
        yf_change, yf_amp = _fetch_change_pct_yfinance(sym)
        change_pct = yf_change
        if amplitude_pct is None and yf_amp is not None:
            amplitude_pct = yf_amp

    close = df["Close"]
    bias_6 = _bias(close, 6)
    bias_3 = _bias(close, 3)

    cloud_info: dict[str, Any] = {}
    struct_lower = _cloud_lower(df, 21, 55)
    for name, fast, slow in CLOUD_LAYERS:
        cloud_info[name] = {"lower": _cloud_lower(df, fast, slow)}

    last_close = float(close.iloc[-1])
    structural_touch = (
        struct_lower is not None and last_close <= struct_lower * 1.002
    )

    vol = df["Volume"]
    vol_avg = float(vol.rolling(20).mean().iloc[-1]) if len(vol) >= 20 else None
    volume_spike = (
        vol_avg is not None
        and vol_avg > 0
        and float(vol.iloc[-1]) > vol_avg * 1.5
    )

    wide_range = amplitude_pct is not None and amplitude_pct > AMPLITUDE_MAX_PCT

    flags = {
        "drop_ge_10pct": change_pct is not None and change_pct <= -10.0,
        "structural_support": structural_touch,
        "bias_6_oversold": bias_6 is not None and bias_6 <= -6.0,
        "bias_3_oversold": bias_3 is not None and bias_3 <= -4.0,
        "amplitude_ok": amplitude_pct is not None and amplitude_pct <= AMPLITUDE_MAX_PCT,
        "volume_spike": volume_spike,
    }

    score = 0
    if flags["drop_ge_10pct"]:
        score += 25
    if flags["structural_support"]:
        score += 25
    if flags["bias_6_oversold"]:
        score += 20
    if flags["bias_3_oversold"]:
        score += 10
    if flags["amplitude_ok"]:
        score += 10
    elif wide_range:
        score = max(0, score - 5)
    if flags["volume_spike"]:
        score += 10

    return OvernightSignal(
        ticker=sym,
        score=score,
        threshold=threshold,
        triggered=score >= threshold,
        change_pct=change_pct,
        amplitude_pct=amplitude_pct,
        bias_6=bias_6,
        bias_3=bias_3,
        structural_support_touch=structural_touch,
        wide_range=wide_range,
        volume_spike=volume_spike,
        flags=flags,
        cloud=cloud_info,
        as_of=as_of,
    )
