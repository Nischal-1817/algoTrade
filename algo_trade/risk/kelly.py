"""
Kelly-based position sizing (fraction of bankroll per trade).

Uses quarter-Kelly by default (safer than full Kelly). When history is thin,
falls back to a small default fraction so ₹10k can start conservatively and
scale as you add capital and accumulate trade stats.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, List, Sequence

import numpy as np


@dataclass
class KellyConfig:
    enabled: bool = True
    multiplier: float = 0.25  # quarter-Kelly
    max_fraction: float = 0.25  # never deploy more than 25% per trade
    min_fraction: float = 0.05  # 5% when edge unknown / few trades
    min_trades: int = 5  # need this many closed trades before trusting estimate


def load_kelly_config() -> KellyConfig:
    en = os.getenv("ALGO_USE_KELLY", "1").lower() in ("1", "true", "yes")
    return KellyConfig(
        enabled=en,
        multiplier=float(os.getenv("KELLY_MULTIPLIER", "0.25")),
        max_fraction=float(os.getenv("KELLY_MAX_FRACTION", "0.25")),
        min_fraction=float(os.getenv("KELLY_MIN_FRACTION", "0.05")),
        min_trades=int(os.getenv("KELLY_MIN_TRADES", "5")),
    )


def kelly_fraction_from_trade_returns(
    returns_pct: Sequence[float],
    *,
    config: KellyConfig | None = None,
) -> float:
    """
  returns_pct: per-trade return % (e.g. +3.2, -4.1).
  Returns fraction of bankroll to deploy (0..max_fraction).
  """
    cfg = config or load_kelly_config()
    if not cfg.enabled:
        return 1.0

    rets = [float(r) for r in returns_pct if r is not None and not np.isnan(r)]
    if len(rets) < cfg.min_trades:
        return cfg.min_fraction

    wins = [r for r in rets if r > 0]
    losses = [r for r in rets if r < 0]
    if not wins or not losses:
        return cfg.min_fraction

    p = len(wins) / len(rets)
    avg_win = float(np.mean(wins))
    avg_loss = abs(float(np.mean(losses)))
    if avg_loss <= 0:
        return cfg.min_fraction

    b = avg_win / avg_loss
    q = 1.0 - p
    f_star = (p * b - q) / b
    if f_star <= 0:
        return cfg.min_fraction

    f = f_star * cfg.multiplier
    return float(max(cfg.min_fraction, min(cfg.max_fraction, f)))


def kelly_fraction_from_trades(
    trades: Sequence[dict[str, Any]],
    *,
    config: KellyConfig | None = None,
) -> float:
    """Extract return_pct from backtest/live trade dicts."""
    returns = []
    for t in trades:
        if "return_pct" in t:
            returns.append(float(t["return_pct"]))
        elif t.get("entry_price") and t.get("exit_price"):
            ep, xp = float(t["entry_price"]), float(t["exit_price"])
            if ep > 0:
                returns.append((xp / ep - 1.0) * 100.0)
    return kelly_fraction_from_trade_returns(returns, config=config)


def position_size_inr(
    bankroll: float,
    price: float,
    kelly_fraction: float,
) -> tuple[int, float]:
    """Whole shares only. Returns (qty, spend_inr)."""
    if price <= 0 or bankroll <= 0 or kelly_fraction <= 0:
        return 0, 0.0
    spend = bankroll * kelly_fraction
    qty = int(spend // price)
    return qty, qty * price
