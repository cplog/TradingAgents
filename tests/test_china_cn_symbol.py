"""Unit tests for mainland A-share symbol normalization."""

import pytest

from tradingagents.dataflows.china_cn_symbol import (
    akshare_symbol,
    baostock_code,
    is_cn_a_share_symbol,
)


@pytest.mark.unit
def test_is_cn_a_share_recognized():
    assert is_cn_a_share_symbol("600000.SH")
    assert is_cn_a_share_symbol("000001.SZ")
    assert is_cn_a_share_symbol("430047.BJ")
    assert is_cn_a_share_symbol("600000")
    assert not is_cn_a_share_symbol("AAPL")
    assert not is_cn_a_share_symbol("6060.HK")


@pytest.mark.unit
def test_akshare_symbol():
    assert akshare_symbol("600000.SH") == "600000"
    assert akshare_symbol("600000") == "600000"


@pytest.mark.unit
def test_baostock_code():
    assert baostock_code("600000.SH") == "sh.600000"
    assert baostock_code("000001.SZ") == "sz.000001"
    assert baostock_code("430047.BJ") == "bj.430047"
    assert baostock_code("600000") == "sh.600000"
    assert baostock_code("000001") == "sz.000001"


@pytest.mark.unit
def test_akshare_hk_listing_code():
    from tradingagents.dataflows.china_cn_symbol import akshare_hk_listing_code

    assert akshare_hk_listing_code("6060.HK") == "06060"
    assert akshare_hk_listing_code("1211.HK") == "01211"
    assert akshare_hk_listing_code("AAPL") is None


@pytest.mark.unit
def test_akshare_us_ticker():
    from tradingagents.dataflows.china_cn_symbol import akshare_us_ticker

    assert akshare_us_ticker("AAPL") == "AAPL"
    assert akshare_us_ticker("brk.b") == "BRK.B"
    assert akshare_us_ticker("6060.HK") is None
    assert akshare_us_ticker("600000.SH") is None
    assert akshare_us_ticker("NVDA.TO") is None
    assert akshare_us_ticker("^GSPC") is None
