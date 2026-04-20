"""Simple dual moving-average crossover on close (educational / low complexity)."""

from __future__ import annotations

import pandas as pd


def add_signals(df: pd.DataFrame, fast: int, slow: int, price_col: str = "close") -> pd.DataFrame:
    if fast >= slow:
        raise ValueError("fast period must be < slow period")
    out = df.copy()
    out["sma_fast"] = out[price_col].rolling(fast, min_periods=fast).mean()
    out["sma_slow"] = out[price_col].rolling(slow, min_periods=slow).mean()
    # Signal at bar close: 1 = long bias, 0 = flat/cash
    out["signal"] = (out["sma_fast"] > out["sma_slow"]).astype(int)
    out["position_target"] = out["signal"]
    return out
