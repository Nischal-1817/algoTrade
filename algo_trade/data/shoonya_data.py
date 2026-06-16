"""Daily OHLCV from Shoonya get_daily_price_series."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import pandas as pd

from algo_trade.broker.shoonya_client import get_authenticated_api, resolve_trading_symbol

logger = logging.getLogger("algo_trade.data.shoonya")


def _parse_daily_rows(raw: Any) -> pd.DataFrame:
    rows = []
    if raw is None:
        return pd.DataFrame()
    if isinstance(raw, str):
        raw = [raw]
    for item in raw:
        if isinstance(item, str):
            item = json.loads(item)
        if not isinstance(item, dict):
            continue
        ts = int(float(item.get("ssboe", 0)))
        if ts <= 0:
            continue
        dt = datetime.fromtimestamp(ts, tz=timezone.utc).replace(tzinfo=None)
        rows.append(
            {
                "date": dt,
                "open": float(item.get("into", 0)),
                "high": float(item.get("inth", 0)),
                "low": float(item.get("intl", 0)),
                "close": float(item.get("intc", 0)),
                "volume": float(item.get("intv", 0)),
            }
        )
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows).set_index("date").sort_index()
    df.index = pd.to_datetime(df.index).tz_localize(None)
    return df


def fetch_daily_ohlcv_shoonya(
    symbol: str,
    *,
    lookback_days: int = 400,
    api: Any | None = None,
) -> pd.DataFrame:
    """
    Fetch NSE daily bars from Shoonya for mean-reversion signals.
    """
    api = api or get_authenticated_api()
    tsym = resolve_trading_symbol(api, symbol)
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=lookback_days)
    ret = api.get_daily_price_series(
        exchange="NSE",
        tradingsymbol=tsym,
        startdate=str(int(start.timestamp())),
        enddate=str(int(end.timestamp())),
    )
    df = _parse_daily_rows(ret)
    if df.empty:
        raise ValueError(f"No Shoonya daily data for {tsym}")
    logger.info("Shoonya daily bars: %s rows for %s", len(df), tsym)
    return df
