"""
Live mean-reversion cycle via Groww (orders) + Yahoo (daily bars).

Only trades symbol/qty in algo_state.json — does not sell unrelated holdings.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

from algo_trade.backtest.engine import run_long_only_next_open
from algo_trade.broker.groww_broker import (
    get_cash_balance,
    get_groww_client,
    get_ltp,
    live_trading_allowed,
    place_cnc_market,
)
from algo_trade.config import get_settings
from algo_trade.data import fetch_daily_ohlcv
from algo_trade.live.state import AlgoState, init_state, load_state, save_state
from algo_trade.risk.kelly import (
    kelly_fraction_from_trades,
    load_kelly_config,
    position_size_inr,
)
from algo_trade.strategy.mean_reversion import add_mean_reversion_signals, live_action_from_history

logger = logging.getLogger("algo_trade.live.groww")


def _allowed_symbol(symbol: str) -> bool:
    allowed = os.getenv("ALGO_ALLOWED_SYMBOLS", "").strip().upper()
    if not allowed:
        return True
    sym = symbol.upper().replace(".NS", "")
    return sym in {s.strip().upper().replace(".NS", "") for s in allowed.split(",")}


def _max_capital() -> float:
    return float(os.getenv("ALGO_MAX_CAPITAL", "10000"))


def _estimate_kelly_fraction(ohlcv, state: AlgoState) -> float:
    settings = get_settings()
    sig = add_mean_reversion_signals(ohlcv)
    bt = run_long_only_next_open(
        sig,
        initial_capital=settings.initial_capital,
        commission_pct=settings.commission_pct,
        slippage_pct=settings.slippage_pct,
        use_kelly_sizing=False,
    )
    hist = bt.get("trades", [])
    live = [t for t in state.trades if t.get("side") == "SELL"]
    return kelly_fraction_from_trades(hist + live)


def run_live_cycle() -> dict[str, Any]:
    symbol = os.getenv("ALGO_SYMBOL", "SBIN").strip().upper().replace(".NS", "")
    if not _allowed_symbol(symbol):
        raise RuntimeError(
            f"Symbol {symbol} not in ALGO_ALLOWED_SYMBOLS. "
            "Use a symbol dedicated to this bot only."
        )

    client = get_groww_client()
    cash = get_cash_balance(client)
    ltp = get_ltp(client, symbol)

    state = load_state()
    if state is None or state.symbol != symbol:
        state = init_state(symbol, symbol, "", _max_capital())
    state.trading_symbol = symbol
    state.max_capital = _max_capital()

    ohlcv = fetch_daily_ohlcv(symbol, start=None)
    ohlcv = ohlcv.rename(columns=str.lower)

    if state.in_position:
        state.bars_held += 1

    action = live_action_from_history(
        ohlcv,
        in_position=state.in_position,
        entry_close=state.entry_close,
        bars_held=state.bars_held,
    )
    state.last_action = action
    state.last_signal_note = (
        f"broker=groww action={action} in_pos={state.in_position} "
        f"bars_held={state.bars_held} ltp={ltp} cash={cash}"
    )

    order_result: dict[str, Any] | None = None

    if action == "buy" and not state.in_position:
        bankroll = min(state.max_capital, cash * 0.95) if cash > 0 else state.max_capital
        state.bankroll_inr = bankroll
        kelly_cfg = load_kelly_config()
        state.kelly_fraction = (
            _estimate_kelly_fraction(ohlcv, state) if kelly_cfg.enabled else 1.0
        )
        qty, _spend = position_size_inr(bankroll, ltp, state.kelly_fraction)
        if qty < 1:
            state.last_signal_note += (
                f"; skip buy — kelly={state.kelly_fraction:.2%} "
                f"bankroll={bankroll:.0f} need 1 share @ {ltp:.2f}"
            )
        else:
            order_result = place_cnc_market(
                trading_symbol=symbol, quantity=qty, buy=True
            )
            if live_trading_allowed() or order_result.get("status") == "dry_run":
                state.in_position = True
                state.qty = qty
                state.entry_close = float(ohlcv["close"].iloc[-1])
                state.entry_time = datetime.now(timezone.utc).isoformat()
                state.bars_held = 0
                state.trades.append(
                    {
                        "side": "BUY",
                        "qty": qty,
                        "price": ltp,
                        "time": state.entry_time,
                        "order": order_result,
                        "dry_run": not live_trading_allowed(),
                    }
                )

    elif action == "sell" and state.in_position and state.qty > 0:
        order_result = place_cnc_market(
            trading_symbol=symbol, quantity=state.qty, buy=False
        )
        if live_trading_allowed() or order_result.get("status") == "dry_run":
            state.trades.append(
                {
                    "side": "SELL",
                    "qty": state.qty,
                    "price": ltp,
                    "time": datetime.now(timezone.utc).isoformat(),
                    "order": order_result,
                    "dry_run": not live_trading_allowed(),
                }
            )
            state.in_position = False
            state.qty = 0
            state.entry_close = None
            state.entry_time = None
            state.bars_held = 0

    save_state(state)

    return {
        "broker": "groww",
        "symbol": symbol,
        "cash_balance": cash,
        "cnc_balance_available": cash,
        "ltp": ltp,
        "action": action,
        "in_position": state.in_position,
        "algo_qty": state.qty,
        "max_capital": state.max_capital,
        "bankroll_inr": state.bankroll_inr,
        "kelly_fraction": state.kelly_fraction,
        "live_orders_enabled": live_trading_allowed(),
        "order_result": order_result,
        "last_signal_note": state.last_signal_note,
        "trades": state.trades,
    }
