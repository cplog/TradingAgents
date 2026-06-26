"""Exchange-style symbol hints for AKShare routing."""


import re


def is_cn_a_share_symbol(symbol: str) -> bool:
    if not symbol or not isinstance(symbol, str):
        return False
    s = symbol.strip().upper()
    if s.endswith((".SH", ".SZ", ".BJ")):
        return True
    if len(s) == 6 and s.isdigit():
        return True
    return False


def akshare_symbol(symbol: str) -> str | None:
    """Six-digit code for ``ak.stock_zh_a_hist``."""
    if not is_cn_a_share_symbol(symbol):
        return None
    s = symbol.strip().upper()
    if s.endswith((".SH", ".SZ", ".BJ")):
        return s[:-3]
    if len(s) == 6 and s.isdigit():
        return s
    return None


def akshare_hk_listing_code(symbol: str) -> str | None:
    """5-digit Eastmoney HK code for ``ak.stock_hk_hist`` (e.g. ``6060.HK`` → ``06060``)."""
    if not symbol or not isinstance(symbol, str):
        return None
    s = symbol.strip().upper()
    if not s.endswith(".HK"):
        return None
    num = s[:-3]
    if not num.isdigit():
        return None
    return num.zfill(5)


_US_CLASS_B = re.compile(r"^[A-Z]{1,4}\.[A-Z]$")


def akshare_us_ticker(symbol: str) -> str | None:
    """Ticker for ``ak.stock_us_daily`` — US listco style only (e.g. ``AAPL``, ``BRK.B``)."""
    if not symbol or not isinstance(symbol, str):
        return None
    s = symbol.strip().upper()
    if is_cn_a_share_symbol(s) or s.endswith(".HK"):
        return None
    if any(c in s for c in "-^"):
        return None
    if "." in s:
        return s if _US_CLASS_B.fullmatch(s) else None
    if 1 <= len(s) <= 5 and s.isalpha():
        return s
    return None
