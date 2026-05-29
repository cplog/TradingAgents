"""Tests for AKShare monitor helpers."""

import pytest

from tradingagents.dataflows.akshare_monitor import normalize_akshare_us_code


@pytest.mark.unit
def test_normalize_akshare_us_code():
    assert normalize_akshare_us_code("105.AAPL") == "AAPL"
    assert normalize_akshare_us_code("AAPL") == "AAPL"
