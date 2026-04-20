"""Optional: verify Groww credentials resolve to an access token (no orders)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from algo_trade.broker.groww_broker import get_groww_client
from algo_trade.logging_config import setup_logging


def main() -> None:
    log = setup_logging()
    try:
        c = get_groww_client()
        log.info("Groww client OK: %s", type(c).__name__)
        log.info("No orders were placed. Use backtests before any live trading.")
    except Exception as e:
        log.exception("Groww connection failed: %s", e)
        raise SystemExit(1) from e


if __name__ == "__main__":
    main()
