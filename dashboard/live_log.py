"""Public live-trading log dashboard (orders, PnL, holdings)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from algo_trade.config import DATA_DIR, ensure_dirs
from algo_trade.live.dashboard_data import PUBLIC_SNAPSHOT_PATH, build_dashboard_snapshot, save_public_snapshot

st.set_page_config(page_title="algoTrade Live Log", layout="wide", page_icon="📊")


def _check_password() -> bool:
    expected = os.getenv("DASHBOARD_PASSWORD", "").strip()
    if not expected:
        return True
    if "dashboard_auth" not in st.session_state:
        st.session_state.dashboard_auth = False
    if st.session_state.dashboard_auth:
        return True
    st.title("algoTrade — live log")
    pwd = st.text_input("Dashboard password", type="password")
    if st.button("Enter"):
        if pwd == expected:
            st.session_state.dashboard_auth = True
            st.rerun()
        else:
            st.error("Wrong password")
    return False


@st.cache_data(ttl=60)
def _load_snapshot() -> dict:
    if PUBLIC_SNAPSHOT_PATH.exists():
        try:
            return json.loads(PUBLIC_SNAPSHOT_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return build_dashboard_snapshot()


def main() -> None:
    ensure_dirs()
    if not _check_password():
        return

    st.title("algoTrade — live trading log")
    st.caption("Read-only view of orders, holdings, and P&L. Not financial advice.")

    col_r1, col_r2 = st.columns([3, 1])
    with col_r2:
        if st.button("Refresh now"):
            try:
                save_public_snapshot()
                _load_snapshot.clear()
                st.rerun()
            except Exception as exc:
                st.error(f"Refresh failed: {exc}")

    try:
        data = _load_snapshot()
    except Exception as exc:
        st.error(f"Could not load data: {exc}")
        return

    updated = data.get("updated_at", "unknown")
    st.markdown(f"**Last updated (UTC):** `{updated}`")

    if not data.get("broker_ok"):
        st.warning("Broker snapshot unavailable — showing saved logs only.")

    m1, m2, m3, m4, m5 = st.columns(5)
    pnl = data.get("pnl") or {}
    m1.metric("Cash (Angel)", f"₹{data.get('available_cash') or 0:,.0f}")
    m2.metric("Realized P&L", f"₹{pnl.get('realized_inr', 0):,.2f}")
    m3.metric("Unrealized P&L", f"₹{pnl.get('unrealized_inr', 0):,.2f}")
    m4.metric("Total P&L", f"₹{pnl.get('total_inr', 0):,.2f}")
    m5.metric("Closed trades", pnl.get("closed_trades", 0))

    st.subheader("Open holdings")
    holdings = data.get("holdings") or []
    if holdings:
        st.dataframe(pd.DataFrame(holdings), use_container_width=True, hide_index=True)
    else:
        st.info("No open positions.")

    st.subheader("Orders log")
    orders = data.get("orders") or []
    if orders:
        df = pd.DataFrame(orders)
        cols = [c for c in ["time", "tag", "symbol", "action", "qty", "ltp", "order_id", "watchlist_rank"] if c in df.columns]
        st.dataframe(df[cols], use_container_width=True, hide_index=True)
    else:
        st.info("No orders recorded yet (strategy may be on HOLD, or no signals fired).")

    st.subheader("Recent trading cycles")
    cycles = data.get("recent_cycles") or []
    for c in cycles[:8]:
        mode = "DRY-RUN" if c.get("dry_run") else "LIVE"
        held = ", ".join(c.get("held_symbols") or []) or "none"
        with st.expander(f"{c.get('timestamp', '')[:19]} — {mode} — held: {held}"):
            actions = c.get("actions") or []
            if actions:
                st.dataframe(pd.DataFrame(actions), hide_index=True)
            else:
                st.write("No actions this cycle.")

    st.subheader("Algo state (per symbol)")
    state = data.get("algo_state") or {}
    if state:
        rows = [{"symbol": k, **v} for k, v in state.items() if v.get("in_position") or v.get("trade_returns_pct")]
        if rows:
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        else:
            st.write("No active or historical symbol state yet.")

    st.subheader("Watchlist (top 10 by backtest)")
    top10 = data.get("watchlist_top10") or []
    st.write(", ".join(top10) if top10 else "—")
    if data.get("watchlist_generated_at"):
        st.caption(f"Watchlist built: {data['watchlist_generated_at']}")


if __name__ == "__main__":
    main()
