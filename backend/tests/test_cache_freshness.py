"""Redis cache freshness test for price data.

Verifies that cached prices in Redis are not stale (> 5 minutes).
If stale data is found, flags the symbols and recommends a refresh.

Usage (inside Docker):
    docker compose exec backend python -m tests.test_cache_freshness

Exit code 1 if any price data is stale.
"""

import os
import sys
from datetime import datetime, timezone

import redis

REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")

# Maximum allowed age for cached price data
MAX_AGE_SECONDS = 300  # 5 minutes


def main():
    print("=" * 60)
    print("REDIS CACHE FRESHNESS CHECK")
    print(f"Max allowed age: {MAX_AGE_SECONDS}s ({MAX_AGE_SECONDS // 60} min)")
    print("=" * 60)

    r = redis.from_url(REDIS_URL, decode_responses=True)

    # Scan for all price:* keys
    price_keys = []
    cursor = 0
    while True:
        cursor, keys = r.scan(cursor, match="price:*", count=100)
        price_keys.extend(keys)
        if cursor == 0:
            break

    if not price_keys:
        print("\n  No price keys found in Redis cache.")
        print("  This may be normal if the system just started.")
        print("=" * 60)
        return

    print(f"\nFound {len(price_keys)} cached price entries.\n")

    now = datetime.now(timezone.utc)
    stale = []
    fresh = []
    no_timestamp = []

    for key in sorted(price_keys):
        # Skip historical price keys (they have long TTLs by design)
        if "historical" in key:
            continue

        data = r.hgetall(key)
        if not data:
            continue

        last_updated_str = data.get("last_updated")
        if not last_updated_str:
            no_timestamp.append(key)
            continue

        try:
            # Parse ISO timestamp (may or may not have timezone)
            last_updated = datetime.fromisoformat(last_updated_str)
            if last_updated.tzinfo is None:
                last_updated = last_updated.replace(tzinfo=timezone.utc)
            age = (now - last_updated).total_seconds()
        except (ValueError, TypeError):
            no_timestamp.append(key)
            continue

        ttl = r.ttl(key)
        entry = {
            "key": key,
            "age_s": round(age, 1),
            "ttl": ttl,
            "price": data.get("price", "?"),
            "last_updated": last_updated_str,
        }

        if age > MAX_AGE_SECONDS:
            stale.append(entry)
        else:
            fresh.append(entry)

    # Display results
    print(f"  Fresh  : {len(fresh)}")
    print(f"  Stale  : {len(stale)}")
    print(f"  No TS  : {len(no_timestamp)}")

    if fresh:
        print(f"\n{'Key':40s} {'Age':>8s} {'TTL':>6s} {'Price':>14s}")
        print("-" * 72)
        for e in fresh[:20]:  # Show first 20
            print(f"  {e['key']:38s} {e['age_s']:>7.0f}s {e['ttl']:>5d}s {e['price']:>14s}")
        if len(fresh) > 20:
            print(f"  ... and {len(fresh) - 20} more")

    if stale:
        print(f"\n{'!'*60}")
        print("STALE ENTRIES (age > 5 minutes):")
        print(f"{'!'*60}")
        print(f"\n{'Key':40s} {'Age':>8s} {'TTL':>6s}")
        print("-" * 56)
        for e in stale:
            print(f"  {e['key']:38s} {e['age_s']:>7.0f}s {e['ttl']:>5d}s")
        print(f"\nAction: Force refresh via CoinGecko/Yahoo for {len(stale)} symbol(s).")

    if no_timestamp:
        print(f"\nEntries without timestamp ({len(no_timestamp)}):")
        for k in no_timestamp[:10]:
            print(f"  {k}")

    # Summary
    print("\n" + "=" * 60)
    if stale:
        print(f"FRESHNESS CHECK: FAIL — {len(stale)} stale entries detected")
        print("=" * 60)
        sys.exit(1)
    else:
        print(f"FRESHNESS CHECK: PASS — all {len(fresh)} entries within {MAX_AGE_SECONDS}s")
        print("=" * 60)


if __name__ == "__main__":
    main()
