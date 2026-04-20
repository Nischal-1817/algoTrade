"""Download NSE equity daily bars via Yahoo Finance (.NS suffix)."""

from __future__ import annotations

import logging
from typing import Optional

import pandas as pd
import yfinance as yf

logger = logging.getLogger("algo_trade.data")


def normalize_nse_symbol(symbol: str) -> str:
    """Ensure Yahoo-style NSE ticker (e.g. RELIANCE -> RELIANCE.NS)."""
    s = symbol.strip().upper()
    if s.endswith(".NS"):
        return s
    if s.endswith(".NSE"):
        return s.replace(".NSE", ".NS")
    return f"{s}.NS"


def fetch_daily_ohlcv(
    symbol: str,
    start: Optional[str] = None,
    end: Optional[str] = None,
    auto_adjust: bool = True,
) -> pd.DataFrame:
    """
    Fetch daily OHLCV. `auto_adjust=True` uses split/dividend-adjusted prices
    for backtests (common convention for equity trend strategies).
    """
    ysym = normalize_nse_symbol(symbol)
    logger.info("Fetching %s (interval=1d)", ysym)
    t = yf.Ticker(ysym)
    df = t.history(start=start, end=end, interval="1d", auto_adjust=auto_adjust)
    if df.empty:
        raise ValueError(f"No data returned for {ysym}. Check symbol and date range.")
    df = df.rename(
        columns={
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Volume": "volume",
        }
    )
    out = df[["open", "high", "low", "close", "volume"]].copy()
    out.index = pd.to_datetime(out.index).tz_localize(None)
    out = out.sort_index()
    return out
