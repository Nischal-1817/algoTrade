"""
Flask gateway for algo trading on AWS (fixed IP for broker whitelist).

Run on EC2; call from your laptop via HTTPS + GATEWAY_SECRET.
Broker API keys live on the server only — not on your home PC.
"""

from __future__ import annotations

import json
import os
import sys
from functools import wraps
from pathlib import Path

import requests as http_requests
from dotenv import load_dotenv
from flask import Flask, jsonify, request

# Parent repo root (algoTrade/) must be on path for algo_trade imports
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

load_dotenv(REPO_ROOT / ".env")
load_dotenv(Path(__file__).resolve().parent / ".env")

from algo_trade.broker.groww_broker import (  # noqa: E402
    get_cash_balance,
    get_groww_client,
    get_ltp,
    live_trading_allowed,
)
from algo_trade.config import DATA_DIR, ensure_dirs  # noqa: E402
from algo_trade.live import load_state, run_live_cycle  # noqa: E402
from algo_trade.logging_config import setup_logging  # noqa: E402

log = setup_logging()
app = Flask(__name__)

GATEWAY_SECRET = os.getenv("GATEWAY_SECRET", "")


def _auth_required(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if not GATEWAY_SECRET:
            return jsonify({"error": "GATEWAY_SECRET not set on server"}), 503
        auth = request.headers.get("Authorization", "")
        token = auth.removeprefix("Bearer ").strip() if auth else ""
        if not token:
            token = request.headers.get("X-API-Key", "").strip()
        if token != GATEWAY_SECRET:
            return jsonify({"error": "unauthorized"}), 401
        return f(*args, **kwargs)

    return wrapped


def _fetch_outbound_ip() -> str:
    r = http_requests.get("https://api.ipify.org?format=json", timeout=10)
    r.raise_for_status()
    return r.json()["ip"]


@app.get("/health")
def health():
    return jsonify({"status": "ok", "service": "algo-trade-gateway"})


@app.get("/api/public-ip")
def public_ip():
    """IP to whitelist on Groww / Shoonya (this EC2 instance)."""
    try:
        ip = _fetch_outbound_ip()
        return jsonify({"public_ip": ip, "note": "Whitelist this IP on your broker API dashboard"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.get("/api/status")
@_auth_required
def status():
    ensure_dirs()
    state = load_state()
    out = {
        "broker": os.getenv("ALGO_BROKER", "groww"),
        "live_orders_enabled": live_trading_allowed(),
        "algo_symbol": os.getenv("ALGO_SYMBOL", "SBIN"),
        "max_capital": os.getenv("ALGO_MAX_CAPITAL", "10000"),
        "state": state.to_dict() if state else None,
    }
    try:
        if os.getenv("ALGO_BROKER", "groww").lower() == "groww":
            client = get_groww_client()
            out["cash_balance"] = get_cash_balance(client)
            sym = state.symbol if state else os.getenv("ALGO_SYMBOL", "SBIN")
            out["ltp"] = get_ltp(client, sym)
    except Exception as e:
        out["broker_error"] = str(e)
    return jsonify(out)


@app.post("/api/run-cycle")
@_auth_required
def run_cycle():
    """Run one mean-reversion cycle (dry-run unless live env vars set on server)."""
    ensure_dirs()
    try:
        summary = run_live_cycle()
        return jsonify({"ok": True, "summary": summary})
    except Exception as e:
        log.exception("Gateway run-cycle failed")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.get("/api/state")
@_auth_required
def state_file():
    path = DATA_DIR / "algo_state.json"
    if not path.exists():
        return jsonify({"state": None})
    return jsonify(json.loads(path.read_text(encoding="utf-8")))


if __name__ == "__main__":
    host = os.getenv("GATEWAY_HOST", "0.0.0.0")
    port = int(os.getenv("GATEWAY_PORT", "8080"))
    debug = os.getenv("FLASK_DEBUG", "").lower() in ("1", "true", "yes")
    if not GATEWAY_SECRET:
        log.warning("GATEWAY_SECRET not set — protected routes will return 503")
    app.run(host=host, port=port, debug=debug)
