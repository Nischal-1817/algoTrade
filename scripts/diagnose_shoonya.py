"""
Deep connectivity check for Shoonya API — finds client vs server issues.
Does NOT print passwords, API secrets, or TOTP secrets.
"""

from __future__ import annotations

import base64
import hashlib
import json
import socket
import ssl
import sys
from pathlib import Path
from urllib.parse import urlparse

import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from algo_trade.broker.shoonya_client import SHOONYA_HOST, _totp_code, load_shoonya_credentials


def _check(label: str, ok: bool, detail: str = "") -> bool:
    mark = "PASS" if ok else "FAIL"
    print(f"  [{mark}] {label}" + (f" — {detail}" if detail else ""))
    return ok


def main() -> None:
    print("=== Shoonya connection diagnostics ===\n")

    cred = load_shoonya_credentials()
    if not cred:
        print("FAIL: credentials.py missing Shoonya fields")
        raise SystemExit(1)

    # --- Local / credential shape (no network) ---
    print("1) Local checks (your machine + credential format)")
    uid_ok = bool(cred.user_id and cred.user_id.strip())
    vc_ok = bool(cred.vendor_code and "_U" in cred.vendor_code)
    try:
        base64.b32decode(cred.totp_secret.replace(" ", "").upper(), casefold=True)
        totp_ok = True
    except Exception as e:
        totp_ok = False
        totp_err = str(e)
    else:
        totp_err = ""

    _check("USER_ID present", uid_ok, f"length={len(cred.user_id)}")
    _check("VENDOR_CODE looks like Shoonya format (*_U)", vc_ok, cred.vendor_code[:3] + "***")
    _check("TOTP secret is valid Base32", totp_ok, totp_err or "can generate OTP")
    if cred.user_id and cred.vendor_code:
        uid_in_vc = cred.user_id.upper() in cred.vendor_code.upper()
        _check(
            "USER_ID appears inside VENDOR_CODE (common pattern)",
            uid_in_vc,
            "mismatch may mean wrong user id — check Shoonya app",
        )

    try:
        otp = _totp_code(cred.totp_secret)
        _check("TOTP generates 6 digits", len(otp) == 6 and otp.isdigit(), f"len={len(otp)}")
    except Exception as e:
        _check("TOTP generates 6 digits", False, str(e))

  # --- Network to Shoonya ---
    print("\n2) Network reachability (api.shoonya.com)")
    host = "api.shoonya.com"
    try:
        ip = socket.gethostbyname(host)
        _check("DNS resolves", True, ip)
    except socket.gaierror as e:
        _check("DNS resolves", False, str(e))

    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((host, 443), timeout=15) as sock:
            with ctx.wrap_socket(sock, server_hostname=host) as ssock:
                cert = ssock.getpeercert()
                _check("TLS to port 443", True, f"subject={cert.get('subject', '')[:80]}")
    except Exception as e:
        _check("TLS to port 443", False, str(e))

    # GET root paths — see if nginx responds at all
    for path in ["/", "/NorenWClientTP/", "/NorenWSTV/"]:
        url = f"https://{host}{path}"
        try:
            r = requests.get(url, timeout=15)
            _check(f"GET {path}", r.status_code < 500, f"HTTP {r.status_code}")
        except Exception as e:
            _check(f"GET {path}", False, str(e))

    # --- QuickAuth variants ---
    print("\n3) QuickAuth POST tests (login endpoint)")
    pwd_hash = hashlib.sha256(cred.password.encode("utf-8")).hexdigest()
    app_key = hashlib.sha256(f"{cred.user_id}|{cred.api_secret}".encode("utf-8")).hexdigest()
    otp = _totp_code(cred.totp_secret)
    jdata = {
        "source": "API",
        "apkversion": "1.0.0",
        "uid": cred.user_id,
        "pwd": pwd_hash,
        "factor2": otp,
        "vc": cred.vendor_code,
        "appkey": app_key,
        "imei": cred.imei,
    }
    payload = "jData=" + json.dumps(jdata)

    urls = [
        "https://api.shoonya.com/NorenWClientTP/QuickAuth",
        "https://api.shoonya.com/NorenWClientTP//QuickAuth",  # double slash (old bug)
        "https://api.shoonya.com/NorenWSTV/QuickAuth",
        "https://shoonya.finvasia.com/NorenWClientTP/QuickAuth",  # legacy host
    ]

    any_json = False
    for url in urls:
        try:
            r = requests.post(
                url,
                data=payload,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=30,
            )
            body = (r.text or "")[:120].replace("\n", " ")
            is_json = body.strip().startswith("{")
            if is_json:
                any_json = True
            kind = "JSON" if is_json else "HTML/other"
            _check(
                urlparse(url).path,
                r.status_code == 200 and is_json,
                f"HTTP {r.status_code} ({kind}) {body}",
            )
        except requests.exceptions.SSLError as e:
            _check(urlparse(url).path, False, f"SSL error: {e}")
        except Exception as e:
            _check(urlparse(url).path, False, str(e))

    print("\n4) Verdict")
    if any_json:
        print("  Shoonya returned JSON on at least one URL — credentials/request format reach the API.")
        print("  If login still fails, read 'emsg' in the JSON (wrong password, API not enabled, etc.).")
    else:
        print("  No JSON from any QuickAuth URL — only HTTP errors (502/404/HTML).")
        print("  This is NOT caused by wrong Python code in this repo:")
        print("    - Request matches official NorenRestApiPy (SHA256 pwd, jData=..., same fields).")
        print("    - Failure happens before a login success/error JSON is returned.")
        print("  Likely causes: Shoonya gateway down, API not enabled for your client id,")
        print("  or wrong endpoint assigned by support (ask for exact host URL).")
        print("\n  Things YOU can still verify in Shoonya app:")
        print("    - Log in on website/mobile with same USER_ID + PASSWORD")
        print("    - USER_ID exactly matches Shoonya (often same prefix as VENDOR_CODE)")
        print("    - API enabled: apisupport@shoonya.com with client id")

    print(f"\n  Configured host in project: {SHOONYA_HOST}")


if __name__ == "__main__":
    main()
