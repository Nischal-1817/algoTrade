"""Build and load backtest-ranked watchlists for dynamic slot filling."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Sequence

from algo_trade.backtest.engine import run_long_only_next_open
from algo_trade.backtest.metrics import compute_metrics
from algo_trade.config import DATA_DIR
from algo_trade.data import fetch_daily_ohlcv
from algo_trade.strategy.mean_reversion import add_mean_reversion_signals

logger = logging.getLogger("algo_trade.universe.watchlist")

WATCHLIST_PATH = DATA_DIR / "watchlist.json"


def rank_symbols_for_mean_reversion(
    symbols: Sequence[str],
    *,
    start: str = "2018-01-01",
    end: str | None = None,
    slice_capital: float = 5_000.0,
    commission_pct: float = 0.03,
    slippage_pct: float = 0.05,
    min_trades: int = 2,
    use_kelly: bool = True,
) -> list[dict[str, Any]]:
    """Backtest each symbol; return rows sorted by total_return_pct descending."""
    rows: list[dict[str, Any]] = []
    for sym in symbols:
        sym = sym.strip().upper().replace(".NS", "")
        if not sym:
            continue
        try:
            ohlcv = fetch_daily_ohlcv(sym, start=start, end=end)
            sig = add_mean_reversion_signals(ohlcv)
            result = run_long_only_next_open(
                sig,
                initial_capital=slice_capital,
                commission_pct=commission_pct,
                slippage_pct=slippage_pct,
                use_kelly_sizing=use_kelly,
            )
            eq = result["equity_curve"].ffill()
            metrics = compute_metrics(eq, result["trades"], initial_capital=slice_capital)
            if metrics["n_trades"] < min_trades:
                continue
            rows.append(
                {
                    "symbol": sym,
                    "total_return_pct": metrics["total_return_pct"],
                    "max_drawdown_pct": metrics["max_drawdown_pct"],
                    "n_trades": metrics["n_trades"],
                    "win_rate_pct": metrics["win_rate_pct"],
                    "final_equity": metrics["final_equity"],
                }
            )
            logger.info(
                "Rank %s: return=%.2f%% trades=%d",
                sym,
                metrics["total_return_pct"],
                metrics["n_trades"],
            )
        except Exception as exc:
            logger.warning("Skip %s: %s", sym, exc)

    rows.sort(
        key=lambda r: (r["total_return_pct"], r["win_rate_pct"], -r["max_drawdown_pct"]),
        reverse=True,
    )
    for i, row in enumerate(rows, start=1):
        row["rank"] = i
    return rows


def build_watchlist(
    symbols: Sequence[str],
    *,
    top_n: int = 50,
    start: str = "2018-01-01",
    slice_capital: float = 5_000.0,
    min_trades: int = 2,
) -> dict[str, Any]:
    ranked = rank_symbols_for_mean_reversion(
        symbols,
        start=start,
        slice_capital=slice_capital,
        min_trades=min_trades,
    )
    top = ranked[:top_n]
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "start": start,
        "top_n": top_n,
        "universe_size": len(list(symbols)),
        "ranked_count": len(ranked),
        "symbols": [r["symbol"] for r in top],
        "rankings": top,
    }
    save_watchlist(payload)
    return payload


def save_watchlist(payload: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    WATCHLIST_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    logger.info("Wrote watchlist %s (%d symbols)", WATCHLIST_PATH, len(payload.get("symbols", [])))


def load_watchlist(*, fallback: Sequence[str] | None = None) -> dict[str, Any]:
    if WATCHLIST_PATH.exists():
        try:
            return json.loads(WATCHLIST_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Could not read watchlist: %s", exc)
    fb = list(fallback or ("ICICIBANK", "ITC", "RELIANCE", "TCS"))
    return {
        "generated_at": None,
        "symbols": fb,
        "rankings": [],
        "fallback": True,
    }


def watchlist_symbols(*, fallback: Sequence[str] | None = None) -> list[str]:
    data = load_watchlist(fallback=fallback)
    return [s.upper() for s in data.get("symbols", [])]
