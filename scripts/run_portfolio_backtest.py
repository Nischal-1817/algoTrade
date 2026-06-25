"""Backtest equal-weight multi-stock portfolio (mean reversion + Kelly per symbol)."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from algo_trade.backtest.portfolio import run_portfolio_mean_reversion
from algo_trade.config import REPORT_DIR, ensure_dirs, get_settings
from algo_trade.logging_config import setup_logging

DEFAULT_SYMBOLS = "ICICIBANK,ITC,RELIANCE,TCS"


def _print_table(result: dict) -> None:
    print()
    print(f"Portfolio: Rs {result['total_capital']:,.0f} across {len(result['symbols'])} stocks")
    print(f"Per-stock slice: Rs {result['slice_capital']:,.0f}  |  Kelly per symbol: {result['use_kelly']}")
    print()
    print(f"{'Symbol':<12} {'Return%':>9} {'MaxDD%':>9} {'Trades':>7} {'Win%':>7} {'Kelly':>7} {'Final Rs':>12}")
    print("-" * 72)
    for sym in result["symbols"]:
        m = result["per_symbol"][sym]["metrics"]
        k = result["per_symbol"][sym]["kelly_fraction"]
        kelly_s = f"{k:.2f}" if k is not None else "n/a"
        print(
            f"{sym:<12} {m['total_return_pct']:>9.2f} {m['max_drawdown_pct']:>9.2f} "
            f"{m['n_trades']:>7} {m['win_rate_pct']:>7.1f} {kelly_s:>7} "
            f"{result['per_symbol'][sym]['final_equity']:>12,.0f}"
        )
    pm = result["portfolio_metrics"]
    print("-" * 72)
    print(
        f"{'PORTFOLIO':<12} {pm['total_return_pct']:>9.2f} {pm['max_drawdown_pct']:>9.2f} "
        f"{pm['n_trades']:>7} {pm['win_rate_pct']:>7.1f} {'':>7} {pm['final_equity']:>12,.0f}"
    )
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Multi-symbol portfolio backtest")
    parser.add_argument("--symbols", default=DEFAULT_SYMBOLS, help="Comma-separated, e.g. ICICIBANK,ITC,RELIANCE,TCS")
    parser.add_argument("--capital", type=float, default=20_000.0, help="Total portfolio capital (INR)")
    parser.add_argument("--start", default="2018-01-01")
    parser.add_argument("--end", default=None)
    parser.add_argument("--no-kelly", action="store_true", help="Disable Kelly sizing (full slice per trade)")
    parser.add_argument("--bb-period", type=int, default=20)
    parser.add_argument("--bb-std", type=float, default=2.0)
    parser.add_argument("--rsi-entry", type=float, default=35.0)
    parser.add_argument("--take-profit-pct", type=float, default=6.0)
    parser.add_argument("--stop-loss-pct", type=float, default=5.0)
    parser.add_argument("--max-hold-days", type=int, default=15)
    args = parser.parse_args()

    log = setup_logging()
    ensure_dirs()
    settings = get_settings()
    symbols = [s.strip().upper().replace(".NS", "") for s in args.symbols.split(",") if s.strip()]
    use_kelly = not args.no_kelly and os.getenv("ALGO_USE_KELLY", "1").lower() in ("1", "true", "yes")

    log.info(
        "Portfolio backtest %s | Rs %.0f | %s-%s | Kelly=%s",
        ",".join(symbols),
        args.capital,
        args.start,
        args.end or "now",
        use_kelly,
    )

    result = run_portfolio_mean_reversion(
        symbols,
        total_capital=args.capital,
        start=args.start,
        end=args.end,
        commission_pct=settings.commission_pct,
        slippage_pct=settings.slippage_pct,
        use_kelly=use_kelly,
        bb_period=args.bb_period,
        bb_std=args.bb_std,
        rsi_entry=args.rsi_entry,
        take_profit_pct=args.take_profit_pct,
        stop_loss_pct=args.stop_loss_pct,
        max_hold_days=args.max_hold_days,
    )

    _print_table(result)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    tag = "_".join(symbols[:4])
    if len(symbols) > 4:
        tag += f"_plus{len(symbols) - 4}"
    summary_path = REPORT_DIR / f"portfolio_{tag}_{stamp}.summary.json"
    payload = {
        "portfolio_metrics": result["portfolio_metrics"],
        "per_symbol": result["per_symbol"],
        "meta": {
            "symbols": symbols,
            "total_capital": args.capital,
            "slice_capital": result["slice_capital"],
            "start": args.start,
            "end": args.end,
            "strategy": "mean_reversion",
            "kelly_sizing": use_kelly,
            "bb_period": args.bb_period,
            "rsi_entry": args.rsi_entry,
            "take_profit_pct": args.take_profit_pct,
            "stop_loss_pct": args.stop_loss_pct,
            "max_hold_days": args.max_hold_days,
            "note": "Equal-weight slices; Kelly estimated per symbol from its own trade history.",
        },
    }
    summary_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    log.info("Wrote summary %s", summary_path)


if __name__ == "__main__":
    main()
