"""Persist per-symbol live algo state (positions, Kelly history)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from algo_trade.config import DATA_DIR

STATE_PATH = DATA_DIR / "algo_state.json"


@dataclass
class SymbolState:
    in_position: bool = False
    entry_close: float | None = None
    entry_price: float | None = None
    qty: int = 0
    bars_held: int = 0
    entry_date: str | None = None
    last_processed_bar: str | None = None
    trade_returns_pct: list[float] = field(default_factory=list)


@dataclass
class AlgoState:
    symbols: dict[str, SymbolState] = field(default_factory=dict)
    last_run: str | None = None
    portfolio_capital: float | None = None
    # Pooled across all symbols so Kelly sizing reflects the strategy's edge
    # instead of stalling at min_fraction until one symbol alone closes 5 trades.
    trade_returns_pct: list[float] = field(default_factory=list)

    def get_symbol(self, symbol: str) -> SymbolState:
        sym = symbol.strip().upper().replace(".NS", "")
        if sym not in self.symbols:
            self.symbols[sym] = SymbolState()
        return self.symbols[sym]


def load_state() -> AlgoState:
    if not STATE_PATH.exists():
        return AlgoState()
    try:
        raw = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return AlgoState()
    symbols: dict[str, SymbolState] = {}
    for sym, data in (raw.get("symbols") or {}).items():
        symbols[sym] = SymbolState(**data)
    return AlgoState(
        symbols=symbols,
        last_run=raw.get("last_run"),
        portfolio_capital=raw.get("portfolio_capital"),
        trade_returns_pct=list(raw.get("trade_returns_pct") or []),
    )


def save_state(state: AlgoState) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "last_run": datetime.now(timezone.utc).isoformat(),
        "portfolio_capital": state.portfolio_capital,
        "trade_returns_pct": state.trade_returns_pct,
        "symbols": {k: asdict(v) for k, v in state.symbols.items()},
    }
    STATE_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    state.last_run = payload["last_run"]
