"""Run one Angel One live portfolio cycle (mean reversion + Kelly)."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from algo_trade.broker import live_trading_allowed
from algo_trade.config import REPORT_DIR, ensure_dirs
from algo_trade.live import run_dynamic_slot_cycle, run_portfolio_cycle
from algo_trade.logging_config import setup_logging

DEFAULT_SYMBOLS = "ICICIBANK,ITC,RELIANCE,TCS"


def main() -> None:
    parser = argparse.ArgumentParser(description="Angel One live trading cycle")
    parser.add_argument(
        "--mode",
        choices=("dynamic", "fixed"),
        default=os.getenv("ALGO_MODE", "dynamic"),
    )
    parser.add_argument("--max-slots", type=int, default=int(os.getenv("ALGO_MAX_SLOTS", "4")))
    parser.add_argument("--symbols", default=DEFAULT_SYMBOLS, help="fixed mode only")
    parser.add_argument("--capital", type=float, default=20_000.0)
    parser.add_argument("--start", default="2020-01-01", help="History start for signals")
    parser.add_argument(
        "--live",
        action="store_true",
        help="Place REAL orders (also needs ENABLE_LIVE_TRADING=1 and LIVE_TRADING_CONFIRM)",
    )
    args = parser.parse_args()

    log = setup_logging()
    ensure_dirs()
    symbols = [s.strip().upper().replace(".NS", "") for s in args.symbols.split(",") if s.strip()]
    dry_run = not args.live

    if args.live and not live_trading_allowed():
        log.error(
            "Refusing --live without safety env vars. Set:\n"
            "  ENABLE_LIVE_TRADING=1\n"
            "  LIVE_TRADING_CONFIRM=I_UNDERSTAND_REAL_MONEY"
        )
        raise SystemExit(1)

    if dry_run:
        log.warning("DRY-RUN mode — no real orders. Pass --live to trade (with env safety flags).")

    if args.mode == "dynamic":
        out = run_dynamic_slot_cycle(
            portfolio_capital=args.capital,
            max_slots=args.max_slots,
            dry_run=dry_run,
            history_start=args.start,
        )
    else:
        out = run_portfolio_cycle(
            symbols,
            portfolio_capital=args.capital,
            dry_run=dry_run,
            history_start=args.start,
        )

    print()
    print(f"Mode: {'DRY-RUN' if dry_run else 'LIVE'} | {out.get('mode', args.mode)}")
    print(f"Cash: Rs {out['available_cash']:,.2f}")
    if args.mode == "dynamic":
        print(
            f"Portfolio: Rs {out['portfolio_capital']:,.0f} | "
            f"{out['max_slots']} slots x Rs {out['slice_capital']:,.0f} | "
            f"watchlist {out['watchlist_size']} | held {out.get('held_symbols', [])}"
        )
    else:
        print(f"Portfolio: Rs {out['portfolio_capital']:,.0f} | slice Rs {out['slice_capital']:,.0f}")
    print()
    for r in out["results"]:
        if "error" in r:
            print(f"  {r['symbol']}: ERROR — {r['error']}")
            continue
        extra = ""
        if r.get("qty"):
            extra = f" qty={r['qty']}"
        if r.get("kelly_fraction") is not None:
            extra += f" kelly={r['kelly_fraction']:.2f}"
        if r.get("watchlist_rank"):
            extra += f" rank={r['watchlist_rank']}"
        print(f"  {r['symbol']}: {r['action'].upper()}{extra}")
    print()

    stamp = out["timestamp"].replace(":", "").replace("-", "")[:15]
    path = REPORT_DIR / f"live_cycle_{stamp}.json"
    path.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    log.info("Wrote %s", path)


if __name__ == "__main__":
    main()
