"""Build read-only payload for the live trading dashboard (no secrets)."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from algo_trade.config import DATA_DIR, REPORT_DIR
from algo_trade.live.state import STATE_PATH, load_state
from algo_trade.universe.watchlist import WATCHLIST_PATH, load_watchlist

logger = logging.getLogger("algo_trade.live.dashboard_data")

PUBLIC_SNAPSHOT_PATH = DATA_DIR / "dashboard_public.json"


def _load_live_cycles(limit: int = 30) -> list[dict[str, Any]]:
    paths = sorted(REPORT_DIR.glob("live_cycle_*.json"), reverse=True)[:limit]
    rows: list[dict[str, Any]] = []
    for p in paths:
        try:
            rows.append(json.loads(p.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            continue
    return rows


def _orders_from_cycles(cycles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    orders: list[dict[str, Any]] = []
    for cycle in cycles:
        ts = cycle.get("timestamp", "")
        dry = cycle.get("dry_run", True)
        for r in cycle.get("results") or []:
            order = r.get("order")
            if not order or order.get("skipped"):
                continue
            if order.get("dry_run") or dry:
                tag = "DRY-RUN"
            else:
                tag = "LIVE"
            o = order.get("order") or order
            orders.append(
                {
                    "time": ts,
                    "tag": tag,
                    "symbol": r.get("symbol"),
                    "action": r.get("action", "").upper(),
                    "qty": r.get("qty"),
                    "ltp": r.get("ltp"),
                    "kelly_fraction": r.get("kelly_fraction"),
                    "watchlist_rank": r.get("watchlist_rank"),
                    "transactiontype": o.get("transactiontype"),
                    "tradingsymbol": o.get("tradingsymbol"),
                    "order_id": (order.get("response") or {}).get("data", {}).get("orderid"),
                }
            )
    return orders


def _pnl_summary(
    holdings: list[dict[str, Any]],
    state_symbols: dict[str, Any],
    slice_capital: float,
) -> dict[str, Any]:
    realized = 0.0
    closed_trades = 0
    for sym, data in state_symbols.items():
        for ret_pct in data.get("trade_returns_pct") or []:
            realized += slice_capital * float(ret_pct) / 100.0
            closed_trades += 1

    unrealized = 0.0
    for row in holdings:
        try:
            unrealized += float(row.get("profitandloss") or 0)
        except (TypeError, ValueError):
            qty = float(row.get("quantity") or 0)
            avg = float(row.get("averageprice") or row.get("avgprice") or 0)
            ltp = float(row.get("ltp") or 0)
            if qty and avg and ltp:
                unrealized += (ltp - avg) * qty

    return {
        "realized_inr": round(realized, 2),
        "unrealized_inr": round(unrealized, 2),
        "total_inr": round(realized + unrealized, 2),
        "closed_trades": closed_trades,
    }


def _broker_snapshot() -> dict[str, Any]:
    try:
        from algo_trade.broker import get_authenticated_client, get_cash_balance, get_holdings

        api = get_authenticated_client()
        cash = get_cash_balance(api)
        holdings = get_holdings(api)
        return {
            "ok": True,
            "available_cash": cash,
            "holdings": holdings,
        }
    except Exception as exc:
        logger.warning("Broker snapshot failed: %s", exc)
        return {"ok": False, "error": str(exc), "available_cash": None, "holdings": []}


def build_dashboard_snapshot(*, include_broker: bool = True) -> dict[str, Any]:
    state = load_state()
    watchlist = load_watchlist()
    cycles = _load_live_cycles()
    slice_capital = 5000.0
    if state.portfolio_capital:
        slice_capital = state.portfolio_capital / 4.0

    broker = _broker_snapshot() if include_broker else {"ok": False, "holdings": []}
    holdings = broker.get("holdings") or []

    state_dict = {
        sym: {
            "in_position": s.in_position,
            "qty": s.qty,
            "entry_price": s.entry_price,
            "entry_close": s.entry_close,
            "bars_held": s.bars_held,
            "trade_returns_pct": s.trade_returns_pct,
        }
        for sym, s in state.symbols.items()
    }

    pnl = _pnl_summary(holdings, state_dict, slice_capital)
    orders = _orders_from_cycles(cycles)

    held = []
    for row in holdings:
        ts = str(row.get("tradingsymbol", ""))
        sym = ts.replace("-EQ", "") if ts.endswith("-EQ") else ts
        held.append(
            {
                "symbol": sym,
                "tradingsymbol": ts,
                "qty": row.get("quantity"),
                "avg_price": row.get("averageprice") or row.get("avgprice"),
                "ltp": row.get("ltp"),
                "pnl": row.get("profitandloss"),
            }
        )

    return {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "portfolio_capital": state.portfolio_capital or 20_000.0,
        "slice_capital": slice_capital,
        "max_slots": 4,
        "mode": "dynamic",
        "watchlist_top10": (watchlist.get("symbols") or [])[:10],
        "watchlist_generated_at": watchlist.get("generated_at"),
        "broker_ok": broker.get("ok", False),
        "available_cash": broker.get("available_cash"),
        "holdings": held,
        "pnl": pnl,
        "algo_state": state_dict,
        "last_run": state.last_run,
        "recent_cycles": [
            {
                "timestamp": c.get("timestamp"),
                "dry_run": c.get("dry_run"),
                "held_symbols": c.get("held_symbols", []),
                "results_count": len(c.get("results") or []),
                "actions": [
                    {"symbol": r.get("symbol"), "action": r.get("action"), "qty": r.get("qty")}
                    for r in (c.get("results") or [])
                    if r.get("symbol")
                ],
            }
            for c in cycles[:15]
        ],
        "orders": orders[:50],
    }


def save_public_snapshot(path: Path | None = None) -> Path:
    path = path or PUBLIC_SNAPSHOT_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = build_dashboard_snapshot()
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    logger.info("Wrote dashboard snapshot %s", path)
    return path
