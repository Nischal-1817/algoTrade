"""Run a simple NSE SMA backtest and write HTML + JSON summary."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from algo_trade.backtest import compute_metrics, run_long_only_next_open, write_html_report
from algo_trade.config import REPORT_DIR, get_settings, ensure_dirs
from algo_trade.data import fetch_daily_ohlcv
from algo_trade.logging_config import setup_logging
from algo_trade.strategy import add_mean_reversion_signals, add_signals


def main() -> None:
    parser = argparse.ArgumentParser(description="NSE backtest (Yahoo data)")
    parser.add_argument("--symbol", default=None, help="e.g. RELIANCE or RELIANCE.NS")
    parser.add_argument("--start", default="2018-01-01")
    parser.add_argument("--end", default=None)
    parser.add_argument(
        "--strategy",
        choices=("sma", "mean_reversion"),
        default="sma",
        help="sma = trend crossover; mean_reversion = buy low / sell high rules",
    )
    parser.add_argument("--fast", type=int, default=None)
    parser.add_argument("--slow", type=int, default=None)
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
    symbol = args.symbol or settings.default_symbol_yahoo
    fast = args.fast or settings.fast_sma
    slow = args.slow or settings.slow_sma

    ohlcv = fetch_daily_ohlcv(symbol, start=args.start, end=args.end)
    if args.strategy == "sma":
        log.info("Backtest %s %s-%s SMA %d/%d", symbol, args.start, args.end or "now", fast, slow)
        sig = add_signals(ohlcv, fast=fast, slow=slow)
        strategy_meta = {"strategy": "sma_crossover", "fast_sma": fast, "slow_sma": slow}
    else:
        log.info(
            "Backtest %s %s-%s mean_reversion BB=%d stop=%.1f%% tp=%.1f%%",
            symbol,
            args.start,
            args.end or "now",
            args.bb_period,
            args.stop_loss_pct,
            args.take_profit_pct,
        )
        sig = add_mean_reversion_signals(
            ohlcv,
            bb_period=args.bb_period,
            bb_std=args.bb_std,
            rsi_entry=args.rsi_entry,
            take_profit_pct=args.take_profit_pct,
            stop_loss_pct=args.stop_loss_pct,
            max_hold_days=args.max_hold_days,
        )
        strategy_meta = {
            "strategy": "mean_reversion",
            "bb_period": args.bb_period,
            "bb_std": args.bb_std,
            "rsi_entry": args.rsi_entry,
            "take_profit_pct": args.take_profit_pct,
            "stop_loss_pct": args.stop_loss_pct,
            "max_hold_days": args.max_hold_days,
        }
    use_kelly = os.getenv("ALGO_USE_KELLY", "1").lower() in ("1", "true", "yes")
    result = run_long_only_next_open(
        sig,
        initial_capital=settings.initial_capital,
        commission_pct=settings.commission_pct,
        slippage_pct=settings.slippage_pct,
        use_kelly_sizing=use_kelly,
    )
    metrics = compute_metrics(
        result["equity_curve"],
        result["trades"],
        initial_capital=settings.initial_capital,
    )
    meta = {
        "symbol": symbol,
        "start": str(ohlcv.index[0].date()),
        "end": str(ohlcv.index[-1].date()),
        "initial_capital": settings.initial_capital,
        "commission_pct": settings.commission_pct,
        "slippage_pct": settings.slippage_pct,
        "note": "Educational backtest; not investment advice. Data via Yahoo Finance.",
        "kelly_sizing": use_kelly,
        "last_kelly_fraction": result.get("last_kelly_fraction"),
        **strategy_meta,
    }
    report_path = write_html_report(
        symbol=symbol,
        ohlcv=sig,
        equity=result["equity_curve"],
        metrics=metrics,
        trades=result["trades"],
        meta=meta,
    )
    summary_path = report_path.with_suffix(".summary.json")
    summary_path.write_text(json.dumps({"metrics": metrics, "meta": meta}, indent=2, default=str), encoding="utf-8")
    log.info("Wrote report %s", report_path)
    log.info("Wrote summary %s", summary_path)


if __name__ == "__main__":
    main()
