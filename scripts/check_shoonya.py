"""Verify Shoonya login and show cash balance (no orders)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from algo_trade.broker.shoonya_client import get_authenticated_api, get_cash_balance, resolve_symbol
from algo_trade.logging_config import setup_logging


def main() -> None:
    log = setup_logging()
    api = get_authenticated_api(force_login=True)
    cash = get_cash_balance(api)
    sym = __import__("os").getenv("ALGO_SYMBOL", "SBIN")
    tsym, token = resolve_symbol(api, sym)
    log.info("Shoonya OK. Cash balance ~ %.2f INR. Symbol %s -> %s (token %s)", cash, sym, tsym, token)
    log.info("No orders placed.")


if __name__ == "__main__":
    main()
