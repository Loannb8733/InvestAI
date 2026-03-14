"""Ping the Render health endpoint to prevent cold-start sleep.

Usage (manual):
    python scripts/keep_warm.py

Intended to run via GitHub Actions cron every 14 minutes.
"""

import sys
import urllib.request

URL = "https://investai-api.onrender.com/health"
TIMEOUT = 15  # seconds


def main() -> None:
    try:
        req = urllib.request.Request(URL, method="GET")
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            print(f"OK {resp.status} — {resp.read().decode()}")
    except Exception as exc:
        print(f"WARN: ping failed — {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
