"""
Shoonya login test — same flow as support notebook (Cells 1–4).

Usage (from project root, with venv):
  .venv\\Scripts\\python.exe scripts\\shoonya_notebook_login.py

Credentials: credentials.py (SHOONYA_* fields) or env vars.

Notes:
  - Uses official host NorenWClientTP (QuickAuth). WSTV/QuickAuth returns 404.
  - Sudhakar's snippet must use __init__, not init.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pyotp
from NorenRestApiPy.NorenApi import NorenApi

from algo_trade.broker.shoonya_client import SHOONYA_HOST, SHOONYA_WEBSOCKET, load_shoonya_credentials


class ShoonyaApi(NorenApi):
    """Match support notebook; fixed __init__ and official endpoints."""

    def __init__(self):
        NorenApi.__init__(self, host=SHOONYA_HOST, websocket=SHOONYA_WEBSOCKET)


def main() -> None:
    cred = load_shoonya_credentials()
    if not cred:
        print("Missing credentials — fill credentials.py (SHOONYA_* fields).")
        raise SystemExit(1)

    user_id = cred.user_id
    password = cred.password
    api_key = cred.api_secret
    vendor_code = cred.vendor_code
    totp_secret = cred.totp_secret
    imei = cred.imei

    print("Credentials loaded.")
    print(f"Host: {SHOONYA_HOST}")

    api = ShoonyaApi()

    try:
        totp = pyotp.TOTP(totp_secret.replace(" ", "").upper()).now().zfill(6)
        print(f"Generated current TOTP: {totp[:2]}**** (hidden)")

        login_response = api.login(
            userid=user_id,
            password=password,
            twoFA=totp,
            vendor_code=vendor_code,
            api_secret=api_key,
            imei=imei,
        )

        if login_response and login_response.get("stat") == "Ok":
            print("Shoonya API login successful.")
            print("Token present:", bool(login_response.get("susertoken")))
        else:
            emsg = login_response.get("emsg") if login_response else "no response"
            print("Login failed:", emsg)
            raise SystemExit(1)

        limits = api.get_limits()
        if limits and limits.get("stat") == "Ok":
            print(f"Account: {limits.get('actid')}")
            print(f"Available margin cash: {limits.get('cash')}")
        else:
            print("Failed to fetch account limits:", limits)
            raise SystemExit(1)

    except Exception as e:
        print("Error during execution:", e)
        raise SystemExit(1) from e


if __name__ == "__main__":
    main()
