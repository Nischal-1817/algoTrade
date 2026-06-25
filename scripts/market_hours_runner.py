"""
Run live trading cycles during NSE cash session (09:00–15:30 IST, Mon–Fri).

Outside that window the process sleeps until the next open. During the window it
runs one cycle immediately, then every --interval-minutes (default 60).

For daily mean-reversion the important run is near the open (~09:20 IST); later
runs sync state but signals usually change only after the 15:30 close.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from datetime import datetime, timedelta, time as dt_time
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from algo_trade.broker import live_trading_allowed
from algo_trade.config import ensure_dirs
from algo_trade.live import run_dynamic_slot_cycle, run_portfolio_cycle
from algo_trade.logging_config import setup_logging

IST = ZoneInfo("Asia/Kolkata")
MARKET_OPEN = dt_time(9, 0)
MARKET_CLOSE = dt_time(15, 30)
logger = logging.getLogger("algo_trade.market_hours")


def _now_ist() -> datetime:
    return datetime.now(IST)


def in_market_window(now: datetime) -> bool:
    if now.weekday() >= 5:
        return False
    t = now.time()
    return MARKET_OPEN <= t <= MARKET_CLOSE


def seconds_until_next_open(now: datetime) -> float:
    """Seconds until the next weekday 09:00 IST."""
    target = datetime.combine(now.date(), MARKET_OPEN, tzinfo=IST)

    if now.weekday() >= 5:
        target += timedelta(days=(7 - now.weekday()))
    elif now.time() >= MARKET_CLOSE:
        target += timedelta(days=1)
    elif now.time() < MARKET_OPEN:
        pass
    else:
        return 60.0

    while target.weekday() >= 5:
        target += timedelta(days=1)

    if now >= target:
        target += timedelta(days=1)
        while target.weekday() >= 5:
            target += timedelta(days=1)

    return max(30.0, (target - now).total_seconds())


def seconds_until_close(now: datetime) -> float:
    close = datetime.combine(now.date(), MARKET_CLOSE, tzinfo=IST)
    return max(0.0, (close - now).total_seconds())


def run_once(
    *,
    mode: str,
    symbols: list[str],
    capital: float,
    max_slots: int,
    live: bool,
    history_start: str,
) -> None:
    dry_run = not live
    if mode == "dynamic":
        out = run_dynamic_slot_cycle(
            portfolio_capital=capital,
            max_slots=max_slots,
            dry_run=dry_run,
            history_start=history_start,
        )
    else:
        out = run_portfolio_cycle(
            symbols,
            portfolio_capital=capital,
            dry_run=dry_run,
            history_start=history_start,
        )
    for r in out.get("results", []):
        if "error" in r:
            logger.error("%s: %s", r.get("symbol"), r["error"])
        else:
            rank = f" #{r['watchlist_rank']}" if r.get("watchlist_rank") else ""
            logger.info(
                "%s%s %s qty=%s",
                r.get("symbol"),
                rank,
                r.get("action", "").upper(),
                r.get("qty"),
            )


def main() -> None:
    parser = argparse.ArgumentParser(description="Market-hours live trading loop (IST)")
    parser.add_argument(
        "--mode",
        choices=("dynamic", "fixed"),
        default=os.getenv("ALGO_MODE", "dynamic"),
    )
    parser.add_argument(
        "--max-slots",
        type=int,
        default=int(os.getenv("ALGO_MAX_SLOTS", "4")),
    )
    parser.add_argument(
        "--symbols",
        default=os.getenv("ALGO_SYMBOLS", "ICICIBANK,ITC,RELIANCE,TCS"),
        help="Used only when --mode fixed",
    )
    parser.add_argument(
        "--capital",
        type=float,
        default=float(os.getenv("ALGO_CAPITAL", os.getenv("ALGO_MAX_CAPITAL", "20000"))),
    )
    parser.add_argument("--start", default="2020-01-01")
    parser.add_argument("--interval-minutes", type=int, default=60)
    parser.add_argument(
        "--live",
        action="store_true",
        help="Real orders (also set ENABLE_LIVE_TRADING + LIVE_TRADING_CONFIRM in .env)",
    )
    parser.add_argument("--once", action="store_true", help="Single cycle if in window, then exit")
    args = parser.parse_args()

    setup_logging()
    ensure_dirs()
    symbols = [s.strip().upper().replace(".NS", "") for s in args.symbols.split(",") if s.strip()]
    live = args.live or live_trading_allowed()
    interval = max(15, args.interval_minutes) * 60

    logger.info(
        "Market-hours runner | mode=%s | slots=%d | capital=%.0f | live=%s | interval=%dm",
        args.mode,
        args.max_slots,
        args.capital,
        live,
        args.interval_minutes,
    )

    while True:
        now = _now_ist()
        if in_market_window(now):
            logger.info("Market open window — running cycle (%s IST)", now.strftime("%H:%M"))
            try:
                run_once(
                    mode=args.mode,
                    symbols=symbols,
                    capital=args.capital,
                    max_slots=args.max_slots,
                    live=live,
                    history_start=args.start,
                )
            except Exception:
                logger.exception("Cycle failed")

            if args.once:
                return

            if seconds_until_close(now) <= 0:
                nap = seconds_until_next_open(now)
                logger.info("Session ended — sleeping %.0f min until next open", nap / 60)
                time.sleep(nap)
                continue

            nap = min(interval, seconds_until_close(now))
            logger.info("Next cycle in %.0f min", nap / 60)
            time.sleep(nap)
        else:
            nap = seconds_until_next_open(now)
            logger.info(
                "Outside 09:00–15:30 IST (now %s) — sleeping %.0f min until next open",
                now.strftime("%a %H:%M"),
                nap / 60,
            )
            time.sleep(nap)


if __name__ == "__main__":
    main()
