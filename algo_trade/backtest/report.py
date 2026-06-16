"""Write a self-contained HTML backtest report (Plotly charts)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from algo_trade.config import REPORT_DIR, ensure_dirs


def _fig_equity_drawdown(equity: pd.Series) -> go.Figure:
    roll_max = equity.cummax()
    dd = (equity / roll_max - 1.0) * 100.0
    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.06,
        row_heights=[0.72, 0.28],
    )
    fig.add_trace(
        go.Scatter(x=equity.index, y=equity.values, name="Equity", line=dict(color="#2563eb")),
        row=1,
        col=1,
    )
    fig.add_trace(
        go.Scatter(
            x=dd.index,
            y=dd.values,
            name="Drawdown %",
            fill="tozeroy",
            line=dict(color="#dc2626"),
            fillcolor="rgba(220,38,38,0.25)",
        ),
        row=2,
        col=1,
    )
    fig.update_layout(
        height=640,
        margin=dict(l=48, r=24, t=40, b=48),
        title="Equity and drawdown",
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )
    fig.update_yaxes(title_text="INR", row=1, col=1)
    fig.update_yaxes(title_text="%", row=2, col=1)
    return fig


def _fig_price_signals(ohlcv: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=ohlcv.index,
            y=ohlcv["close"],
            name="Close",
            line=dict(color="#0f172a"),
        )
    )
    if "sma_fast" in ohlcv.columns:
        fig.add_trace(
            go.Scatter(x=ohlcv.index, y=ohlcv["sma_fast"], name="Fast SMA", line=dict(color="#16a34a"))
        )
    if "sma_slow" in ohlcv.columns:
        fig.add_trace(
            go.Scatter(x=ohlcv.index, y=ohlcv["sma_slow"], name="Slow SMA", line=dict(color="#ca8a04"))
        )
    if "bb_lower" in ohlcv.columns:
        fig.add_trace(
            go.Scatter(
                x=ohlcv.index,
                y=ohlcv["bb_lower"],
                name="BB lower",
                line=dict(color="#dc2626", dash="dot"),
            )
        )
    if "bb_mid" in ohlcv.columns:
        fig.add_trace(
            go.Scatter(
                x=ohlcv.index,
                y=ohlcv["bb_mid"],
                name="BB mid",
                line=dict(color="#64748b", dash="dash"),
            )
        )
    if "bb_upper" in ohlcv.columns:
        fig.add_trace(
            go.Scatter(
                x=ohlcv.index,
                y=ohlcv["bb_upper"],
                name="BB upper",
                line=dict(color="#16a34a", dash="dot"),
            )
        )
    if "sma_trend" in ohlcv.columns:
        fig.add_trace(
            go.Scatter(
                x=ohlcv.index,
                y=ohlcv["sma_trend"],
                name="Trend SMA",
                line=dict(color="#7c3aed"),
            )
        )
    title = "Price and bands" if "bb_mid" in ohlcv.columns else "Price and moving averages"
    fig.update_layout(
        height=420,
        margin=dict(l=48, r=24, t=40, b=48),
        title=title,
    )
    fig.update_yaxes(title_text="Price")
    return fig


def write_html_report(
    *,
    symbol: str,
    ohlcv: pd.DataFrame,
    equity: pd.Series,
    metrics: Dict[str, Any],
    trades: List[Dict[str, Any]],
    meta: Dict[str, Any],
    path: Path | None = None,
) -> Path:
    ensure_dirs()
    safe_sym = symbol.replace(".", "_").replace("/", "_")
    out = path or (
        REPORT_DIR / f"backtest_{safe_sym}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.html"
    )

    fig1 = _fig_equity_drawdown(equity)
    fig2 = _fig_price_signals(ohlcv)
    fig1_json = fig1.to_json()
    fig2_json = fig2.to_json()

    trades_rows = ""
    for t in trades[-200:]:
        trades_rows += (
            "<tr>"
            f"<td>{t['entry_time']}</td><td>{t['exit_time']}</td>"
            f"<td>{t['entry_price']:.2f}</td><td>{t['exit_price']:.2f}</td>"
            f"<td>{t['pnl']:.2f}</td><td>{t['return_pct']:.2f}%</td>"
            "</tr>"
        )

    metrics_tbl = "".join(
        f"<tr><td>{k}</td><td style='text-align:right'>{v}</td></tr>" for k, v in metrics.items()
    )

    meta_json = json.dumps(meta, indent=2, default=str)
    gen_ts = datetime.now(timezone.utc).isoformat()

    html_parts = [
        "<!DOCTYPE html>\n<html lang=\"en\"><head><meta charset=\"utf-8\"/>\n",
        f"<title>Backtest report — {symbol}</title>\n",
        '<script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>\n',
        "<style>\n",
        "body { font-family: system-ui, sans-serif; margin: 24px; color: #0f172a; }\n",
        "table { border-collapse: collapse; width: 100%; max-width: 960px; }\n",
        "th, td { border: 1px solid #e2e8f0; padding: 8px; text-align: left; }\n",
        "th { background: #f1f5f9; }\n",
        ".small { color: #64748b; font-size: 0.9rem; }\n",
        "pre { background: #f8fafc; padding: 12px; overflow: auto; max-width: 960px; }\n",
        "</style>\n</head><body>\n",
        "<h1>Backtest report</h1>\n",
        f"<p class=\"small\">Symbol: <strong>{symbol}</strong> · Generated UTC {gen_ts}</p>\n",
        "<h2>Summary</h2>\n",
        f"<table>{metrics_tbl}</table>\n",
        "<h2>Charts</h2>\n",
        "<div id=\"c1\"></div>\n",
        "<div id=\"c2\"></div>\n",
        "<h2>Trades (last 200)</h2>\n",
        "<table><thead><tr>\n",
        "<th>Entry</th><th>Exit</th><th>Entry px</th><th>Exit px</th><th>PnL</th><th>Return %</th>\n",
        "</tr></thead><tbody>",
        trades_rows,
        "</tbody></table>\n",
        "<h2>Run metadata</h2>\n",
        f"<pre>{meta_json}</pre>\n",
        "<script>\n",
        "var fig1 = ",
        fig1_json,
        ";\nvar fig2 = ",
        fig2_json,
        ";\nPlotly.newPlot('c1', fig1.data, fig1.layout, {responsive:true});\n",
        "Plotly.newPlot('c2', fig2.data, fig2.layout, {responsive:true});\n",
        "</script>\n</body></html>\n",
    ]
    out.write_text("".join(html_parts), encoding="utf-8")
    return out
