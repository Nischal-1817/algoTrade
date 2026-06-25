"""Verify Angel One login, balance, and market data."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from algo_trade.broker import (
    get_authenticated_client,
    get_cash_balance,
    get_holdings,
    get_ltp,
    live_trading_allowed,
    load_credentials,
)
from algo_trade.logging_config import setup_logging


def main() -> None:
    log = setup_logging()
    creds = load_credentials()
    log.info("Angel client %s", creds.client_id)

    api = get_authenticated_client()
    cash = get_cash_balance(api)
    holdings = get_holdings(api)
    sbin_ltp = get_ltp(api, "SBIN")

    print()
    print("Angel One connection: OK")
    print(f"  Client ID:     {creds.client_id}")
    print(f"  Available:     Rs {cash:,.2f}")
    print(f"  Holdings:      {len(holdings)}")
    print(f"  SBIN LTP:      Rs {sbin_ltp:,.2f}  (market price, not your balance)")
    print(f"  Live orders:   {'ENABLED' if live_trading_allowed() else 'blocked (dry-run only)'}")
    print()
    if not live_trading_allowed():
        print("To enable real orders:")
        print("  $env:ENABLE_LIVE_TRADING='1'")
        print("  $env:LIVE_TRADING_CONFIRM='I_UNDERSTAND_REAL_MONEY'")
        print("  .\\.venv\\Scripts\\python.exe scripts\\run_live_trading.py --live")
        print()


if __name__ == "__main__":
    main()
