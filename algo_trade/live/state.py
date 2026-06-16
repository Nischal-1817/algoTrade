"""Persist algo-only position (never touches other holdings)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List

from algo_trade.config import DATA_DIR


def _state_path() -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return DATA_DIR / "algo_state.json"


@dataclass
class AlgoState:
    symbol: str
    trading_symbol: str = ""
    token: str = ""
    in_position: bool = False
    qty: int = 0
    entry_close: float | None = None
    entry_time: str | None = None
    bars_held: int = 0
    max_capital: float = 10_000.0
    kelly_fraction: float = 0.05
    bankroll_inr: float = 0.0
    trades: List[dict[str, Any]] = field(default_factory=list)
    last_action: str = "hold"
    last_run_utc: str = ""
    last_signal_note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> AlgoState:
        return cls(
            symbol=d.get("symbol", ""),
            trading_symbol=d.get("trading_symbol", ""),
            token=d.get("token", ""),
            in_position=bool(d.get("in_position", False)),
            qty=int(d.get("qty", 0)),
            entry_close=d.get("entry_close"),
            entry_time=d.get("entry_time"),
            bars_held=int(d.get("bars_held", 0)),
            max_capital=float(d.get("max_capital", 10_000.0)),
            kelly_fraction=float(d.get("kelly_fraction", 0.05)),
            bankroll_inr=float(d.get("bankroll_inr", 0.0)),
            trades=list(d.get("trades", [])),
            last_action=d.get("last_action", "hold"),
            last_run_utc=d.get("last_run_utc", ""),
            last_signal_note=d.get("last_signal_note", ""),
        )


def load_state() -> AlgoState | None:
    path = _state_path()
    if not path.exists():
        return None
    return AlgoState.from_dict(json.loads(path.read_text(encoding="utf-8")))


def save_state(state: AlgoState) -> Path:
    state.last_run_utc = datetime.now(timezone.utc).isoformat()
    path = _state_path()
    path.write_text(json.dumps(state.to_dict(), indent=2, default=str), encoding="utf-8")
    return path


def init_state(
    symbol: str, trading_symbol: str, token: str, max_capital: float
) -> AlgoState:
    return AlgoState(
        symbol=symbol.upper().replace(".NS", ""),
        trading_symbol=trading_symbol,
        token=token,
        max_capital=max_capital,
    )
