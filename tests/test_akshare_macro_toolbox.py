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
    assert 'category="interest_rate"' in out


@pytest.mark.unit
def test_list_akshare_endpoints_interest_rate_category(monkeypatch):
    fake_ak = SimpleNamespace(
        macro_bank_usa_interest_rate=lambda: pd.DataFrame({"x": [1]}),
        macro_uk_bank_rate=lambda: pd.DataFrame({"x": [1]}),
        macro_china_lpr=lambda: pd.DataFrame({"x": [1]}),
        macro_usa_cpi_yoy=lambda: pd.DataFrame({"x": [1]}),
        macro_usa_eia_crude_rate=lambda: pd.DataFrame({"x": [1]}),
    )
    monkeypatch.setattr(akshare_macro, "_import_akshare", lambda: fake_ak)

    out = akshare_macro.list_akshare_endpoints(category="interest_rate", limit=20)
    assert "macro_bank_usa_interest_rate" in out
    assert "macro_uk_bank_rate" in out
    assert "macro_china_lpr" in out
    assert "macro_usa_cpi_yoy" not in out
    assert "macro_usa_eia_crude_rate" not in out
    assert "not `macro_usa_*`" in out


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
def test_get_macro_akshare_usa_bank_rate_alias(monkeypatch):
    """LLMs often guess macro_usa_bank_interest_rate; AKShare uses macro_bank_usa_interest_rate."""

    def macro_bank_usa_interest_rate():
        return pd.DataFrame({"日期": ["2024-01-01"], "今值": [5.25]})

    fake_ak = SimpleNamespace(macro_bank_usa_interest_rate=macro_bank_usa_interest_rate)
    monkeypatch.setattr(akshare_macro, "_import_akshare", lambda: fake_ak)

    out = akshare_macro.get_macro_akshare(
        function_name="macro_usa_bank_interest_rate",
        params_json="{}",
        tail_rows=5,
    )
    assert "macro_bank_usa_interest_rate" in out
    assert "resolved_from_alias" in out
    assert "5.25" in out


@pytest.mark.unit
def test_get_macro_akshare_usa_irate_alias(monkeypatch):
    """LLMs often abbreviate US interest rate as macro_usa_irate."""

    def macro_bank_usa_interest_rate():
        return pd.DataFrame({"日期": ["2024-01-01"], "今值": [5.25]})

    fake_ak = SimpleNamespace(macro_bank_usa_interest_rate=macro_bank_usa_interest_rate)
    monkeypatch.setattr(akshare_macro, "_import_akshare", lambda: fake_ak)

    out = akshare_macro.get_macro_akshare(
        function_name="macro_usa_irate",
        params_json="{}",
        tail_rows=5,
    )
    assert "macro_bank_usa_interest_rate" in out
    assert "resolved_from_alias" in out
    assert "5.25" in out


@pytest.mark.unit
def test_get_macro_akshare_unknown_fn_returns_hint(monkeypatch):
    fake_ak = SimpleNamespace(
        macro_bank_usa_interest_rate=lambda: pd.DataFrame({"x": [1]}),
        macro_usa_ppi=lambda: pd.DataFrame({"x": [1]}),
    )
    monkeypatch.setattr(akshare_macro, "_import_akshare", lambda: fake_ak)

    out = akshare_macro.get_macro_akshare(function_name="macro_typo_xyz")
    assert "not found" in out
    assert "macro_typo_xyz" in out
    assert "list_akshare_endpoints" in out


@pytest.mark.unit
def test_get_macro_akshare_rejects_non_allowed_prefix(monkeypatch):
    fake_ak = SimpleNamespace(foo=lambda: pd.DataFrame({"x": [1]}))
    monkeypatch.setattr(akshare_macro, "_import_akshare", lambda: fake_ak)

    with pytest.raises(DataVendorUnavailable, match="must start with 'macro_' or 'stock_'"):
        akshare_macro.get_macro_akshare(function_name="foo")
