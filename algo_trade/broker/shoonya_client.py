"""
Shoonya (Finvasia) via NorenRestApiPy.

Credentials: credentials.py or env vars (see credentials.example.py / .env.example).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import requests

from algo_trade.config import DATA_DIR

logger = logging.getLogger("algo_trade.broker.shoonya")


# Official live endpoints (Finvasia / ShoonyaApi-py README). Support may also mention NorenWSTV —
# QuickAuth on WSTV returned 404 in tests; WClientTP is used for login.
SHOONYA_HOST = os.getenv(
    "SHOONYA_API_HOST", "https://api.shoonya.com/NorenWClientTP/"
)
SHOONYA_WEBSOCKET = os.getenv(
    "SHOONYA_WEBSOCKET", "wss://api.shoonya.com/NorenWSTP/"
)


class ShoonyaApiPy:
    """Lazy import of Noren API with Shoonya endpoints (same pattern as Shoonya support notebooks)."""

    _api = None

    @classmethod
    def create(cls):
        if cls._api is not None:
            return cls._api
        from NorenRestApiPy.NorenApi import NorenApi

        host = SHOONYA_HOST
        websocket = SHOONYA_WEBSOCKET

        class _Api(NorenApi):
            def __init__(self):
                NorenApi.__init__(self, host=host, websocket=websocket)

        cls._api = _Api()
        return cls._api


@dataclass
class ShoonyaCredentials:
    user_id: str
    password: str
    totp_secret: str
    vendor_code: str
    api_secret: str
    imei: str = "abc1234"


def load_shoonya_credentials() -> Optional[ShoonyaCredentials]:
    try:
        import credentials as cred  # type: ignore

        return ShoonyaCredentials(
            user_id=cred.SHOONYA_USER_ID,
            password=cred.SHOONYA_PASSWORD,
            totp_secret=cred.SHOONYA_TOTP_SECRET,
            vendor_code=cred.SHOONYA_VENDOR_CODE,
            api_secret=cred.SHOONYA_API_SECRET,
            imei=getattr(cred, "SHOONYA_IMEI", "abc1234"),
        )
    except Exception:
        pass
    uid = os.getenv("SHOONYA_USER_ID")
    pwd = os.getenv("SHOONYA_PASSWORD")
    totp = os.getenv("SHOONYA_TOTP_SECRET")
    vc = os.getenv("SHOONYA_VENDOR_CODE")
    sec = os.getenv("SHOONYA_API_SECRET")
    if uid and pwd and totp and vc and sec:
        return ShoonyaCredentials(
            user_id=uid,
            password=pwd,
            totp_secret=totp,
            vendor_code=vc,
            api_secret=sec,
            imei=os.getenv("SHOONYA_IMEI", "abc1234"),
        )
    return None


def _totp_code(secret: str) -> str:
    from pyotp import TOTP

    return TOTP(secret.replace(" ", "").upper()).now().zfill(6)


def _login_via_http(cred: ShoonyaCredentials, host: str) -> dict:
    """Direct QuickAuth POST (used to surface HTTP status when NorenApi swallows HTML)."""
    otp = _totp_code(cred.totp_secret)
    pwd = hashlib.sha256(cred.password.encode("utf-8")).hexdigest()
    app_key = hashlib.sha256(f"{cred.user_id}|{cred.api_secret}".encode("utf-8")).hexdigest()
    values = {
        "source": "API",
        "apkversion": "1.0.0",
        "uid": cred.user_id,
        "pwd": pwd,
        "factor2": otp,
        "vc": cred.vendor_code,
        "appkey": app_key,
        "imei": cred.imei,
    }
    base = host if host.endswith("/") else host + "/"
    url = f"{base}QuickAuth"
    res = requests.post(url, data="jData=" + json.dumps(values), timeout=45)
    text = (res.text or "").strip()
    if res.status_code != 200:
        raise RuntimeError(
            f"Shoonya HTTP {res.status_code} at {url} — "
            f"body: {text[:200] if text else '(empty)'}"
        )
    if not text or text.startswith("<"):
        raise RuntimeError(
            f"Shoonya HTML/empty at {url} (often 502 Bad Gateway). Body: {text[:200]}"
        )
    ret = json.loads(text)
    if ret.get("stat") != "Ok":
        raise RuntimeError(f"Shoonya login failed: {ret.get('emsg', ret)}")
    return ret


def login(api: Any, cred: ShoonyaCredentials) -> dict:
    """
    Login like Shoonya support notebooks: NorenApi.login + TOTP.
    Falls back to explicit HTTP if the library raises JSONDecodeError on 502 HTML.
    """
    otp = _totp_code(cred.totp_secret)
    try:
        ret = api.login(
            userid=cred.user_id,
            password=cred.password,
            twoFA=otp,
            vendor_code=cred.vendor_code,
            api_secret=cred.api_secret,
            imei=cred.imei,
        )
    except json.JSONDecodeError:
        ret = None
    except Exception as e:
        raise RuntimeError(f"Shoonya login error: {e}") from e

    if not ret or ret.get("stat") != "Ok":
        emsg = ret.get("emsg", ret) if isinstance(ret, dict) else "no JSON response"
        if ret is None or (isinstance(ret, dict) and ret.get("stat") != "Ok"):
            try:
                ret = _login_via_http(cred, SHOONYA_HOST)
            except RuntimeError as http_err:
                raise RuntimeError(
                    f"Shoonya login failed ({emsg}). HTTP detail: {http_err}"
                ) from http_err
        else:
            raise RuntimeError(f"Shoonya login failed: {emsg}")

    if ret.get("stat") != "Ok":
        raise RuntimeError(f"Shoonya login failed: {ret.get('emsg', ret)}")

    api.set_session(cred.user_id, cred.password, ret["susertoken"])
    session_path = DATA_DIR / "shoonya_session.json"
    session_path.write_text(json.dumps(ret, indent=2, default=str), encoding="utf-8")
    logger.info("Shoonya login OK for %s via %s", cred.user_id, SHOONYA_HOST)
    return ret


def get_authenticated_api(*, force_login: bool = False) -> Any:
    cred = load_shoonya_credentials()
    if not cred:
        raise RuntimeError(
            "Missing Shoonya credentials. Fill credentials.py or SHOONYA_* env vars "
            "(see credentials.example.py)."
        )
    api = ShoonyaApiPy.create()
    if not force_login:
        session_path = DATA_DIR / "shoonya_session.json"
        if session_path.exists():
            try:
                sess = json.loads(session_path.read_text(encoding="utf-8"))
                token = sess.get("susertoken")
                if token:
                    api.set_session(
                        userid=cred.user_id,
                        password=cred.password,
                        usertoken=token,
                    )
                    lim = api.get_limits()
                    if lim and lim.get("stat") == "Ok":
                        return api
            except Exception as e:
                logger.debug("Session reuse failed, re-login: %s", e)
    login(api, cred)
    return api


def live_trading_allowed() -> bool:
    ok = os.getenv("ENABLE_LIVE_TRADING", "").lower() in ("1", "true", "yes")
    phrase = os.getenv("LIVE_TRADING_CONFIRM", "")
    shoonya = os.getenv("ALLOW_SHOONYA_ORDERS", "").lower() in ("1", "true", "yes")
    return ok and phrase == "I_UNDERSTAND_RISK" and shoonya


def resolve_symbol(api: Any, symbol: str) -> tuple[str, str]:
    """NSE cash: (tradingsymbol e.g. SBIN-EQ, token)."""
    sym = symbol.strip().upper().replace(".NS", "")
    if sym.endswith("-EQ"):
        ret = api.searchscrip(exchange="NSE", searchtext=sym.replace("-EQ", ""))
        if ret and ret.get("stat") == "Ok":
            for v in ret.get("values") or []:
                if v.get("tsym") == sym:
                    return sym, str(v.get("token", ""))
        return sym, ""
    ret = api.searchscrip(exchange="NSE", searchtext=sym)
    if not ret or ret.get("stat") != "Ok":
        raise RuntimeError(f"searchscrip failed for {sym}: {ret}")
    values = ret.get("values") or []
    for v in values:
        tsym = v.get("tsym", "")
        if tsym == f"{sym}-EQ" or (tsym.endswith("-EQ") and sym in tsym):
            return tsym, str(v.get("token", ""))
    if values:
        v = values[0]
        return v["tsym"], str(v.get("token", ""))
    raise RuntimeError(f"No NSE EQ symbol found for {sym}")


def resolve_trading_symbol(api: Any, symbol: str) -> str:
    return resolve_symbol(api, symbol)[0]


def get_cash_balance(api: Any) -> float:
    lim = api.get_limits()
    if not lim or lim.get("stat") != "Ok":
        raise RuntimeError(f"get_limits failed: {lim}")
    for key in ("cash", "availablecash", "availablemargin"):
        if key in lim and lim[key] not in (None, ""):
            try:
                return float(lim[key])
            except (TypeError, ValueError):
                continue
    return 0.0


def get_ltp(api: Any, exchange: str, token: str) -> float:
    q = api.get_quotes(exchange=exchange, token=token)
    if isinstance(q, list) and q:
        q = q[0]
    if not q or q.get("stat") != "Ok":
        raise RuntimeError(f"get_quotes failed for token {token}: {q}")
    return float(q.get("lp") or q.get("ltp") or 0)


def place_cnc_market(
    api: Any,
    *,
    buy: bool,
    trading_symbol: str,
    quantity: int,
    remarks: str = "algo_trade",
) -> dict:
    if quantity < 1:
        raise ValueError("quantity must be >= 1")
    side = "B" if buy else "S"
    if not live_trading_allowed():
        payload = {
            "status": "dry_run",
            "buy_or_sell": side,
            "tradingsymbol": trading_symbol,
            "quantity": quantity,
            "remarks": remarks,
        }
        logger.warning("DRY RUN — Shoonya order not sent: %s", payload)
        return payload
    ret = api.place_order(
        buy_or_sell=side,
        product_type="C",
        exchange="NSE",
        tradingsymbol=trading_symbol,
        quantity=quantity,
        discloseqty=0,
        price_type="MKT",
        price=0.0,
        retention="DAY",
        amo="NO",
        remarks=remarks,
    )
    if not ret or ret.get("stat") != "Ok":
        raise RuntimeError(f"place_order failed: {ret}")
    return ret
