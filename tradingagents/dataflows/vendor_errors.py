"""Backward-compat re-exports from the vendor-error taxonomy.

Previous code imported ``DataVendorUnavailable`` from this module.
It is now ``VendorRateLimitError`` in ``errors.py``.
"""

from .errors import (
    NoMarketDataError,
    VendorError,
    VendorNotConfiguredError,
    VendorRateLimitError,
)

DataVendorUnavailable = VendorRateLimitError
