"""Multi-symbol portfolio backtest with equal capital slices and per-symbol Kelly."""

from __future__ import annotations

from typing import Any

import pandas as pd

from algo_trade.backtest.engine import run_long_only_next_open
from algo_trade.backtest.metrics import compute_metrics
from algo_trade.data import fetch_daily_ohlcv
from algo_trade.risk.kelly import kelly_fraction_from_trade_returns, load_kelly_config
from algo_trade.strategy.mean_reversion import (
    add_mean_reversion_signals,
    should_enter_row,
    should_exit_row,
)


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


def simulate_dynamic_slots(
    signals: dict[str, pd.DataFrame],
    *,
    total_capital: float,
    max_slots: int,
    commission_pct: float,
    slippage_pct: float,
    rsi_entry: float = 35.0,
    take_profit_pct: float = 6.0,
    stop_loss_pct: float = 5.0,
    max_hold_days: int = 15,
) -> dict[str, Any]:
    """
    Mirror `algo_trade.live.angel_runner.run_dynamic_slot_cycle`: a fixed number of
    concurrent slots (Rs total_capital / max_slots each), whole-share sizing, and
    Kelly fraction estimated from the POOLED closed-trade history across every
    symbol/slot (not each symbol's own thin history) — the same fix now used live.

    `signals` must already carry indicator columns from `add_mean_reversion_signals`
    (bb_lower, bb_mid, rsi, sma_trend, close, open) for each symbol, pre-fetched so a
    parameter sweep can reuse one set of downloads instead of re-fetching per run.
    """
    if max_slots <= 0:
        raise ValueError("max_slots must be > 0")
    slice_capital = total_capital / max_slots
    kelly_cfg = load_kelly_config()

    all_dates = sorted(set().union(*(set(df.index) for df in signals.values())))

    slot_symbol: list[str | None] = [None] * max_slots
    slot_cash = [slice_capital] * max_slots
    slot_shares = [0.0] * max_slots
    slot_entry_price = [0.0] * max_slots
    slot_entry_close = [0.0] * max_slots
    slot_bars_held = [0] * max_slots
    held_by_symbol: dict[str, int] = {}

    pooled_returns: list[float] = []
    trades: list[dict[str, Any]] = []
    equity_hist: list[tuple[pd.Timestamp, float]] = []

    for i in range(len(all_dates) - 1):
        date = all_dates[i]
        next_date = all_dates[i + 1]

        for slot_i in range(max_slots):
            sym = slot_symbol[slot_i]
            if sym is None:
                continue
            df = signals[sym]
            if date not in df.index:
                continue
            row = df.loc[date]
            if pd.isna(row.get("bb_lower")):
                continue
            slot_bars_held[slot_i] += 1
            exit_now = should_exit_row(
                row,
                entry_close=slot_entry_close[slot_i],
                bars_held=slot_bars_held[slot_i],
                take_profit_pct=take_profit_pct,
                stop_loss_pct=stop_loss_pct,
                max_hold_days=max_hold_days,
            )
            if exit_now and next_date in df.index:
                next_open = float(df.loc[next_date, "open"])
                px = next_open * (1 - slippage_pct / 100) * (1 - commission_pct / 100)
                proceeds = slot_shares[slot_i] * px
                cost_basis = slot_shares[slot_i] * slot_entry_price[slot_i]
                slot_cash[slot_i] += proceeds
                ret_pct = (px / slot_entry_price[slot_i] - 1.0) * 100.0
                pooled_returns.append(ret_pct)
                trades.append(
                    {
                        "symbol": sym,
                        "entry_price": slot_entry_price[slot_i],
                        "exit_price": px,
                        "exit_date": next_date,
                        "return_pct": ret_pct,
                        "pnl": proceeds - cost_basis,
                    }
                )
                slot_symbol[slot_i] = None
                slot_shares[slot_i] = 0.0
                slot_entry_price[slot_i] = 0.0
                slot_entry_close[slot_i] = 0.0
                slot_bars_held[slot_i] = 0
                del held_by_symbol[sym]

        empty_slots = [i for i in range(max_slots) if slot_symbol[i] is None]
        if empty_slots:
            candidates: list[tuple[float, str, pd.Series]] = []
            for sym, df in signals.items():
                if sym in held_by_symbol or date not in df.index or next_date not in df.index:
                    continue
                row = df.loc[date]
                if pd.isna(row.get("bb_lower")) or pd.isna(row.get("sma_trend")):
                    continue
                if should_enter_row(row, rsi_entry=rsi_entry):
                    candidates.append((float(row["rsi"]), sym, row))
            candidates.sort(key=lambda c: c[0])  # most oversold first when slots are scarce

            for _, sym, row in candidates:
                if not empty_slots:
                    break
                slot_i = empty_slots.pop(0)
                next_open = float(signals[sym].loc[next_date, "open"])
                frac = kelly_fraction_from_trade_returns(pooled_returns, config=kelly_cfg)
                spendable = slot_cash[slot_i] * frac
                px = next_open * (1 + slippage_pct / 100) * (1 + commission_pct / 100)
                qty = int(spendable // px) if px > 0 else 0
                if qty <= 0 and px > 0 and slot_cash[slot_i] >= px:
                    qty = 1  # matches live's "buy at least one share" fallback
                if qty <= 0:
                    empty_slots.insert(0, slot_i)
                    continue
                cost = qty * px
                slot_cash[slot_i] -= cost
                slot_shares[slot_i] = qty
                slot_entry_price[slot_i] = px
                slot_entry_close[slot_i] = float(row["close"])
                slot_bars_held[slot_i] = 0
                slot_symbol[slot_i] = sym
                held_by_symbol[sym] = slot_i

        total_eq = 0.0
        for slot_i in range(max_slots):
            total_eq += slot_cash[slot_i]
            sym = slot_symbol[slot_i]
            if sym is not None and date in signals[sym].index:
                total_eq += slot_shares[slot_i] * float(signals[sym].loc[date, "close"])
        equity_hist.append((date, total_eq))

    equity = pd.Series(
        [e for _, e in equity_hist],
        index=pd.DatetimeIndex([d for d, _ in equity_hist]),
        name="equity",
    )
    metrics = compute_metrics(equity, trades, initial_capital=total_capital)
    final_kelly = kelly_fraction_from_trade_returns(pooled_returns, config=kelly_cfg)

    return {
        "max_slots": max_slots,
        "slice_capital": slice_capital,
        "total_capital": total_capital,
        "metrics": metrics,
        "trades": trades,
        "equity_curve": equity,
        "pooled_kelly_final": final_kelly,
        "pooled_trades_count": len(pooled_returns),
    }


def run_dynamic_slot_backtest(
    symbols: list[str],
    *,
    total_capital: float,
    max_slots: int,
    start: str,
    end: str | None = None,
    commission_pct: float,
    slippage_pct: float,
    bb_period: int = 20,
    bb_std: float = 2.0,
    rsi_entry: float = 35.0,
    trend_sma: int = 200,
    take_profit_pct: float = 6.0,
    stop_loss_pct: float = 5.0,
    max_hold_days: int = 15,
) -> dict[str, Any]:
    """Fetch + build signals, then run `simulate_dynamic_slots`. See that function for semantics."""
    signals = {
        sym: add_mean_reversion_signals(
            fetch_daily_ohlcv(sym, start=start, end=end),
            bb_period=bb_period,
            bb_std=bb_std,
            rsi_entry=rsi_entry,
            trend_sma=trend_sma,
            take_profit_pct=take_profit_pct,
            stop_loss_pct=stop_loss_pct,
            max_hold_days=max_hold_days,
        )
        for sym in symbols
    }
    return simulate_dynamic_slots(
        signals,
        total_capital=total_capital,
        max_slots=max_slots,
        commission_pct=commission_pct,
        slippage_pct=slippage_pct,
        rsi_entry=rsi_entry,
        take_profit_pct=take_profit_pct,
        stop_loss_pct=stop_loss_pct,
        max_hold_days=max_hold_days,
    )
