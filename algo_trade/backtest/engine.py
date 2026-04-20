"""Long-only daily backtest: signal on close, trade next open."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import pandas as pd

logger = logging.getLogger("algo_trade.backtest")


@dataclass
class Trade:
    entry_time: pd.Timestamp
    exit_time: Optional[pd.Timestamp]
    entry_price: float
    exit_price: Optional[float]
    qty: float
    side: str


def _apply_costs(price: float, side: str, commission_pct: float, slippage_pct: float) -> float:
    slip = slippage_pct / 100.0
    comm = commission_pct / 100.0
    if side == "buy":
        return price * (1 + slip) * (1 + comm)
    return price * (1 - slip) * (1 - comm)


def run_long_only_next_open(
    ohlcv: pd.DataFrame,
    *,
    initial_capital: float,
    commission_pct: float,
    slippage_pct: float,
    price_col: str = "close",
) -> Dict[str, Any]:
    """
    `ohlcv` must include columns: open, position_target (0/1).
    Signal is read from the close of day i; orders fill at the open of day i+1.
    Equity is marked to market on each close using `price_col`.
    """
    df = ohlcv.copy()
    if "open" not in df.columns or "position_target" not in df.columns:
        raise ValueError("ohlcv needs 'open' and 'position_target'")
    df["position_target"] = df["position_target"].fillna(0).astype(int)

    cash = float(initial_capital)
    shares = 0.0
    equity_curve: List[float] = []
    trades: List[Trade] = []
    current: Optional[Trade] = None
    prev_target = 0

    for i in range(len(df)):
        mark = float(df[price_col].iloc[i])
        equity_curve.append(cash + shares * mark)

        if i >= len(df) - 1:
            break

        target = int(df["position_target"].iloc[i])
        next_open = float(df["open"].iloc[i + 1])
        next_ts = df.index[i + 1]

        if prev_target == 0 and target == 1 and shares == 0:
            spendable = cash
            if spendable > 0:
                px = _apply_costs(next_open, "buy", commission_pct, slippage_pct)
                qty = spendable / px
                cash -= qty * px
                shares = qty
                current = Trade(
                    entry_time=next_ts,
                    exit_time=None,
                    entry_price=px,
                    exit_price=None,
                    qty=qty,
                    side="long",
                )
                trades.append(current)
                logger.debug("BUY %s qty=%.4f @ %.4f", next_ts, qty, px)
        elif prev_target == 1 and target == 0 and shares > 0 and current is not None:
            px = _apply_costs(next_open, "sell", commission_pct, slippage_pct)
            cash += shares * px
            current.exit_time = next_ts
            current.exit_price = px
            logger.debug("SELL %s qty=%.4f @ %.4f", next_ts, shares, px)
            shares = 0.0
            current = None

        prev_target = target

    equity_s = pd.Series(equity_curve, index=df.index, name="equity")

    closed_trades: List[Dict[str, Any]] = []
    for t in trades:
        if t.exit_time is None or t.exit_price is None:
            continue
        pnl = (t.exit_price - t.entry_price) * t.qty
        closed_trades.append(
            {
                "entry_time": t.entry_time,
                "exit_time": t.exit_time,
                "entry_price": t.entry_price,
                "exit_price": t.exit_price,
                "qty": t.qty,
                "pnl": pnl,
                "return_pct": (t.exit_price / t.entry_price - 1.0) * 100.0,
            }
        )

    return {
        "equity_curve": equity_s,
        "trades": closed_trades,
        "final_cash": cash,
        "final_shares": shares,
        "final_equity": float(equity_s.iloc[-1]),
    }
