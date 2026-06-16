"""Runtime settings. Live trading is off unless explicitly enabled."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = PROJECT_ROOT / "logs"
REPORT_DIR = PROJECT_ROOT / "reports"
DATA_DIR = PROJECT_ROOT / "data"


@dataclass
class Settings:
    """Conservative defaults: simulation only."""

    exchange: str = "NSE"
    default_symbol_yahoo: str = "RELIANCE.NS"
    initial_capital: float = 100_000.0
    commission_pct: float = 0.03
    slippage_pct: float = 0.05
    fast_sma: int = 20
    slow_sma: int = 50
    # Groww: never place real orders unless both are set.
    enable_live_trading: bool = field(
        default_factory=lambda: os.getenv("ENABLE_LIVE_TRADING", "").lower() in ("1", "true", "yes")
    )
    live_trading_confirm: str = field(
        default_factory=lambda: os.getenv("LIVE_TRADING_CONFIRM", "")
    )


def get_settings() -> Settings:
    return Settings()


def ensure_dirs() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
