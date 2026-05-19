"""Domain exceptions for the Kronos integration."""


class KronosError(Exception):
    """Base class for Kronos-integration domain errors."""


class KronosDisabled(KronosError):
    """KRONOS_ENABLED is false — caller should skip the forecast entirely."""


class InsufficientData(KronosError):
    """Fewer OHLCV bars available than the configured lookback."""


class ModelLoadError(KronosError):
    """Loading the upstream Kronos model/tokenizer failed."""
