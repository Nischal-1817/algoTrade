"""Dispatch live cycle to configured broker (default: Groww)."""

from __future__ import annotations

import os
from typing import Any


def run_live_cycle(**kwargs) -> dict[str, Any]:
    broker = os.getenv("ALGO_BROKER", "groww").strip().lower()
    if broker == "shoonya":
        from algo_trade.live.shoonya_runner import run_live_cycle as _run

        return _run(**kwargs)
    from algo_trade.live.groww_runner import run_live_cycle as _run

    return _run()
