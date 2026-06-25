"""Multi-symbol portfolio backtest with equal capital slices and per-symbol Kelly."""

from __future__ import annotations

from typing import Any

import pandas as pd

from algo_trade.backtest.engine import run_long_only_next_open
from algo_trade.backtest.metrics import compute_metrics
from algo_trade.data import fetch_daily_ohlcv
from algo_trade.strategy.mean_reversion import add_mean_reversion_signals


def _align_equity_slices(
    equity_by_symbol: dict[str, pd.Series],
    *,
    slice_capital: float,
) -> pd.Series:
    """Sum per-symbol equity curves on a shared calendar (forward-fill gaps)."""
    if not equity_by_symbol:
        raise ValueError("equity_by_symbol is empty")
    union = sorted(set().union(*[set(s.index) for s in equity_by_symbol.values()]))
    idx = pd.DatetimeIndex(union)
    total = pd.Series(0.0, index=idx, name="portfolio_equity")
    for sym, eq in equity_by_symbol.items():
        aligned = eq.reindex(idx).ffill()
        aligned = aligned.fillna(slice_capital)
        total = total.add(aligned, fill_value=0.0)
    return total


def run_portfolio_mean_reversion(
    symbols: list[str],
    *,
    total_capital: float,
    start: str,
    end: str | None,
    commission_pct: float,
    slippage_pct: float,
    use_kelly: bool,
    bb_period: int = 20,
    bb_std: float = 2.0,
    rsi_entry: float = 35.0,
    take_profit_pct: float = 6.0,
    stop_loss_pct: float = 5.0,
    max_hold_days: int = 15,
) -> dict[str, Any]:
    if not symbols:
        raise ValueError("symbols must not be empty")
    n = len(symbols)
    slice_capital = total_capital / n

    per_symbol: dict[str, dict[str, Any]] = {}
    equity_by_symbol: dict[str, pd.Series] = {}
    all_trades: list[dict[str, Any]] = []

    for sym in symbols:
        ohlcv = fetch_daily_ohlcv(sym, start=start, end=end)
        sig = add_mean_reversion_signals(
            ohlcv,
            bb_period=bb_period,
            bb_std=bb_std,
            rsi_entry=rsi_entry,
            take_profit_pct=take_profit_pct,
            stop_loss_pct=stop_loss_pct,
            max_hold_days=max_hold_days,
        )
        result = run_long_only_next_open(
            sig,
            initial_capital=slice_capital,
            commission_pct=commission_pct,
            slippage_pct=slippage_pct,
            use_kelly_sizing=use_kelly,
        )
        eq = result["equity_curve"].ffill()
        final_equity = float(eq.iloc[-1]) if len(eq) else slice_capital
        trades = [{**t, "symbol": sym} for t in result["trades"]]
        all_trades.extend(trades)
        metrics = compute_metrics(
            eq,
            result["trades"],
            initial_capital=slice_capital,
        )
        per_symbol[sym] = {
            "metrics": metrics,
            "kelly_fraction": result.get("last_kelly_fraction"),
            "slice_capital": slice_capital,
            "final_equity": final_equity,
        }
        equity_by_symbol[sym] = eq

    portfolio_equity = _align_equity_slices(
        equity_by_symbol, slice_capital=slice_capital
    )
    portfolio_metrics = compute_metrics(
        portfolio_equity,
        all_trades,
        initial_capital=total_capital,
    )

    return {
        "symbols": symbols,
        "total_capital": total_capital,
        "slice_capital": slice_capital,
        "per_symbol": per_symbol,
        "portfolio_equity": portfolio_equity,
        "portfolio_metrics": portfolio_metrics,
        "trades": all_trades,
        "use_kelly": use_kelly,
    }
