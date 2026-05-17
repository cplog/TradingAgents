from types import SimpleNamespace

import pandas as pd
import pytest

from tradingagents.dataflows import akshare_macro
from tradingagents.dataflows.vendor_errors import DataVendorUnavailable


@pytest.mark.unit
def test_list_akshare_endpoints_filters_prefix(monkeypatch):
    fake_ak = SimpleNamespace(
        macro_cnbs=lambda: pd.DataFrame({"date": ["2024-01-01"], "v": [1.0]}),
        macro_global=lambda: pd.DataFrame({"date": ["2024-01-01"], "v": [2.0]}),
        stock_ebs_lg=lambda: pd.DataFrame({"日期": ["2024-01-01"], "股债利差": [0.05]}),
        hello=123,
    )
    monkeypatch.setattr(akshare_macro, "_import_akshare", lambda: fake_ak)

    out = akshare_macro.list_akshare_endpoints(prefix="macro_", include_stock=False, limit=20)
    assert "macro_cnbs" in out
    assert "macro_global" in out
    assert "stock_ebs_lg" not in out


@pytest.mark.unit
def test_get_macro_akshare_calls_dynamic_function(monkeypatch):
    fake_ak = SimpleNamespace(
        stock_a_gxl_lg=lambda symbol="上证A股": pd.DataFrame(
            {
                "日期": ["2024-01-01", "2024-01-02", "2024-01-03"],
                "股息率": [2.1, 2.2, 2.3],
                "symbol": [symbol, symbol, symbol],
            }
        )
    )
    monkeypatch.setattr(akshare_macro, "_import_akshare", lambda: fake_ak)

    out = akshare_macro.get_macro_akshare(
        function_name="stock_a_gxl_lg",
        params_json='{"symbol":"上证A股"}',
        tail_rows=2,
    )
    assert "AKShare `stock_a_gxl_lg`" in out
    assert "shown_rows: `2`" in out
    assert "上证A股" in out


@pytest.mark.unit
def test_get_macro_akshare_rejects_non_allowed_prefix(monkeypatch):
    fake_ak = SimpleNamespace(foo=lambda: pd.DataFrame({"x": [1]}))
    monkeypatch.setattr(akshare_macro, "_import_akshare", lambda: fake_ak)

    with pytest.raises(DataVendorUnavailable, match="must start with 'macro_' or 'stock_'"):
        akshare_macro.get_macro_akshare(function_name="foo")
