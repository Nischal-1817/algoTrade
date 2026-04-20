"""Streamlit dashboard: run backtests and inspect results."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from algo_trade.backtest import compute_metrics, run_long_only_next_open, write_html_report
from algo_trade.config import get_settings, ensure_dirs
from algo_trade.data import fetch_daily_ohlcv
from algo_trade.logging_config import setup_logging
from algo_trade.strategy import add_signals

st.set_page_config(page_title="NSE backtest lab", layout="wide")
log = setup_logging()


def main() -> None:
    ensure_dirs()
    settings = get_settings()
    st.title("NSE backtest lab (beginner / low complexity)")
    st.caption(
        "Uses Yahoo Finance (.NS) for history. Groww is not required for backtests. "
        "This is for learning—not financial advice."
    )

    col1, col2, col3 = st.columns(3)
    with col1:
        symbol = st.text_input("Symbol", value="RELIANCE", help="NSE name; .NS added automatically")
    with col2:
        start = st.text_input("Start date", value="2018-01-01")
    with col3:
        end = st.text_input("End date (optional)", value="")

    c4, c5, c6, c7 = st.columns(4)
    with c4:
        fast = st.number_input("Fast SMA", min_value=2, max_value=200, value=settings.fast_sma)
    with c5:
        slow = st.number_input("Slow SMA", min_value=3, max_value=400, value=settings.slow_sma)
    with c6:
        capital = st.number_input("Initial capital (INR)", min_value=10_000.0, value=settings.initial_capital, step=10_000.0)
    with c7:
        slip = st.number_input("Slippage % (each side)", min_value=0.0, value=settings.slippage_pct, step=0.01)
        comm = st.number_input("Commission % (each side)", min_value=0.0, value=settings.commission_pct, step=0.01)

    run = st.button("Run backtest", type="primary")
    if not run:
        st.info("Set parameters and click **Run backtest**.")
        return

    if fast >= slow:
        st.error("Fast SMA must be smaller than slow SMA.")
        return

    try:
        end_arg = end.strip() or None
        ohlcv = fetch_daily_ohlcv(symbol, start=start, end=end_arg)
        sig = add_signals(ohlcv, fast=int(fast), slow=int(slow))
        result = run_long_only_next_open(
            sig,
            initial_capital=float(capital),
            commission_pct=float(comm),
            slippage_pct=float(slip),
        )
        metrics = compute_metrics(
            result["equity_curve"],
            result["trades"],
            initial_capital=float(capital),
        )
    except Exception as e:
        log.exception("Backtest failed")
        st.exception(e)
        return

    mcol1, mcol2, mcol3, mcol4 = st.columns(4)
    mcol1.metric("Final equity (INR)", f"{metrics['final_equity']:,.0f}")
    mcol2.metric("Total return %", f"{metrics['total_return_pct']:.2f}")
    mcol3.metric("Max drawdown %", f"{metrics['max_drawdown_pct']:.2f}")
    mcol4.metric("Trades (round-trip)", f"{metrics['n_trades']}")

    eq = result["equity_curve"]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=eq.index, y=eq.values, name="Equity"))
    fig.update_layout(title="Equity curve", height=400, margin=dict(l=8, r=8, t=40, b=8))
    st.plotly_chart(fig, use_container_width=True)

    pxfig = go.Figure()
    pxfig.add_trace(go.Scatter(x=sig.index, y=sig["close"], name="Close"))
    pxfig.add_trace(go.Scatter(x=sig.index, y=sig["sma_fast"], name=f"SMA {fast}"))
    pxfig.add_trace(go.Scatter(x=sig.index, y=sig["sma_slow"], name=f"SMA {slow}"))
    pxfig.update_layout(title="Price & SMAs", height=400, margin=dict(l=8, r=8, t=40, b=8))
    st.plotly_chart(pxfig, use_container_width=True)

    if result["trades"]:
        tdf = pd.DataFrame(result["trades"])
        st.dataframe(tdf, use_container_width=True, hide_index=True)
    else:
        st.warning("No completed round-trip trades in this window (try longer history or different SMAs).")

    meta = {
        "symbol": symbol,
        "start": str(ohlcv.index[0].date()),
        "end": str(ohlcv.index[-1].date()),
        "fast_sma": int(fast),
        "slow_sma": int(slow),
        "initial_capital": float(capital),
        "commission_pct": float(comm),
        "slippage_pct": float(slip),
    }
    if st.button("Save HTML report to reports/"):
        path = write_html_report(
            symbol=symbol,
            ohlcv=sig,
            equity=eq,
            metrics=metrics,
            trades=result["trades"],
            meta=meta,
        )
        st.success(f"Saved: {path.relative_to(ROOT)}")
        log.info("Dashboard saved report %s", path)


if __name__ == "__main__":
    main()
