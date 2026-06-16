"""
Show your public IP for broker API whitelisting (Groww, etc.).

Usage:
  python scripts/show_public_ip.py
  python scripts/show_public_ip.py --watch          # alert when IP changes
  python scripts/show_public_ip.py --watch --interval 300

Note: Home broadband usually has a *dynamic* IP that changes sometimes.
      There is no reliable way to get a free *static* IP at home without:
        - ISP static-IP plan (often paid), or
        - A cloud VPS (small monthly cost, fixed IP).

      For whitelisting: run this script, give Groww the IP shown, and re-run
      after router reboot / if API stops working.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

IP_HISTORY = ROOT / "data" / "public_ip_history.json"

PROVIDERS = (
    ("https://api.ipify.org?format=json", "ip"),
    ("https://ifconfig.me/ip", None),
    ("https://icanhazip.com", None),
)


def fetch_public_ip() -> tuple[str, str]:
    """Return (ip, provider_name). Raises if all providers fail."""
    last_err: Exception | None = None
    for url, key in PROVIDERS:
        try:
            r = requests.get(url, timeout=12)
            r.raise_for_status()
            text = r.text.strip()
            if key:
                data = r.json()
                ip = str(data[key]).strip()
            else:
                ip = text.split()[0] if text else ""
            if ip and _looks_like_ip(ip):
                return ip, url.split("/")[2]
        except Exception as e:
            last_err = e
    raise RuntimeError(f"Could not detect public IP: {last_err}")


def _looks_like_ip(s: str) -> bool:
    parts = s.split(".")
    if len(parts) != 4:
        return False
    try:
        return all(0 <= int(p) <= 255 for p in parts)
    except ValueError:
        return False


def _load_last() -> dict | None:
    if not IP_HISTORY.exists():
        return None
    try:
        return json.loads(IP_HISTORY.read_text(encoding="utf-8"))
    except Exception:
        return None


def _save_record(ip: str, provider: str) -> None:
    IP_HISTORY.parent.mkdir(parents=True, exist_ok=True)
    prev = _load_last()
    record = {
        "ip": ip,
        "provider": provider,
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "previous_ip": prev.get("ip") if prev else None,
    }
    IP_HISTORY.write_text(json.dumps(record, indent=2), encoding="utf-8")
    return record


def main() -> None:
    parser = argparse.ArgumentParser(description="Show public IP for API whitelisting")
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Loop and print when IP changes (Ctrl+C to stop)",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=600,
        help="Seconds between checks in watch mode (default 600)",
    )
    args = parser.parse_args()

    def once() -> str:
        ip, provider = fetch_public_ip()
        prev = _load_last()
        record = _save_record(ip, provider)
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

        print("=" * 50)
        print("PUBLIC IP (give this to Groww whitelist)")
        print("=" * 50)
        print(f"  {ip}")
        print(f"  Source: {provider}")
        print(f"  Checked: {ts}")
        if prev and prev.get("ip") and prev["ip"] != ip:
            print(f"  WARNING: IP changed from {prev['ip']}")
            print("  Update whitelist on Groww if API auth fails.")
        elif prev and prev.get("ip") == ip:
            print("  (unchanged since last check)")
        print()
        print("Saved to:", IP_HISTORY.relative_to(ROOT))
        print()
        print("Free static IP at home: usually NOT available.")
        print("If this IP changes, re-run and update Groww whitelist.")
        return ip

    if not args.watch:
        once()
        return

    print(f"Watching public IP every {args.interval}s (Ctrl+C to stop)\n")
    last_ip: str | None = None
    try:
        while True:
            ip, _ = fetch_public_ip()
            if last_ip is not None and ip != last_ip:
                print(f"\n*** IP CHANGED: {last_ip} -> {ip} ***")
                print("Update Groww whitelist with the new IP.\n")
            _save_record(ip, "watch")
            if ip != last_ip:
                once()
            last_ip = ip
            time.sleep(max(60, args.interval))
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
