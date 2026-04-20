"""
Groww API wrapper. Real orders are blocked unless ENABLE_LIVE_TRADING=1 and
LIVE_TRADING_CONFIRM=I_UNDERSTAND_RISK (set in environment).

Default path: connect and fetch token in dry-run / info-only scenarios only.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger("algo_trade.broker")


def _market_order_type():
    """Resolve market order enum across growwapi versions."""
    from growwapi import GrowwAPI

    for name in ("ORDER_TYPE_MARKET", "ORDER_TYPE_MKT", "ORDER_TYPE_MARKET_ORDER"):
        if hasattr(GrowwAPI, name):
            return getattr(GrowwAPI, name)
    raise RuntimeError(
        "growwapi: no market order type constant found (ORDER_TYPE_MARKET). "
        "Upgrade: pip install -U growwapi — see https://groww.in/trade-api/docs/python-sdk/orders"
    )


@dataclass
class GrowwCredentials:
    api_key: str
    api_secret: str


def load_credentials_from_module() -> Optional[GrowwCredentials]:
    try:
        import credentials as cred  # type: ignore

        return GrowwCredentials(api_key=cred.API_KEY, api_secret=cred.API_Secret)
    except Exception:
        key = os.getenv("GROWW_API_KEY")
        sec = os.getenv("GROWW_API_SECRET")
        if key and sec:
            return GrowwCredentials(api_key=key, api_secret=sec)
    return None


def get_groww_client():
    """Returns GrowwAPI instance or raises if growwapi / credentials missing."""
    from growwapi import GrowwAPI

    c = load_credentials_from_module()
    if not c:
        raise RuntimeError(
            "No Groww credentials: add credentials.py (see credentials.example.py) "
            "or set GROWW_API_KEY and GROWW_API_SECRET."
        )
    token = GrowwAPI.get_access_token(api_key=c.api_key, secret=c.api_secret)
    return GrowwAPI(token)


def live_trading_allowed() -> bool:
    ok = os.getenv("ENABLE_LIVE_TRADING", "").lower() in ("1", "true", "yes")
    phrase = os.getenv("LIVE_TRADING_CONFIRM", "")
    return ok and phrase == "I_UNDERSTAND_RISK"


def place_market_order_example(
    *,
    trading_symbol: str,
    quantity: int,
    transaction_type_buy: bool,
) -> dict:
    """
    Example NSE CNC market order. Returns dry_run payload unless live env flags are set
    (ENABLE_LIVE_TRADING + LIVE_TRADING_CONFIRM=I_UNDERSTAND_RISK).
    """
    from growwapi import GrowwAPI

    side = GrowwAPI.TRANSACTION_TYPE_BUY if transaction_type_buy else GrowwAPI.TRANSACTION_TYPE_SELL
    market_ot = _market_order_type()
    payload = {
        "trading_symbol": trading_symbol,
        "quantity": quantity,
        "transaction_type": side,
        "order_type": market_ot,
        "exchange": GrowwAPI.EXCHANGE_NSE,
        "segment": GrowwAPI.SEGMENT_CASH,
        "product": GrowwAPI.PRODUCT_CNC,
    }
    if not live_trading_allowed():
        logger.warning("DRY RUN — order not sent. Set env to enable live. Payload: %s", payload)
        return {"status": "dry_run", "payload": {k: str(v) for k, v in payload.items()}}

    client = get_groww_client()
    return client.place_order(
        trading_symbol=trading_symbol,
        quantity=quantity,
        validity=GrowwAPI.VALIDITY_DAY,
        exchange=GrowwAPI.EXCHANGE_NSE,
        segment=GrowwAPI.SEGMENT_CASH,
        product=GrowwAPI.PRODUCT_CNC,
        order_type=market_ot,
        transaction_type=side,
    )
