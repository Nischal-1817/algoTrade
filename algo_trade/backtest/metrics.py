"""Performance metrics from an equity curve (daily frequency assumed)."""

from __future__ import annotations

from typing import Any, Dict, List

import numpy as np
import pandas as pd


def compute_metrics(
    equity: pd.Series,
    trades: List[Dict[str, Any]],
    *,
    initial_capital: float,
    risk_free_rate: float = 0.06,
) -> Dict[str, Any]:
    equity = equity.astype(float)
    ret = equity.pct_change(fill_method=None).dropna()
    total_return_pct = (equity.iloc[-1] / initial_capital - 1.0) * 100.0

    years = (equity.index[-1] - equity.index[0]).days / 365.25
    if years > 0 and equity.iloc[0] > 0:
        cagr_pct = ((equity.iloc[-1] / equity.iloc[0]) ** (1 / years) - 1.0) * 100.0
    else:
        cagr_pct = float("nan")

    roll_max = equity.cummax()
    dd = (equity / roll_max - 1.0) * 100.0
    max_dd_pct = float(dd.min()) if len(dd) else float("nan")

    if len(ret) > 1 and ret.std() > 0:
        # Daily Sharpe ~ sqrt(252) annualization
        excess = ret.mean() * 252 - risk_free_rate
        sharpe = excess / (ret.std() * np.sqrt(252))
    else:
        sharpe = float("nan")

    wins = [t for t in trades if t.get("pnl", 0) > 0]
    losses = [t for t in trades if t.get("pnl", 0) < 0]
    win_rate = (len(wins) / len(trades) * 100.0) if trades else float("nan")

    return {
        "initial_capital": initial_capital,
        "final_equity": float(equity.iloc[-1]),
        "total_return_pct": float(total_return_pct),
        "cagr_pct": float(cagr_pct),
        "max_drawdown_pct": float(max_dd_pct),
        "sharpe_approx": float(sharpe),
        "n_trades": len(trades),
        "n_wins": len(wins),
        "n_losses": len(losses),
        "win_rate_pct": float(win_rate),
        "avg_trade_pnl": float(np.mean([t["pnl"] for t in trades])) if trades else float("nan"),
    }
