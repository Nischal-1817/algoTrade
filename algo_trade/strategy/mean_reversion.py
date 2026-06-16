"""
Buy-low / sell-high (mean reversion) on daily bars.

Rules (defaults tuned for NSE large-caps; backtest before live use):

  ENTRY (go long at next session open):
    - Close is below the lower Bollinger band (period, std dev).
    - RSI is below rsi_entry (oversold).
    - Close is above the long trend SMA (only buy dips inside an uptrend).

  EXIT (flatten at next session open) — first condition that fires:
    - Take profit: close >= middle Bollinger band OR gain >= take_profit_pct.
    - Stop loss: close <= entry * (1 - stop_loss_pct/100).
    - Time stop: held >= max_hold_days sessions.
"""

from __future__ import annotations

import pandas as pd


def _rsi(close: pd.Series, period: int) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, pd.NA)
    return 100 - (100 / (1 + rs))


def add_mean_reversion_signals(
    df: pd.DataFrame,
    *,
    price_col: str = "close",
    bb_period: int = 20,
    bb_std: float = 2.0,
    rsi_period: int = 14,
    rsi_entry: float = 35.0,
    trend_sma: int = 200,
    take_profit_pct: float = 6.0,
    stop_loss_pct: float = 5.0,
    max_hold_days: int = 15,
) -> pd.DataFrame:
    if bb_period < 2 or rsi_period < 2 or trend_sma < 2:
        raise ValueError("periods must be >= 2")
    if bb_std <= 0 or stop_loss_pct <= 0 or take_profit_pct <= 0 or max_hold_days < 1:
        raise ValueError("invalid risk / band parameters")

    out = df.copy()
    close = out[price_col]
    mid = close.rolling(bb_period, min_periods=bb_period).mean()
    std = close.rolling(bb_period, min_periods=bb_period).std()
    out["bb_mid"] = mid
    out["bb_lower"] = mid - bb_std * std
    out["bb_upper"] = mid + bb_std * std
    out["rsi"] = _rsi(close, rsi_period)
    out["sma_trend"] = close.rolling(trend_sma, min_periods=trend_sma).mean()

    warmup = max(bb_period, rsi_period, trend_sma)
    position_target: list[int] = []
    in_pos = 0
    entry_close: float | None = None
    bars_held = 0

    for i in range(len(out)):
        if i < warmup:
            position_target.append(0)
            continue

        c = float(close.iloc[i])
        bb_l = float(out["bb_lower"].iloc[i])
        bb_m = float(out["bb_mid"].iloc[i])
        r = float(out["rsi"].iloc[i])
        trend = float(out["sma_trend"].iloc[i])

        if in_pos == 0:
            buy = c < bb_l and r < rsi_entry and c > trend
            if buy:
                in_pos = 1
                entry_close = c
                bars_held = 0
        else:
            bars_held += 1
            assert entry_close is not None
            gain_pct = (c / entry_close - 1.0) * 100.0
            take_profit = c >= bb_m or gain_pct >= take_profit_pct
            stop = gain_pct <= -stop_loss_pct
            time_stop = bars_held >= max_hold_days
            if take_profit or stop or time_stop:
                in_pos = 0
                entry_close = None
                bars_held = 0

        position_target.append(in_pos)

    out["position_target"] = position_target
    out["signal"] = out["position_target"]
    return out


def should_enter_row(
    row: pd.Series,
    *,
    rsi_entry: float = 35.0,
) -> bool:
    """Entry rules on one bar (columns from add_mean_reversion_signals)."""
    c = float(row["close"])
    return (
        c < float(row["bb_lower"])
        and float(row["rsi"]) < rsi_entry
        and c > float(row["sma_trend"])
    )


def should_exit_row(
    row: pd.Series,
    *,
    entry_close: float,
    bars_held: int,
    take_profit_pct: float = 6.0,
    stop_loss_pct: float = 5.0,
    max_hold_days: int = 15,
) -> bool:
    """Exit rules on one bar while in a position."""
    c = float(row["close"])
    gain_pct = (c / entry_close - 1.0) * 100.0
    return (
        c >= float(row["bb_mid"])
        or gain_pct >= take_profit_pct
        or gain_pct <= -stop_loss_pct
        or bars_held >= max_hold_days
    )


def live_action_from_history(
    ohlcv: pd.DataFrame,
    *,
    in_position: bool,
    entry_close: float | None,
    bars_held: int,
    bb_period: int = 20,
    bb_std: float = 2.0,
    rsi_period: int = 14,
    rsi_entry: float = 35.0,
    trend_sma: int = 200,
    take_profit_pct: float = 6.0,
    stop_loss_pct: float = 5.0,
    max_hold_days: int = 15,
) -> str:
    """
    Return 'buy', 'sell', or 'hold' using the latest completed daily bar.
    """
    sig = add_mean_reversion_signals(
        ohlcv,
        bb_period=bb_period,
        bb_std=bb_std,
        rsi_period=rsi_period,
        rsi_entry=rsi_entry,
        trend_sma=trend_sma,
        take_profit_pct=take_profit_pct,
        stop_loss_pct=stop_loss_pct,
        max_hold_days=max_hold_days,
    )
    row = sig.iloc[-1]
    if pd.isna(row.get("bb_lower")) or pd.isna(row.get("sma_trend")):
        return "hold"
    if in_position:
        if entry_close is None:
            return "hold"
        if should_exit_row(
            row,
            entry_close=entry_close,
            bars_held=bars_held,
            take_profit_pct=take_profit_pct,
            stop_loss_pct=stop_loss_pct,
            max_hold_days=max_hold_days,
        ):
            return "sell"
        return "hold"
    if should_enter_row(row, rsi_entry=rsi_entry):
        return "buy"
    return "hold"
