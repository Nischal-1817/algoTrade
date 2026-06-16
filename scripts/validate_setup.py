"""Check what is configured before live trading."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> None:
    print("=== algoTrade setup check ===\n")
    shoonya_fields = [
        "SHOONYA_USER_ID",
        "SHOONYA_PASSWORD",
        "SHOONYA_TOTP_SECRET",
        "SHOONYA_VENDOR_CODE",
        "SHOONYA_API_SECRET",
    ]
    try:
        import credentials as cred  # type: ignore

        print("credentials.py found.")
        missing = []
        for f in shoonya_fields:
            val = getattr(cred, f, None)
            if not val or str(val).startswith("your_") or "BASE32" in str(val):
                missing.append(f)
            else:
                print(f"  OK  {f}")
        for f in missing:
            print(f"  MISSING  {f}")
        if missing:
            print("\nAdd Shoonya fields to credentials.py (see credentials.example.py).")
            raise SystemExit(1)
    except ImportError:
        print("credentials.py not found — copy credentials.example.py")
        raise SystemExit(1) from None

    print("\nShoonya fields present. Testing login...")
    from algo_trade.broker.shoonya_client import get_authenticated_api, get_cash_balance

    api = get_authenticated_api(force_login=True)
    cash = get_cash_balance(api)
    print(f"Login OK. Cash balance ~ Rs {cash:,.2f}")
    print("\nNext: python scripts/run_live_trading.py")
    print("Dashboard: streamlit run dashboard/live_app.py")


if __name__ == "__main__":
    main()
