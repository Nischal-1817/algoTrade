"""
Run one live mean-reversion cycle (Groww orders + Yahoo daily data).

Default: DRY RUN. For real orders set:
  ENABLE_LIVE_TRADING=1
  LIVE_TRADING_CONFIRM=I_UNDERSTAND_RISK
  ALLOW_GROWW_ORDERS=1

Schedule ~ 9:20 IST on trading days (Task Scheduler).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from algo_trade.config import ensure_dirs
from algo_trade.live import run_live_cycle
from algo_trade.logging_config import setup_logging


def main() -> None:
    log = setup_logging()
    ensure_dirs()
    try:
        summary = run_live_cycle()
    except Exception as e:
        log.exception("Live cycle failed: %s", e)
        raise SystemExit(1) from e
    print(json.dumps(summary, indent=2, default=str))
    log.info("Done. action=%s live=%s", summary.get("action"), summary.get("live_orders_enabled"))


if __name__ == "__main__":
    main()
