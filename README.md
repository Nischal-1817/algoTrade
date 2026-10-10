# algoTrade

An algorithmic trading framework for Indian equities (NSE): backtesting, portfolio simulation with risk-based position sizing, and live trading through the Angel One SmartAPI, with a Streamlit monitoring dashboard.

> **Disclaimer:** This is a personal learning/research project, not financial advice. Backtests do not guarantee future results. Trade live at your own risk.

## Features

- **Backtesting engine** on daily NSE data (Yahoo Finance), with metrics (CAGR, Sharpe, drawdown, etc.) and HTML/JSON reports.
- **Strategies**
  - Mean reversion: enter on a lower-Bollinger-band close with RSI oversold inside an uptrend; exit on take-profit, stop-loss or time stop.
  - SMA crossover baseline.
- **Portfolio backtests** across multiple symbols with a shared capital pool.
- **Kelly-criterion position sizing** (`algo_trade/risk/kelly.py`).
- **Live trading** via Angel One SmartAPI with persisted state, market-hours runner and dry-run support.
- **Dashboard** (Streamlit) for backtest results and live log/state.
- **Deployment helpers** for AWS EC2 (systemd units and a PowerShell deploy script).

## Project layout

```
algo_trade/
  backtest/    engine, portfolio simulation, metrics, reports
  broker/      Angel One SmartAPI client
  data/        NSE data loading (Yahoo Finance)
  live/        live runner, state, dashboard payload
  risk/        Kelly sizing
  strategy/    mean_reversion, sma_crossover
  universe/    Nifty universe and watchlist builders
dashboard/     Streamlit apps
scripts/       CLI entry points (backtest, live, validation, deploy)
deploy/ec2/    systemd services and remote setup
```

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Run a single-symbol backtest (no broker account needed):

```bash
python scripts/run_backtest.py --strategy mean_reversion --symbol SBIN --start 2018-01-01
```

Run a portfolio backtest:

```bash
python scripts/run_portfolio_backtest.py --capital 20000 --symbols ICICIBANK,ITC,RELIANCE,TCS --start 2018-01-01
```

Launch the dashboard:

```bash
streamlit run dashboard/app.py
```

## Live trading (optional)

Backtests need no credentials. For live trading:

1. Copy `credentials.example.py` to `credentials.py` (gitignored) **or** set environment variables:
   `ANGELONE_API_KEY`, `ANGELONE_CLIENT_ID`, `ANGELONE_PASSWORD`, `ANGELONE_TOTP_SECRET`.
2. Validate the setup: `python scripts/validate_angel_setup.py`
3. Check signals: `python scripts/check_signals.py`
4. Run: `python scripts/run_live_trading.py`

Never commit `credentials.py`, `.env` files, session JSON or `.pem` keys; all are listed in `.gitignore`.

See `USAGE.txt` for more detail, including EC2 deployment.

## Tech stack

Python, pandas, NumPy, yfinance, Plotly, Streamlit, smartapi-python, pyotp.

## License

No license has been chosen yet; all rights reserved by the author until one is added.
