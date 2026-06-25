"""Write data/dashboard_public.json for the live log dashboard."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from algo_trade.config import ensure_dirs
from algo_trade.live.dashboard_data import save_public_snapshot
from algo_trade.logging_config import setup_logging


def main() -> None:
    setup_logging()
    ensure_dirs()
    path = save_public_snapshot()
    print(f"Wrote {path}")


if __name__ == "__main__":
    main()
