"""
Angel One live cycle: mean-reversion signals + Kelly sizing.

Dry-run by default. Real CNC orders only when dry_run=False and live_trading_allowed().
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from algo_trade.broker.angelone_broker import (
    get_authenticated_client,
    get_cash_balance,
    get_holdings,
    get_ltp,
    live_trading_allowed,
    place_cnc_order,
)
from algo_trade.data import fetch_daily_ohlcv
from algo_trade.live.state import AlgoState, SymbolState, load_state, save_state
from algo_trade.risk.kelly import kelly_fraction_from_trade_returns, load_kelly_config, position_size_inr
from algo_trade.strategy.mean_reversion import live_action_from_history

logger = logging.getLogger("algo_trade.live.angel")

DEFAULT_SYMBOLS = ("ICICIBANK", "ITC", "RELIANCE", "TCS")


def _holding_qty(holdings: list[dict[str, Any]], symbol: str) -> int:
    sym = symbol.upper()
    for row in holdings:
        ts = str(row.get("tradingsymbol", "")).upper()
        if ts == f"{sym}-EQ" or ts.startswith(sym):
            return int(float(row.get("quantity", 0) or 0))
    return 0


def _sync_from_broker(sym_state: SymbolState, holdings: list[dict[str, Any]], symbol: str) -> None:
    qty = _holding_qty(holdings, symbol)
    if qty > 0:
        sym_state.in_position = True
        sym_state.qty = qty
    elif not sym_state.in_position:
        sym_state.qty = 0


def _record_exit(state: AlgoState, sym_state: SymbolState, exit_price: float) -> None:
    if sym_state.entry_price and sym_state.entry_price > 0:
        ret = (exit_price / sym_state.entry_price - 1.0) * 100.0
        sym_state.trade_returns_pct.append(ret)
        state.trade_returns_pct.append(ret)
    sym_state.in_position = False
    sym_state.entry_close = None
    sym_state.entry_price = None
    sym_state.qty = 0
    sym_state.bars_held = 0
    sym_state.entry_date = None
    sym_state.last_processed_bar = None


def run_symbol_cycle(
    api,
    symbol: str,
    *,
    slice_capital: float,
    state: AlgoState,
    sym_state: SymbolState,
    holdings: list[dict[str, Any]],
    dry_run: bool,
    history_start: str = "2020-01-01",
    bb_period: int = 20,
    bb_std: float = 2.0,
    rsi_entry: float = 35.0,
    take_profit_pct: float = 6.0,
    stop_loss_pct: float = 5.0,
    max_hold_days: int = 15,
) -> dict[str, Any]:
    _sync_from_broker(sym_state, holdings, symbol)

    ohlcv = fetch_daily_ohlcv(symbol, start=history_start)
    latest_date = ohlcv.index[-1].date().isoformat()
    if sym_state.in_position and latest_date != sym_state.last_processed_bar:
        if sym_state.last_processed_bar is not None:
            sym_state.bars_held += 1
        sym_state.last_processed_bar = latest_date

    action = live_action_from_history(
        ohlcv,
        in_position=sym_state.in_position,
        entry_close=sym_state.entry_close,
        bars_held=sym_state.bars_held,
        bb_period=bb_period,
        bb_std=bb_std,
        rsi_entry=rsi_entry,
        take_profit_pct=take_profit_pct,
        stop_loss_pct=stop_loss_pct,
        max_hold_days=max_hold_days,
    )

    result: dict[str, Any] = {
        "symbol": symbol,
        "action": action,
        "latest_bar": latest_date,
        "in_position": sym_state.in_position,
        "qty": sym_state.qty,
        "bars_held": sym_state.bars_held,
        "order": None,
    }

    if action == "buy" and not sym_state.in_position:
        ltp = get_ltp(api, symbol)
        kelly_cfg = load_kelly_config()
        frac = kelly_fraction_from_trade_returns(state.trade_returns_pct, config=kelly_cfg)
        qty, spend = position_size_inr(slice_capital, ltp, frac)
        if qty <= 0 and ltp > 0 and slice_capital >= ltp:
            logger.info(
                "%s: Kelly qty=0 — buying 1 share (ltp=%.2f, slice=Rs%.0f)",
                symbol,
                ltp,
                slice_capital,
            )
            qty, spend = 1, ltp
        result.update({"ltp": ltp, "kelly_fraction": frac, "qty": qty, "spend_inr": spend})
        if qty > 0:
            order = place_cnc_order(api, symbol, "BUY", qty, dry_run=dry_run)
            result["order"] = order
            if not dry_run and order and not order.get("skipped"):
                sym_state.in_position = True
                sym_state.qty = qty
                sym_state.entry_price = ltp
                sym_state.entry_close = float(ohlcv["close"].iloc[-1])
                sym_state.bars_held = 0
                sym_state.entry_date = latest_date
                sym_state.last_processed_bar = latest_date

    elif action == "sell" and sym_state.in_position:
        qty = sym_state.qty or _holding_qty(holdings, symbol)
        ltp = get_ltp(api, symbol)
        result.update({"ltp": ltp, "qty": qty})
        if qty > 0:
            order = place_cnc_order(api, symbol, "SELL", qty, dry_run=dry_run)
            result["order"] = order
            if not dry_run and order and not order.get("skipped"):
                _record_exit(state, sym_state, ltp)

    return result


def _symbols_from_holdings(holdings: list[dict[str, Any]]) -> set[str]:
    out: set[str] = set()
    for row in holdings:
        ts = str(row.get("tradingsymbol", "")).upper()
        if not ts or not ts.endswith("-EQ"):
            continue
        sym = ts.replace("-EQ", "")
        qty = int(float(row.get("quantity", 0) or 0))
        if qty > 0:
            out.add(sym)
    return out


def _signal_only(
    symbol: str,
    sym_state: SymbolState,
    *,
    history_start: str,
    bb_period: int = 20,
    bb_std: float = 2.0,
    rsi_entry: float = 35.0,
    take_profit_pct: float = 6.0,
    stop_loss_pct: float = 5.0,
    max_hold_days: int = 15,
) -> str:
    ohlcv = fetch_daily_ohlcv(symbol, start=history_start)
    latest_date = ohlcv.index[-1].date().isoformat()
    if sym_state.in_position and latest_date != sym_state.last_processed_bar:
        if sym_state.last_processed_bar is not None:
            sym_state.bars_held += 1
        sym_state.last_processed_bar = latest_date
    return live_action_from_history(
        ohlcv,
        in_position=sym_state.in_position,
        entry_close=sym_state.entry_close,
        bars_held=sym_state.bars_held,
        bb_period=bb_period,
        bb_std=bb_std,
        rsi_entry=rsi_entry,
        take_profit_pct=take_profit_pct,
        stop_loss_pct=stop_loss_pct,
        max_hold_days=max_hold_days,
    )


def run_dynamic_slot_cycle(
    *,
    portfolio_capital: float = 20_000.0,
    max_slots: int = 4,
    dry_run: bool = True,
    history_start: str = "2020-01-01",
    watchlist: list[str] | None = None,
) -> dict[str, Any]:
    """
    Up to max_slots positions (Rs capital/max_slots each).
    Exits: any held stock. Entries: scan backtest-ranked watchlist for BUY signals.
    """
    from algo_trade.universe.watchlist import watchlist_symbols

    watchlist = watchlist or watchlist_symbols()
    if not watchlist:
        raise ValueError("Watchlist is empty — run scripts/build_watchlist.py first")

    api = get_authenticated_client()
    cash = get_cash_balance(api)
    holdings = get_holdings(api)
    state = load_state()
    state.portfolio_capital = portfolio_capital
    slice_capital = portfolio_capital / max_slots

    held = _symbols_from_holdings(holdings)
    for sym in held:
        st = state.get_symbol(sym)
        st.in_position = True
        st.qty = _holding_qty(holdings, sym) or st.qty

    logger.info(
        "Dynamic cycle | watchlist=%d | held=%s | slots=%d | slice=Rs%.0f | cash=Rs%.2f | dry_run=%s",
        len(watchlist),
        ",".join(sorted(held)) or "none",
        max_slots,
        slice_capital,
        cash,
        dry_run,
    )

    results: list[dict[str, Any]] = []

    # 1) Manage exits for everything we hold
    for sym in sorted(held):
        sym_state = state.get_symbol(sym)
        try:
            r = run_symbol_cycle(
                api,
                sym,
                slice_capital=slice_capital,
                state=state,
                sym_state=sym_state,
                holdings=holdings,
                dry_run=dry_run,
                history_start=history_start,
            )
            results.append(r)
            if r.get("action") == "sell" and r.get("order") and not dry_run:
                held.discard(sym)
            logger.info("%s (held) -> %s", sym, r["action"])
        except Exception as exc:
            logger.exception("Exit check failed %s: %s", sym, exc)
            results.append({"symbol": sym, "error": str(exc)})

    empty_slots = max(0, max_slots - len(held))
    buys_placed = 0

    # 2) Fill empty slots from watchlist (best backtest rank first)
    if empty_slots > 0:
        for sym in watchlist:
            if sym in held:
                continue
            sym_state = state.get_symbol(sym)
            if sym_state.in_position:
                continue
            try:
                action = _signal_only(sym, sym_state, history_start=history_start)
                if action != "buy":
                    continue
                r = run_symbol_cycle(
                    api,
                    sym,
                    slice_capital=slice_capital,
                    state=state,
                    sym_state=sym_state,
                    holdings=holdings,
                    dry_run=dry_run,
                    history_start=history_start,
                )
                r["watchlist_rank"] = watchlist.index(sym) + 1
                results.append(r)
                logger.info("%s (watchlist #%d) -> BUY qty=%s", sym, r["watchlist_rank"], r.get("qty"))
                if r.get("action") == "buy" and r.get("qty", 0) > 0:
                    buys_placed += 1
                    held.add(sym)
                    empty_slots -= 1
                    if empty_slots <= 0:
                        break
            except Exception as exc:
                logger.warning("Watchlist skip %s: %s", sym, exc)

    save_state(state)
    try:
        from algo_trade.live.dashboard_data import save_public_snapshot

        save_public_snapshot()
    except Exception:
        logger.debug("Dashboard snapshot skipped", exc_info=True)
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "mode": "dynamic",
        "dry_run": dry_run,
        "live_orders_enabled": live_trading_allowed(),
        "available_cash": cash,
        "portfolio_capital": portfolio_capital,
        "max_slots": max_slots,
        "slice_capital": slice_capital,
        "held_symbols": sorted(held),
        "watchlist_size": len(watchlist),
        "results": results,
    }


def run_portfolio_cycle(
    symbols: list[str] | None = None,
    *,
    portfolio_capital: float = 20_000.0,
    dry_run: bool = True,
    history_start: str = "2020-01-01",
) -> dict[str, Any]:
    symbols = list(symbols or DEFAULT_SYMBOLS)
    symbols = [s.strip().upper().replace(".NS", "") for s in symbols if s.strip()]
    if not symbols:
        raise ValueError("No symbols provided")

    api = get_authenticated_client()
    cash = get_cash_balance(api)
    holdings = get_holdings(api)
    state = load_state()
    state.portfolio_capital = portfolio_capital
    slice_capital = portfolio_capital / len(symbols)

    logger.info(
        "Live cycle | symbols=%s | capital=Rs%.0f | slice=Rs%.0f | cash=Rs%.2f | dry_run=%s | live_ok=%s",
        ",".join(symbols),
        portfolio_capital,
        slice_capital,
        cash,
        dry_run,
        live_trading_allowed(),
    )

    results = []
    for sym in symbols:
        sym_state = state.get_symbol(sym)
        try:
            r = run_symbol_cycle(
                api,
                sym,
                slice_capital=slice_capital,
                state=state,
                sym_state=sym_state,
                holdings=holdings,
                dry_run=dry_run,
                history_start=history_start,
            )
            results.append(r)
            logger.info("%s -> %s (pos=%s qty=%s)", sym, r["action"], r["in_position"], r["qty"])
        except Exception as exc:
            logger.exception("Failed %s: %s", sym, exc)
            results.append({"symbol": sym, "error": str(exc)})

    save_state(state)
    try:
        from algo_trade.live.dashboard_data import save_public_snapshot

        save_public_snapshot()
    except Exception:
        logger.debug("Dashboard snapshot skipped", exc_info=True)
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "dry_run": dry_run,
        "live_orders_enabled": live_trading_allowed(),
        "available_cash": cash,
        "portfolio_capital": portfolio_capital,
        "slice_capital": slice_capital,
        "symbols": symbols,
        "results": results,
    }
