"""Live Groww dashboard: balance, algo state, trades, run cycle."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from algo_trade.broker.groww_broker import get_cash_balance, get_groww_client, get_ltp, live_trading_allowed
from algo_trade.config import DATA_DIR, ensure_dirs
from algo_trade.live import load_state, run_live_cycle
from algo_trade.logging_config import setup_logging

st.set_page_config(page_title="Groww live algo", layout="wide")
log = setup_logging()


def main() -> None:
    ensure_dirs()
    st.title("Groww live — mean reversion")
    st.caption(
        "Groww for balance, LTP, and orders. Yahoo for daily strategy bars. "
        "Bot only trades `ALGO_SYMBOL`. Not financial advice."
    )

    if live_trading_allowed():
        st.error("LIVE ORDERS ENABLED — real money at risk.")
    else:
        st.info("Dry-run: orders logged but not sent unless live env vars are set.")

    state = load_state()
    cash = None
    ltp = None
    try:
        client = get_groww_client()
        cash = get_cash_balance(client)
        sym = state.symbol if state else "SBIN"
        ltp = get_ltp(client, sym)
    except Exception as e:
        st.warning(f"Groww API: {e}")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("CNC cash (Groww)", f"₹{cash:,.0f}" if cash is not None else "—")
    c2.metric(
        "Algo position",
        f"{state.qty} {state.symbol}" if state and state.in_position else "Flat",
    )
    c3.metric("Max capital cap", f"₹{state.max_capital:,.0f}" if state else "₹10,000")
    c4.metric(
        "Kelly size",
        f"{state.kelly_fraction:.1%}" if state else "5% default",
    )
    if ltp is not None:
        st.metric("LTP", f"₹{ltp:,.2f}")

    if st.button("Run live cycle now", type="primary"):
        with st.spinner("Running…"):
            try:
                summary = run_live_cycle()
                st.success(f"Action: {summary.get('action')}")
                st.json(summary)
            except Exception as e:
                log.exception("Live run failed")
                st.exception(e)

    if state and state.trades:
        st.subheader("Algo trade log")
        st.dataframe(pd.DataFrame(state.trades), use_container_width=True, hide_index=True)

    path = DATA_DIR / "algo_state.json"
    if path.exists():
        st.subheader("State file")
        st.code(path.read_text(encoding="utf-8"), language="json")


if __name__ == "__main__":
    main()
