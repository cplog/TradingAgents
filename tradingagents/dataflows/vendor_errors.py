"""Exceptions that tell ``route_to_vendor`` to try the next data vendor."""


class DataVendorUnavailable(Exception):
    """Raised when the current vendor cannot serve the request (no key, wrong market, empty series)."""

    pass
