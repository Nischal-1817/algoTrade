"""Live cycle via Shoonya (optional; default broker is Groww)."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

from algo_trade.backtest.engine import run_long_only_next_open
from algo_trade.broker.shoonya_client import (
    get_authenticated_api,
    get_cash_balance,
    get_ltp,
    live_trading_allowed,
    place_cnc_market,
    resolve_symbol,
)
from algo_trade.config import get_settings
from algo_trade.data.shoonya_data import fetch_daily_ohlcv_shoonya
from algo_trade.live.state import AlgoState, init_state, load_state, save_state
from algo_trade.risk.kelly import (
    kelly_fraction_from_trades,
    load_kelly_config,
    position_size_inr,
)
from algo_trade.strategy.mean_reversion import add_mean_reversion_signals, live_action_from_history

logger = logging.getLogger("algo_trade.live.shoonya")


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
    return kelly_fraction_from_trades(bt.get("trades", []) + state.trades)


def run_live_cycle(*, force_login: bool = False) -> dict[str, Any]:
    symbol = os.getenv("ALGO_SYMBOL", "SBIN").strip().upper().replace(".NS", "")
    if not _allowed_symbol(symbol):
        raise RuntimeError(f"Symbol {symbol} not in ALGO_ALLOWED_SYMBOLS.")

    api = get_authenticated_api(force_login=force_login)
    tsym, token = resolve_symbol(api, symbol)
    cash = get_cash_balance(api)
    ltp = get_ltp(api, "NSE", token)

    state = load_state()
    if state is None or state.symbol != symbol:
        state = init_state(symbol, tsym, token, _max_capital())
    state.trading_symbol = tsym
    state.token = token
    state.max_capital = _max_capital()

    ohlcv = fetch_daily_ohlcv_shoonya(symbol, api=api).rename(columns=str.lower)
    if state.in_position:
        state.bars_held += 1

    action = live_action_from_history(
        ohlcv,
        in_position=state.in_position,
        entry_close=state.entry_close,
        bars_held=state.bars_held,
    )
    state.last_action = action
    state.last_signal_note = f"action={action} ltp={ltp}"

    order_result = None
    if action == "buy" and not state.in_position:
        bankroll = min(state.max_capital, cash * 0.95)
        state.bankroll_inr = bankroll
        state.kelly_fraction = (
            _estimate_kelly_fraction(ohlcv, state)
            if load_kelly_config().enabled
            else 1.0
        )
        qty, _ = position_size_inr(bankroll, ltp, state.kelly_fraction)
        if qty >= 1:
            order_result = place_cnc_market(
                api, buy=True, trading_symbol=tsym, quantity=qty, remarks="algo_mr_buy"
            )
            if live_trading_allowed() or order_result.get("status") == "dry_run":
                state.in_position = True
                state.qty = qty
                state.entry_close = float(ohlcv["close"].iloc[-1])
                state.entry_time = datetime.now(timezone.utc).isoformat()
                state.bars_held = 0
                state.trades.append(
                    {"side": "BUY", "qty": qty, "price": ltp, "order": order_result}
                )
    elif action == "sell" and state.in_position and state.qty > 0:
        order_result = place_cnc_market(
            api, buy=False, trading_symbol=tsym, quantity=state.qty, remarks="algo_mr_sell"
        )
        if live_trading_allowed() or order_result.get("status") == "dry_run":
            state.trades.append({"side": "SELL", "qty": state.qty, "price": ltp})
            state.in_position = False
            state.qty = 0

    save_state(state)
    return {
        "broker": "shoonya",
        "symbol": symbol,
        "cash_balance": cash,
        "ltp": ltp,
        "action": action,
        "live_orders_enabled": live_trading_allowed(),
        "order_result": order_result,
        "trades": state.trades,
    }
