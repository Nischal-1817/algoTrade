"""Print latest mean-reversion entry diagnostics for symbols."""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from algo_trade.data import fetch_daily_ohlcv
from algo_trade.strategy.mean_reversion import add_mean_reversion_signals, live_action_from_history

from algo_trade.universe import NIFTY50, nifty100


def diagnose(symbol: str, start: str) -> dict:
    df = fetch_daily_ohlcv(symbol, start=start)
    sig = add_mean_reversion_signals(df)
    row = sig.iloc[-1]
    action = live_action_from_history(df, in_position=False, entry_close=None, bars_held=0)
    c = float(row["close"])
    bb_l = float(row["bb_lower"])
    rsi = float(row["rsi"])
    trend = float(row["sma_trend"])
    below_bb = c < bb_l
    rsi_ok = rsi < 35
    uptrend = c > trend
    return {
        "symbol": symbol,
        "action": action,
        "close": c,
        "bb_lower": bb_l,
        "rsi": rsi,
        "sma200": trend,
        "below_bb": below_bb,
        "rsi_ok": rsi_ok,
        "uptrend": uptrend,
        "buy_signal": below_bb and rsi_ok and uptrend,
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--symbols", default="ICICIBANK,ITC,RELIANCE,TCS")
    p.add_argument("--scan", choices=("none", "nifty50", "nifty100"), default="none")
    p.add_argument("--start", default="2020-01-01")
    args = p.parse_args()

    if args.scan == "nifty100":
        symbols = list(nifty100())
    elif args.scan == "nifty50":
        symbols = list(NIFTY50)
    else:
        symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]

    rows = []
    for sym in symbols:
        try:
            rows.append(diagnose(sym, args.start))
        except Exception as exc:
            rows.append({"symbol": sym, "action": "error", "error": str(exc)})

    print(f"{'Symbol':<12} {'Act':<5} {'Close':>8} {'BB_lo':>8} {'RSI':>6} {'<BB':>4} {'RSI':>4} {'200d':>4}")
    print("-" * 62)
    buys = []
    for r in rows:
        if r.get("action") == "error":
            print(f"{r['symbol']:<12} ERR   {r.get('error','')[:40]}")
            continue
        print(
            f"{r['symbol']:<12} {r['action']:<5} {r['close']:>8.2f} {r['bb_lower']:>8.2f} "
            f"{r['rsi']:>6.1f} {str(r['below_bb']):>4} {str(r['rsi_ok']):>4} {str(r['uptrend']):>4}"
        )
        if r.get("buy_signal"):
            buys.append(r["symbol"])

    print()
    if buys:
        print(f"BUY signals today: {', '.join(buys)}")
    else:
        print("No BUY signals (need: close < lower BB AND RSI < 35 AND close > SMA200)")


if __name__ == "__main__":
    main()
