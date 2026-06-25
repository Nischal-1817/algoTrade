"""
Angel One SmartAPI wrapper.

Credentials: credentials.py or ANGELONE_* env vars (see credentials.example.py).
Orders require your machine's public IP whitelisted on the SmartAPI app.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from algo_trade.config import PROJECT_ROOT, DATA_DIR, get_settings

# Ensure .env is loaded before reading live-trading flags (systemd may not inject all vars).
load_dotenv(PROJECT_ROOT / ".env")

logger = logging.getLogger("algo_trade.broker.angel")

SESSION_PATH = DATA_DIR / "angelone_session.json"
SYMBOL_CACHE_PATH = DATA_DIR / "angel_symbol_cache.json"


@dataclass
class AngelCredentials:
    api_key: str
    client_id: str
    password: str
    totp_secret: str


def _totp_code(secret: str) -> str:
    from pyotp import TOTP

    return TOTP(secret).now()


def load_credentials() -> AngelCredentials:
    api_key = os.getenv("ANGELONE_API_KEY", "")
    client_id = os.getenv("ANGELONE_CLIENT_ID", "")
    password = os.getenv("ANGELONE_PASSWORD", "")
    totp_secret = os.getenv("ANGELONE_TOTP_SECRET", "")
    try:
        import credentials as cred  # type: ignore

        api_key = api_key or getattr(cred, "ANGELONE_API_KEY", "")
        client_id = client_id or getattr(cred, "ANGELONE_CLIENT_ID", "")
        password = password or getattr(cred, "ANGELONE_PASSWORD", "")
        totp_secret = totp_secret or getattr(cred, "ANGELONE_TOTP_SECRET", "")
    except ImportError:
        pass
    missing = [n for n, v in [
        ("ANGELONE_API_KEY", api_key),
        ("ANGELONE_CLIENT_ID", client_id),
        ("ANGELONE_PASSWORD", password),
        ("ANGELONE_TOTP_SECRET", totp_secret),
    ] if not v]
    if missing:
        raise ValueError(f"Missing Angel credentials: {', '.join(missing)}")
    return AngelCredentials(api_key, client_id, password, totp_secret)


def live_trading_allowed() -> bool:
    load_dotenv(PROJECT_ROOT / ".env")
    s = get_settings()
    ok = s.enable_live_trading and s.live_trading_confirm.strip() == "I_UNDERSTAND_REAL_MONEY"
    if not ok:
        logger.debug(
            "live_trading_allowed=False enable=%s confirm=%r",
            s.enable_live_trading,
            s.live_trading_confirm,
        )
    return ok


def _save_session(client_id: str, data: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "client_id": client_id,
        "jwtToken": data.get("jwtToken"),
        "refreshToken": data.get("refreshToken"),
        "feedToken": data.get("feedToken"),
    }
    SESSION_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _load_symbol_cache() -> dict[str, dict[str, str]]:
    if not SYMBOL_CACHE_PATH.exists():
        return {}
    try:
        return json.loads(SYMBOL_CACHE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save_symbol_cache(cache: dict[str, dict[str, str]]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SYMBOL_CACHE_PATH.write_text(json.dumps(cache, indent=2), encoding="utf-8")


def get_authenticated_client(*, force_login: bool = False):
    from SmartApi.smartConnect import SmartConnect

    creds = load_credentials()
    api = SmartConnect(api_key=creds.api_key)

    if not force_login and SESSION_PATH.exists():
        try:
            sess = json.loads(SESSION_PATH.read_text(encoding="utf-8"))
            api.setAccessToken(sess.get("jwtToken"))
            api.setRefreshToken(sess.get("refreshToken"))
            api.setFeedToken(sess.get("feedToken"))
            api.setUserId(sess.get("client_id", creds.client_id))
            rms = api.rmsLimit()
            if rms.get("status"):
                return api
            logger.info("Cached Angel session invalid, re-logging in")
        except Exception as exc:
            logger.warning("Could not reuse Angel session: %s", exc)

    totp = _totp_code(creds.totp_secret)
    session = api.generateSession(creds.client_id, creds.password, totp)
    if not session.get("status"):
        raise RuntimeError(session.get("message", "Angel login failed"))
    data = session["data"]
    _save_session(creds.client_id, data)
    return api


def get_cash_balance(api=None) -> float:
    api = api or get_authenticated_client()
    rms = api.rmsLimit()
    if not rms.get("status"):
        raise RuntimeError(rms.get("message", "getRMS failed"))
    return float(rms["data"].get("availablecash", 0))


def resolve_symbol(api, symbol: str, *, exchange: str = "NSE") -> dict[str, str]:
    """Return tradingsymbol + symboltoken for an NSE equity (e.g. ICICIBANK -> ICICIBANK-EQ)."""
    sym = symbol.strip().upper().replace(".NS", "").replace(".NSE", "")
    cache = _load_symbol_cache()
    if sym in cache:
        return cache[sym]

    result = api.searchScrip(exchange, sym)
    if not result.get("status") or not result.get("data"):
        raise ValueError(f"Angel symbol not found for {sym!r}")

    rows = result["data"]
    pick = None
    for row in rows:
        ts = row.get("tradingsymbol", "")
        if ts == f"{sym}-EQ":
            pick = row
            break
    if pick is None:
        for row in rows:
            if row.get("exchange") == exchange and str(row.get("tradingsymbol", "")).endswith("-EQ"):
                pick = row
                break
    if pick is None:
        pick = rows[0]

    out = {
        "tradingsymbol": str(pick["tradingsymbol"]),
        "symboltoken": str(pick["symboltoken"]),
        "exchange": str(pick.get("exchange", exchange)),
    }
    cache[sym] = out
    _save_symbol_cache(cache)
    return out


def get_ltp(api, symbol: str) -> float:
    scrip = resolve_symbol(api, symbol)
    resp = api.ltpData(scrip["exchange"], scrip["tradingsymbol"], scrip["symboltoken"])
    if not resp.get("status"):
        raise RuntimeError(resp.get("message", "LTP failed"))
    return float(resp["data"]["ltp"])


def get_holdings(api) -> list[dict[str, Any]]:
    resp = api.holding()
    if not resp.get("status"):
        raise RuntimeError(resp.get("message", "holdings failed"))
    return list(resp.get("data") or [])


def place_cnc_order(
    api,
    symbol: str,
    side: str,
    qty: int,
    *,
    dry_run: bool = True,
) -> dict[str, Any]:
    if qty <= 0:
        return {"skipped": True, "reason": "qty<=0"}
    scrip = resolve_symbol(api, symbol)
    params = {
        "variety": "NORMAL",
        "tradingsymbol": scrip["tradingsymbol"],
        "symboltoken": scrip["symboltoken"],
        "transactiontype": side.upper(),
        "exchange": scrip["exchange"],
        "ordertype": "MARKET",
        "producttype": "DELIVERY",
        "duration": "DAY",
        "quantity": str(qty),
    }
    if dry_run:
        logger.info("DRY-RUN %s %s x%d %s", side.upper(), symbol, qty, scrip["tradingsymbol"])
        return {"dry_run": True, "order": params}
    if not live_trading_allowed():
        raise RuntimeError(
            "Live orders blocked. Set ENABLE_LIVE_TRADING=1 and "
            "LIVE_TRADING_CONFIRM=I_UNDERSTAND_REAL_MONEY"
        )
    resp = api.placeOrderFullResponse(params)
    if not resp or not resp.get("status"):
        raise RuntimeError(str(resp))
    logger.info("Order placed %s %s x%d -> %s", side, symbol, qty, resp)
    return {"dry_run": False, "response": resp, "order": params}
