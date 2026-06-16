"""Verify Groww API: token, margin, sample LTP (no orders)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from algo_trade.broker.groww_broker import get_cash_balance, get_groww_client, get_ltp


def main() -> None:
    print("=== Groww setup check ===\n")
    try:
        import credentials as cred  # type: ignore

        if not getattr(cred, "API_KEY", None) or not getattr(cred, "API_Secret", None):
            print("FAIL: set API_KEY and API_Secret in credentials.py")
            raise SystemExit(1)
        print("  [OK] credentials.py has API_KEY and API_Secret")
    except ImportError:
        print("FAIL: credentials.py not found")
        raise SystemExit(1) from None

    client = get_groww_client()
    print("  [OK] access token obtained")

    cash = get_cash_balance(client)
    print(f"  [OK] CNC balance available: Rs {cash:,.2f}")

    ltp = get_ltp(client, "SBIN")
    print(f"  [OK] SBIN LTP: Rs {ltp:,.2f}")

    print("\nGroww connection OK. Next:")
    print("  .venv\\Scripts\\python.exe scripts\\run_live_trading.py")
    print("  streamlit run dashboard/live_app.py")


if __name__ == "__main__":
    main()
