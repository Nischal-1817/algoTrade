"""
Call the AWS gateway from your laptop.

  set GATEWAY_URL=http://YOUR_ELASTIC_IP:8080
  set GATEWAY_SECRET=your_secret
  python aws_gateway/scripts/call_gateway.py status
  python aws_gateway/scripts/call_gateway.py run-cycle
"""

from __future__ import annotations

import argparse
import json
import os
import sys

import requests

DEFAULT_URL = os.getenv("GATEWAY_URL", "http://127.0.0.1:8080").rstrip("/")
SECRET = os.getenv("GATEWAY_SECRET", "")


def _headers() -> dict:
    h = {"Content-Type": "application/json"}
    if SECRET:
        h["Authorization"] = f"Bearer {SECRET}"
    return h


def main() -> None:
    parser = argparse.ArgumentParser(description="Call algo trade AWS gateway")
    parser.add_argument(
        "command",
        choices=("health", "public-ip", "status", "run-cycle", "state"),
    )
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--secret", default=SECRET)
    args = parser.parse_args()

    base = args.url.rstrip("/")
    secret = args.secret or SECRET
    headers = {"Content-Type": "application/json"}
    if secret:
        headers["Authorization"] = f"Bearer {secret}"

    if args.command == "health":
        r = requests.get(f"{base}/health", timeout=30)
    elif args.command == "public-ip":
        r = requests.get(f"{base}/api/public-ip", timeout=30)
    elif args.command == "status":
        r = requests.get(f"{base}/api/status", headers=headers, timeout=60)
    elif args.command == "state":
        r = requests.get(f"{base}/api/state", headers=headers, timeout=30)
    else:
        r = requests.post(f"{base}/api/run-cycle", headers=headers, timeout=180)

    print(f"HTTP {r.status_code}")
    try:
        print(json.dumps(r.json(), indent=2, default=str))
    except Exception:
        print(r.text)
    if r.status_code >= 400:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
