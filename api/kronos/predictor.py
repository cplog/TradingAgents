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

_REPO_ROOT = Path(__file__).resolve().parents[2]
_VENDOR_KRONOS = _REPO_ROOT / "vendor" / "kronos"

_HISTORY_TAIL_LEN = 20


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

        forecast_rows: List[KronosForecastRow] = []
        for ts, row in pred_df.iterrows():
            amount = float(row["amount"]) if "amount" in row else float(
                row["close"]
            ) * float(row["volume"])
            forecast_rows.append(_row_from(
                ts, row["open"], row["high"], row["low"],
                row["close"], row["volume"], amount,
            ))

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
