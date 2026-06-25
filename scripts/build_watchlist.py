"""Rank NSE universe by mean-reversion backtest; write data/watchlist.json."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from algo_trade.config import ensure_dirs
from algo_trade.logging_config import setup_logging
from algo_trade.universe import NIFTY50, build_watchlist, nifty100


def main() -> None:
    p = argparse.ArgumentParser(description="Build backtest-ranked watchlist")
    p.add_argument("--universe", choices=("nifty50", "nifty100"), default="nifty100")
    p.add_argument("--top", type=int, default=50, help="Keep top N by backtest return")
    p.add_argument("--start", default="2018-01-01")
    p.add_argument("--min-trades", type=int, default=2)
    p.add_argument("--slice", type=float, default=5000.0, help="Capital per symbol in ranking backtest")
    args = p.parse_args()

    log = setup_logging()
    ensure_dirs()

    if args.universe == "nifty50":
        symbols = list(NIFTY50)
    else:
        symbols = list(nifty100())

    log.info("Ranking %d symbols (%s) -> top %d", len(symbols), args.universe, args.top)
    payload = build_watchlist(
        symbols,
        top_n=args.top,
        start=args.start,
        slice_capital=args.slice,
        min_trades=args.min_trades,
    )

    print()
    print(f"Watchlist: top {len(payload['symbols'])} of {payload['ranked_count']} ranked "
          f"(universe {payload['universe_size']})")
    print(f"{'Rank':<5} {'Symbol':<12} {'Return%':>9} {'Trades':>7} {'Win%':>7}")
    print("-" * 44)
    for row in payload["rankings"][:20]:
        print(
            f"{row['rank']:<5} {row['symbol']:<12} {row['total_return_pct']:>9.2f} "
            f"{row['n_trades']:>7} {row['win_rate_pct']:>7.1f}"
        )
    if len(payload["rankings"]) > 20:
        print(f"... and {len(payload['rankings']) - 20} more")
    print()
    print("Top 10:", ", ".join(payload["symbols"][:10]))


if __name__ == "__main__":
    main()
