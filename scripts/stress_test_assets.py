#!/usr/bin/env python3
"""
InvestAI 5K Stress Test
=======================
Injects 5 000 transactions across 50 assets and 5 exchanges, then benchmarks
the dashboard metrics endpoint and validates P&L integrity.

Usage:
    # Against local dev server (default)
    python scripts/stress_test_assets.py

    # Against a custom server
    python scripts/stress_test_assets.py --base-url http://localhost:8000

    # Skip data injection (re-run benchmark only)
    python scripts/stress_test_assets.py --skip-inject

    # Cleanup test data when done
    python scripts/stress_test_assets.py --cleanup

Requirements:
    pip install httpx psutil
"""

from __future__ import annotations

import argparse
import math
import os
import random
import statistics
import sys
import time
import tracemalloc
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

try:
    import httpx
except ImportError:
    sys.exit("httpx is required: pip install httpx")

try:
    import psutil
except ImportError:
    psutil = None  # type: ignore[assignment]

# ============== Configuration ==============

NUM_ASSETS = 50
NUM_TRANSACTIONS = 5_000
NUM_EXCHANGES = 5
BENCHMARK_ITERATIONS = 5
PORTFOLIO_NAME = "__stress_test_5k__"

EXCHANGES = ["Binance", "Kraken", "Crypto.com", "Coinbase", "Ledger"]

# Realistic crypto symbols (50 total)
SYMBOLS = [
    "BTC", "ETH", "SOL", "ADA", "AVAX", "DOT", "ATOM", "NEAR", "SUI", "APT",
    "MATIC", "ARB", "OP", "IMX", "MNT", "UNI", "AAVE", "MKR", "LDO", "SNX",
    "DOGE", "SHIB", "PEPE", "FLOKI", "WIF", "INJ", "TIA", "SEI", "FTM", "ALGO",
    "XTZ", "EGLD", "HBAR", "ICP", "TON", "KAS", "CRV", "COMP", "SUSHI", "CAKE",
    "PENDLE", "RUNE", "JUP", "RAY", "GMX", "LINK", "FIL", "RENDER", "GRT", "AR",
]

# Base prices in EUR (rough orders of magnitude)
BASE_PRICES: Dict[str, float] = {
    "BTC": 60000, "ETH": 3000, "SOL": 150, "ADA": 0.45, "AVAX": 35,
    "DOT": 7, "ATOM": 9, "NEAR": 5, "SUI": 1.3, "APT": 9,
    "MATIC": 0.7, "ARB": 1.1, "OP": 2.5, "IMX": 2, "MNT": 0.8,
    "UNI": 10, "AAVE": 100, "MKR": 2800, "LDO": 2, "SNX": 3,
    "DOGE": 0.15, "SHIB": 0.000025, "PEPE": 0.000012, "FLOKI": 0.0002, "WIF": 2.5,
    "INJ": 25, "TIA": 8, "SEI": 0.5, "FTM": 0.7, "ALGO": 0.2,
    "XTZ": 1, "EGLD": 40, "HBAR": 0.1, "ICP": 12, "TON": 6,
    "KAS": 0.15, "CRV": 0.5, "COMP": 55, "SUSHI": 1, "CAKE": 2.5,
    "PENDLE": 5, "RUNE": 5, "JUP": 0.9, "RAY": 1.8, "GMX": 30,
    "LINK": 15, "FIL": 5, "RENDER": 8, "GRT": 0.25, "AR": 25,
}

# Transaction type weights: BUY heavy, some SELL, some conversions
TX_WEIGHTS = {
    "buy": 50,
    "sell": 20,
    "conversion_out": 10,   # matched with conversion_in
    "transfer_out": 8,      # matched with transfer_in
    "staking_reward": 7,
    "airdrop": 5,
}


# ============== Helpers ==============


def volatile_price(base: float, day_offset: int) -> float:
    """Generate a volatile price with daily random walk + mean reversion."""
    # Brownian-ish walk with drift
    drift = 0.0002 * day_offset  # slight upward drift
    noise = random.gauss(0, 0.03) * math.sqrt(abs(day_offset) + 1)
    factor = math.exp(drift + noise)
    # Clamp to [0.1x, 10x] of base price
    return max(base * 0.1, min(base * 10, base * factor))


def random_date(days_back: int = 365) -> str:
    """Random datetime within the past `days_back` days, ISO format."""
    offset = random.randint(0, days_back * 24 * 3600)
    dt = datetime.utcnow() - timedelta(seconds=offset)
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


def weighted_choice(weights: Dict[str, int]) -> str:
    """Weighted random selection from a dict of {choice: weight}."""
    choices = list(weights.keys())
    w = list(weights.values())
    return random.choices(choices, weights=w, k=1)[0]


class StressTestClient:
    """HTTP client wrapper for InvestAI API."""

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.client = httpx.Client(timeout=60.0)
        self.token: Optional[str] = None
        self.portfolio_id: Optional[str] = None
        # Track created asset IDs for cleanup
        self.asset_ids: Dict[str, str] = {}  # (symbol, exchange) -> asset_id

    @property
    def headers(self) -> Dict[str, str]:
        h = {"Content-Type": "application/json"}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        return h

    def _url(self, path: str) -> str:
        return f"{self.base_url}/api/v1{path}"

    def _check(self, resp: httpx.Response, context: str) -> Any:
        if resp.status_code >= 400:
            print(f"  [ERROR] {context}: {resp.status_code} — {resp.text[:300]}")
            return None
        return resp.json()

    # ---------- Auth ----------

    def login(self, email: str, password: str) -> bool:
        resp = self.client.post(
            self._url("/auth/login"),
            json={"email": email, "password": password},
            headers={"Content-Type": "application/json"},
        )
        data = self._check(resp, "login")
        if data:
            self.token = data["access_token"]
            return True
        return False

    def register(self, email: str, password: str) -> bool:
        resp = self.client.post(
            self._url("/auth/register"),
            json={"email": email, "password": password, "first_name": "Stress", "last_name": "Test"},
            headers={"Content-Type": "application/json"},
        )
        if resp.status_code in (200, 201):
            # Try to login right away
            return self.login(email, password)
        elif resp.status_code == 400 and "existe" in resp.text.lower():
            return self.login(email, password)
        print(f"  [WARN] register: {resp.status_code} — {resp.text[:200]}")
        return self.login(email, password)

    # ---------- Portfolio ----------

    def create_portfolio(self, name: str) -> Optional[str]:
        resp = self.client.post(
            self._url("/portfolios"),
            json={"name": name},
            headers=self.headers,
        )
        data = self._check(resp, "create_portfolio")
        if data:
            self.portfolio_id = data["id"]
            return data["id"]
        return None

    def find_portfolio(self, name: str) -> Optional[str]:
        resp = self.client.get(self._url("/portfolios"), headers=self.headers)
        data = self._check(resp, "list_portfolios")
        if data:
            for p in data:
                if p["name"] == name:
                    self.portfolio_id = p["id"]
                    return p["id"]
        return None

    def delete_portfolio(self, portfolio_id: str) -> bool:
        resp = self.client.delete(
            self._url(f"/portfolios/{portfolio_id}"),
            headers=self.headers,
        )
        return resp.status_code < 400

    # ---------- Assets ----------

    def create_asset(self, symbol: str, exchange: str) -> Optional[str]:
        key = (symbol, exchange)
        if key in self.asset_ids:
            return self.asset_ids[key]

        resp = self.client.post(
            self._url("/assets"),
            json={
                "portfolio_id": self.portfolio_id,
                "symbol": symbol,
                "name": f"{symbol} Token",
                "asset_type": "crypto",
                "currency": "EUR",
                "exchange": exchange,
                "quantity": "0",
                "avg_buy_price": "0",
            },
            headers=self.headers,
        )
        data = self._check(resp, f"create_asset({symbol}@{exchange})")
        if data:
            self.asset_ids[key] = data["id"]
            return data["id"]
        # Might already exist (409)
        if resp.status_code == 409:
            # List assets and find it
            return self._find_asset(symbol, exchange)
        return None

    def _find_asset(self, symbol: str, exchange: str) -> Optional[str]:
        resp = self.client.get(
            self._url(f"/assets?portfolio_id={self.portfolio_id}"),
            headers=self.headers,
        )
        data = self._check(resp, "list_assets")
        if data:
            items = data if isinstance(data, list) else data.get("items", data)
            for a in items:
                if a.get("symbol", "").upper() == symbol.upper() and a.get("exchange", "") == exchange:
                    self.asset_ids[(symbol, exchange)] = a["id"]
                    return a["id"]
        return None

    # ---------- Transactions ----------

    def create_transaction(self, tx: Dict[str, Any]) -> Optional[str]:
        resp = self.client.post(
            self._url("/transactions"),
            json=tx,
            headers=self.headers,
        )
        if resp.status_code >= 400:
            # Silently skip duplicates / validation errors for speed
            return None
        data = resp.json()
        return data.get("id")

    # ---------- Dashboard ----------

    def get_dashboard_metrics(self, days: int = 0) -> Tuple[Optional[Dict], float]:
        """Fetch dashboard metrics. Returns (data, elapsed_seconds)."""
        start = time.perf_counter()
        resp = self.client.get(
            self._url(f"/dashboard?days={days}"),
            headers=self.headers,
        )
        elapsed = time.perf_counter() - start
        data = self._check(resp, "dashboard_metrics")
        return data, elapsed

    def get_portfolio_metrics(self, portfolio_id: str) -> Tuple[Optional[Dict], float]:
        start = time.perf_counter()
        resp = self.client.get(
            self._url(f"/dashboard/portfolio/{portfolio_id}"),
            headers=self.headers,
        )
        elapsed = time.perf_counter() - start
        data = self._check(resp, "portfolio_metrics")
        return data, elapsed


# ============== Data Generation ==============


def generate_transactions(
    client: StressTestClient,
    num_assets: int = NUM_ASSETS,
    num_transactions: int = NUM_TRANSACTIONS,
) -> List[Dict[str, Any]]:
    """Generate realistic transaction data for stress testing."""
    transactions: List[Dict[str, Any]] = []

    # Select assets: distribute across exchanges
    asset_exchange_pairs: List[Tuple[str, str]] = []
    for i, symbol in enumerate(SYMBOLS[:num_assets]):
        # Each symbol on 1-3 exchanges
        num_ex = random.randint(1, min(3, NUM_EXCHANGES))
        for ex in random.sample(EXCHANGES, num_ex):
            asset_exchange_pairs.append((symbol, ex))

    print(f"  Creating {len(asset_exchange_pairs)} asset/exchange pairs...")

    # Create assets via API
    for symbol, exchange in asset_exchange_pairs:
        client.create_asset(symbol, exchange)

    # Track quantities per (symbol, exchange) to avoid selling more than owned
    quantities: Dict[Tuple[str, str], Decimal] = {}

    # Generate transactions chronologically
    base_date = datetime.utcnow() - timedelta(days=365)

    for i in range(num_transactions):
        tx_type = weighted_choice(TX_WEIGHTS)
        day_offset = random.randint(0, 365)
        executed_at = base_date + timedelta(
            days=day_offset,
            hours=random.randint(0, 23),
            minutes=random.randint(0, 59),
        )

        # Pick a random asset/exchange pair
        symbol, exchange = random.choice(asset_exchange_pairs)
        asset_id = client.asset_ids.get((symbol, exchange))
        if not asset_id:
            continue

        base_price = BASE_PRICES.get(symbol, 1.0)
        price = volatile_price(base_price, day_offset)

        key = (symbol, exchange)
        current_qty = quantities.get(key, Decimal("0"))

        if tx_type == "buy":
            # BUY: random quantity based on price tier
            if price > 10000:
                qty = round(random.uniform(0.001, 0.1), 8)
            elif price > 100:
                qty = round(random.uniform(0.1, 5), 6)
            elif price > 1:
                qty = round(random.uniform(1, 100), 4)
            elif price > 0.01:
                qty = round(random.uniform(100, 10000), 2)
            else:
                qty = round(random.uniform(10000, 1000000), 0)

            fee = round(price * qty * random.uniform(0.0005, 0.003), 6)
            tx = {
                "asset_id": asset_id,
                "transaction_type": "buy",
                "quantity": str(qty),
                "price": str(round(price, 8)),
                "fee": str(fee),
                "currency": "EUR",
                "exchange": exchange,
                "executed_at": executed_at.isoformat(),
                "notes": f"stress_test_buy_{i}",
            }
            quantities[key] = current_qty + Decimal(str(qty))
            transactions.append(tx)

        elif tx_type == "sell":
            if current_qty <= 0:
                # Can't sell — switch to BUY
                qty = round(random.uniform(1, 10), 4)
                tx = {
                    "asset_id": asset_id,
                    "transaction_type": "buy",
                    "quantity": str(qty),
                    "price": str(round(price, 8)),
                    "fee": "0",
                    "currency": "EUR",
                    "exchange": exchange,
                    "executed_at": executed_at.isoformat(),
                    "notes": f"stress_test_fallback_buy_{i}",
                }
                quantities[key] = current_qty + Decimal(str(qty))
                transactions.append(tx)
                continue

            # Sell 10-80% of current position
            sell_frac = random.uniform(0.1, 0.8)
            sell_qty = float(current_qty) * sell_frac
            sell_qty = max(0.00000001, round(sell_qty, 8))

            fee = round(price * sell_qty * random.uniform(0.0005, 0.002), 6)
            tx = {
                "asset_id": asset_id,
                "transaction_type": "sell",
                "quantity": str(sell_qty),
                "price": str(round(price, 8)),
                "fee": str(fee),
                "currency": "EUR",
                "exchange": exchange,
                "executed_at": executed_at.isoformat(),
                "notes": f"stress_test_sell_{i}",
            }
            quantities[key] = current_qty - Decimal(str(sell_qty))
            transactions.append(tx)

        elif tx_type == "conversion_out":
            if current_qty <= 0:
                continue

            # Pick a different symbol on the same exchange for conversion target
            dest_candidates = [
                (s, e) for s, e in asset_exchange_pairs
                if e == exchange and s != symbol
            ]
            if not dest_candidates:
                continue

            dest_symbol, dest_exchange = random.choice(dest_candidates)
            dest_asset_id = client.asset_ids.get((dest_symbol, dest_exchange))
            if not dest_asset_id:
                continue

            conv_frac = random.uniform(0.1, 0.5)
            conv_qty = float(current_qty) * conv_frac
            conv_qty = max(0.00000001, round(conv_qty, 8))

            dest_price = volatile_price(BASE_PRICES.get(dest_symbol, 1.0), day_offset)
            dest_qty = round((price * conv_qty) / dest_price, 8) if dest_price > 0 else 0

            conv_id = f"stress_conv_{i}_{uuid.uuid4().hex[:8]}"

            # CONVERSION_OUT
            tx_out = {
                "asset_id": asset_id,
                "transaction_type": "conversion_out",
                "quantity": str(conv_qty),
                "price": str(round(price, 8)),
                "fee": "0",
                "currency": "EUR",
                "exchange": exchange,
                "executed_at": executed_at.isoformat(),
                "notes": conv_id,
            }
            # CONVERSION_IN
            tx_in = {
                "asset_id": dest_asset_id,
                "transaction_type": "conversion_in",
                "quantity": str(dest_qty),
                "price": str(round(dest_price, 8)),
                "fee": "0",
                "currency": "EUR",
                "exchange": dest_exchange,
                "executed_at": (executed_at + timedelta(seconds=1)).isoformat(),
                "notes": conv_id,
            }
            quantities[key] = current_qty - Decimal(str(conv_qty))
            dest_key = (dest_symbol, dest_exchange)
            quantities[dest_key] = quantities.get(dest_key, Decimal("0")) + Decimal(str(dest_qty))
            transactions.append(tx_out)
            transactions.append(tx_in)

        elif tx_type == "transfer_out":
            if current_qty <= 0:
                continue

            # Transfer to a different exchange
            other_exchanges = [e for e in EXCHANGES if e != exchange]
            if not other_exchanges:
                continue
            dest_exchange = random.choice(other_exchanges)
            dest_asset_id = client.asset_ids.get((symbol, dest_exchange))
            if not dest_asset_id:
                # Create the asset on the destination exchange
                dest_asset_id = client.create_asset(symbol, dest_exchange)
                if not dest_asset_id:
                    continue

            transfer_frac = random.uniform(0.2, 0.9)
            transfer_qty = float(current_qty) * transfer_frac
            transfer_qty = max(0.00000001, round(transfer_qty, 8))

            # TRANSFER_OUT with destination_exchange triggers auto mirror
            tx = {
                "asset_id": asset_id,
                "transaction_type": "transfer_out",
                "quantity": str(transfer_qty),
                "price": "0",
                "fee": str(round(random.uniform(0, 0.5), 6)),
                "currency": "EUR",
                "exchange": exchange,
                "executed_at": executed_at.isoformat(),
                "destination_exchange": dest_exchange,
                "notes": f"stress_transfer_{i}",
            }
            quantities[key] = current_qty - Decimal(str(transfer_qty))
            dest_key = (symbol, dest_exchange)
            quantities[dest_key] = quantities.get(dest_key, Decimal("0")) + Decimal(str(transfer_qty))
            transactions.append(tx)

        elif tx_type == "staking_reward":
            # Small reward amounts
            reward_qty = round(random.uniform(0.0001, 0.1) * (1 if price > 1 else 1000), 8)
            tx = {
                "asset_id": asset_id,
                "transaction_type": "staking_reward",
                "quantity": str(reward_qty),
                "price": str(round(price, 8)),
                "fee": "0",
                "currency": "EUR",
                "exchange": exchange,
                "executed_at": executed_at.isoformat(),
                "notes": f"stress_reward_{i}",
            }
            quantities[key] = current_qty + Decimal(str(reward_qty))
            transactions.append(tx)

        elif tx_type == "airdrop":
            airdrop_qty = round(random.uniform(1, 100) * (1 if price > 0.1 else 1000), 6)
            tx = {
                "asset_id": asset_id,
                "transaction_type": "airdrop",
                "quantity": str(airdrop_qty),
                "price": str(round(price, 8)),
                "fee": "0",
                "currency": "EUR",
                "exchange": exchange,
                "executed_at": executed_at.isoformat(),
                "notes": f"stress_airdrop_{i}",
            }
            quantities[key] = current_qty + Decimal(str(airdrop_qty))
            transactions.append(tx)

    return transactions


# ============== Benchmark ==============


def benchmark_endpoints(client: StressTestClient, iterations: int = BENCHMARK_ITERATIONS) -> Dict[str, Any]:
    """Benchmark dashboard and portfolio metrics endpoints."""
    results: Dict[str, Any] = {}

    # --- Dashboard metrics (all portfolios) ---
    print("\n  Benchmarking GET /api/v1/dashboard?days=0 ...")
    times_dashboard: List[float] = []
    dashboard_data = None
    for i in range(iterations):
        data, elapsed = client.get_dashboard_metrics(days=0)
        times_dashboard.append(elapsed)
        if data:
            dashboard_data = data
        print(f"    Iteration {i + 1}/{iterations}: {elapsed:.3f}s")

    results["dashboard"] = {
        "times": times_dashboard,
        "mean": statistics.mean(times_dashboard),
        "median": statistics.median(times_dashboard),
        "p95": sorted(times_dashboard)[int(len(times_dashboard) * 0.95)] if len(times_dashboard) > 1 else times_dashboard[0],
        "min": min(times_dashboard),
        "max": max(times_dashboard),
    }

    # --- Portfolio metrics ---
    if client.portfolio_id:
        print(f"\n  Benchmarking GET /api/v1/dashboard/portfolio/{client.portfolio_id} ...")
        times_portfolio: List[float] = []
        portfolio_data = None
        for i in range(iterations):
            data, elapsed = client.get_portfolio_metrics(client.portfolio_id)
            times_portfolio.append(elapsed)
            if data:
                portfolio_data = data
            print(f"    Iteration {i + 1}/{iterations}: {elapsed:.3f}s")

        results["portfolio"] = {
            "times": times_portfolio,
            "mean": statistics.mean(times_portfolio),
            "median": statistics.median(times_portfolio),
            "p95": sorted(times_portfolio)[int(len(times_portfolio) * 0.95)] if len(times_portfolio) > 1 else times_portfolio[0],
            "min": min(times_portfolio),
            "max": max(times_portfolio),
        }

    results["dashboard_data"] = dashboard_data
    results["portfolio_data"] = portfolio_data
    return results


# ============== SQL Index Verification ==============


def verify_sql_indexes(db_url: Optional[str] = None) -> Dict[str, Any]:
    """Run EXPLAIN ANALYZE on critical queries to verify index usage."""
    results: Dict[str, Any] = {"indexes_verified": False, "details": []}

    if not db_url:
        db_url = os.environ.get("DATABASE_URL", "")
    if not db_url:
        print("  [SKIP] No DATABASE_URL — cannot verify SQL indexes.")
        return results

    # Convert async URL to sync for psycopg2/sqlalchemy sync
    sync_url = db_url.replace("postgresql+asyncpg://", "postgresql://")
    sync_url = sync_url.replace("postgresql+psycopg2://", "postgresql://")

    try:
        from sqlalchemy import create_engine, text

        engine = create_engine(sync_url, pool_pre_ping=True)
        with engine.connect() as conn:
            queries = [
                (
                    "ix_transactions_asset_id_transaction_type",
                    """
                    EXPLAIN ANALYZE
                    SELECT t.id, t.quantity, t.price
                    FROM transactions t
                    WHERE t.asset_id = (SELECT id FROM assets LIMIT 1)
                      AND t.transaction_type = 'BUY'
                    """,
                ),
                (
                    "ix_transactions_asset_id_executed_at",
                    """
                    EXPLAIN ANALYZE
                    SELECT t.id, t.executed_at
                    FROM transactions t
                    WHERE t.asset_id = (SELECT id FROM assets LIMIT 1)
                    ORDER BY t.executed_at
                    LIMIT 100
                    """,
                ),
                (
                    "ix_assets_portfolio_id",
                    """
                    EXPLAIN ANALYZE
                    SELECT a.id, a.symbol
                    FROM assets a
                    WHERE a.portfolio_id = (SELECT id FROM portfolios LIMIT 1)
                    """,
                ),
            ]

            for idx_name, query in queries:
                try:
                    result = conn.execute(text(query))
                    plan_lines = [row[0] for row in result]
                    plan_text = "\n".join(plan_lines)

                    uses_index = "Index" in plan_text
                    uses_seq_scan = "Seq Scan" in plan_text and "Index" not in plan_text

                    detail = {
                        "index": idx_name,
                        "uses_index": uses_index,
                        "seq_scan_only": uses_seq_scan,
                        "plan_summary": plan_lines[0] if plan_lines else "N/A",
                    }
                    results["details"].append(detail)

                    status = "OK (Index Scan)" if uses_index else "WARN (Seq Scan)"
                    print(f"    {idx_name}: {status}")
                    if uses_index:
                        print(f"      Plan: {plan_lines[0]}")
                except Exception as e:
                    results["details"].append({"index": idx_name, "error": str(e)})
                    print(f"    {idx_name}: ERROR — {e}")

            results["indexes_verified"] = True
    except ImportError:
        print("  [SKIP] sqlalchemy not available for sync queries.")
    except Exception as e:
        print(f"  [ERROR] SQL index verification failed: {e}")

    return results


# ============== Memory Profiling ==============


def measure_memory(label: str) -> Dict[str, float]:
    """Snapshot current process memory."""
    info: Dict[str, float] = {}
    if psutil:
        proc = psutil.Process()
        mem = proc.memory_info()
        info["rss_mb"] = mem.rss / (1024 * 1024)
        info["vms_mb"] = mem.vms / (1024 * 1024)
    # tracemalloc peak
    current, peak = tracemalloc.get_traced_memory()
    info["tracemalloc_current_mb"] = current / (1024 * 1024)
    info["tracemalloc_peak_mb"] = peak / (1024 * 1024)
    print(f"  [{label}] RSS={info.get('rss_mb', '?'):.1f}MB, "
          f"tracemalloc_peak={info['tracemalloc_peak_mb']:.1f}MB")
    return info


# ============== P&L Integrity Check ==============


def verify_pnl_integrity(dashboard_data: Optional[Dict], portfolio_data: Optional[Dict]) -> Dict[str, Any]:
    """Validate that Realized + Unrealized = Total P&L."""
    results: Dict[str, Any] = {"passed": False, "checks": []}

    # Check dashboard-level P&L
    if dashboard_data:
        adv = dashboard_data.get("advanced_metrics", {})
        pnl = adv.get("pnl_breakdown", {})
        realized = pnl.get("realized_pnl", 0)
        unrealized = pnl.get("unrealized_pnl", 0)
        total_pnl = pnl.get("total_pnl", 0)
        total_fees = pnl.get("total_fees", 0)
        net_pnl = pnl.get("net_pnl", 0)

        # Check: realized + unrealized == total_pnl
        sum_components = realized + unrealized
        diff = abs(sum_components - total_pnl)
        check1 = {
            "check": "realized + unrealized == total_pnl",
            "realized": realized,
            "unrealized": unrealized,
            "total_pnl": total_pnl,
            "diff": diff,
            "passed": diff < 0.01,
        }
        results["checks"].append(check1)

        # Check: net_pnl == total_pnl - fees
        expected_net = total_pnl - total_fees
        diff2 = abs(net_pnl - expected_net)
        check2 = {
            "check": "net_pnl == total_pnl - fees",
            "net_pnl": net_pnl,
            "expected": expected_net,
            "total_fees": total_fees,
            "diff": diff2,
            "passed": diff2 < 0.01,
        }
        results["checks"].append(check2)

        # Check: total_value - total_invested ~= total_pnl (single source of truth)
        total_value = dashboard_data.get("total_value", 0)
        total_invested = dashboard_data.get("total_invested", 0)
        implied_pnl = total_value - total_invested
        diff3 = abs(implied_pnl - total_pnl)
        check3 = {
            "check": "total_value - total_invested == total_pnl",
            "total_value": total_value,
            "total_invested": total_invested,
            "implied_pnl": implied_pnl,
            "total_pnl": total_pnl,
            "diff": diff3,
            "passed": diff3 < 0.02,  # small rounding tolerance
        }
        results["checks"].append(check3)

    # Check portfolio-level consistency
    if portfolio_data:
        total_val = portfolio_data.get("total_value", 0)
        total_inv = portfolio_data.get("total_invested", 0)
        total_gl = portfolio_data.get("total_gain_loss", 0)
        diff4 = abs((total_val - total_inv) - total_gl)
        check4 = {
            "check": "portfolio: value - invested == gain_loss",
            "total_value": total_val,
            "total_invested": total_inv,
            "total_gain_loss": total_gl,
            "diff": diff4,
            "passed": diff4 < 0.02,
        }
        results["checks"].append(check4)

    results["passed"] = all(c["passed"] for c in results["checks"]) if results["checks"] else False
    return results


# ============== Main ==============


def main():
    parser = argparse.ArgumentParser(description="InvestAI 5K Stress Test")
    parser.add_argument("--base-url", default="http://localhost:8000", help="API base URL")
    parser.add_argument("--email", default="stress@test.investai.local", help="Test user email")
    parser.add_argument("--password", default="StressTest123!", help="Test user password")
    parser.add_argument("--skip-inject", action="store_true", help="Skip data injection")
    parser.add_argument("--cleanup", action="store_true", help="Delete test portfolio and exit")
    parser.add_argument("--num-transactions", type=int, default=NUM_TRANSACTIONS, help="Number of transactions")
    parser.add_argument("--num-assets", type=int, default=NUM_ASSETS, help="Number of assets")
    parser.add_argument("--iterations", type=int, default=BENCHMARK_ITERATIONS, help="Benchmark iterations")
    parser.add_argument("--db-url", default=None, help="DATABASE_URL for EXPLAIN ANALYZE")
    args = parser.parse_args()

    tracemalloc.start()

    print("=" * 60)
    print("  InvestAI 5K Stress Test")
    print("=" * 60)
    print(f"  Target:       {args.base_url}")
    print(f"  Transactions: {args.num_transactions}")
    print(f"  Assets:       {args.num_assets}")
    print(f"  Iterations:   {args.iterations}")
    print()

    client = StressTestClient(args.base_url)

    # ---------- Step 0: Auth ----------
    print("[1/6] Authenticating...")
    if not client.register(args.email, args.password):
        if not client.login(args.email, args.password):
            print("  FATAL: Cannot authenticate. Is the server running?")
            sys.exit(1)
    print(f"  Authenticated as {args.email}")

    # ---------- Cleanup mode ----------
    if args.cleanup:
        print("\n[CLEANUP] Removing stress test portfolio...")
        pid = client.find_portfolio(PORTFOLIO_NAME)
        if pid:
            if client.delete_portfolio(pid):
                print(f"  Deleted portfolio {pid}")
            else:
                print(f"  Failed to delete portfolio {pid}")
        else:
            print("  No stress test portfolio found.")
        return

    # ---------- Step 1: Setup portfolio ----------
    print("\n[2/6] Setting up portfolio...")
    pid = client.find_portfolio(PORTFOLIO_NAME)
    if pid:
        print(f"  Found existing stress test portfolio: {pid}")
    else:
        pid = client.create_portfolio(PORTFOLIO_NAME)
        if not pid:
            print("  FATAL: Cannot create portfolio.")
            sys.exit(1)
        print(f"  Created portfolio: {pid}")

    mem_before = measure_memory("Before injection")

    # ---------- Step 2: Inject data ----------
    if not args.skip_inject:
        print(f"\n[3/6] Generating & injecting {args.num_transactions} transactions...")
        t0 = time.perf_counter()
        transactions = generate_transactions(client, args.num_assets, args.num_transactions)
        t_gen = time.perf_counter() - t0
        print(f"  Generated {len(transactions)} transactions in {t_gen:.1f}s")

        # Sort chronologically before injection
        transactions.sort(key=lambda tx: tx.get("executed_at", ""))

        # Inject in batches for progress
        injected = 0
        failed = 0
        t0 = time.perf_counter()
        batch_size = 100
        for i in range(0, len(transactions), batch_size):
            batch = transactions[i:i + batch_size]
            for tx in batch:
                result = client.create_transaction(tx)
                if result:
                    injected += 1
                else:
                    failed += 1
            pct = min(100, (i + batch_size) / len(transactions) * 100)
            elapsed = time.perf_counter() - t0
            rate = (i + batch_size) / elapsed if elapsed > 0 else 0
            print(f"\r  Progress: {pct:.0f}% ({injected} ok, {failed} err, {rate:.0f} tx/s)    ", end="")

        elapsed = time.perf_counter() - t0
        print(f"\n  Injected {injected} / {len(transactions)} transactions in {elapsed:.1f}s "
              f"({injected / elapsed:.0f} tx/s)")
    else:
        print("\n[3/6] Skipping injection (--skip-inject)")

    mem_after_inject = measure_memory("After injection")

    # ---------- Step 3: Benchmark endpoints ----------
    print("\n[4/6] Benchmarking endpoints...")
    bench = benchmark_endpoints(client, args.iterations)

    print("\n  --- Dashboard Metrics ---")
    d = bench["dashboard"]
    print(f"    Mean:   {d['mean']:.3f}s")
    print(f"    Median: {d['median']:.3f}s")
    print(f"    P95:    {d['p95']:.3f}s")
    print(f"    Min:    {d['min']:.3f}s | Max: {d['max']:.3f}s")

    if "portfolio" in bench:
        print("\n  --- Portfolio Metrics ---")
        p = bench["portfolio"]
        print(f"    Mean:   {p['mean']:.3f}s")
        print(f"    Median: {p['median']:.3f}s")
        print(f"    P95:    {p['p95']:.3f}s")
        print(f"    Min:    {p['min']:.3f}s | Max: {p['max']:.3f}s")

    mem_after_bench = measure_memory("After benchmark")

    # ---------- Step 4: SQL Index Verification ----------
    print("\n[5/6] Verifying SQL indexes (EXPLAIN ANALYZE)...")
    idx_results = verify_sql_indexes(args.db_url)

    # ---------- Step 5: P&L Integrity ----------
    print("\n[6/6] Verifying P&L integrity...")
    pnl_results = verify_pnl_integrity(bench.get("dashboard_data"), bench.get("portfolio_data"))

    for check in pnl_results["checks"]:
        status = "PASS" if check["passed"] else "FAIL"
        print(f"  [{status}] {check['check']} (diff={check['diff']:.4f})")

    # ---------- Summary ----------
    print("\n" + "=" * 60)
    print("  SUMMARY")
    print("=" * 60)

    # Performance verdict
    dashboard_mean = bench["dashboard"]["mean"]
    if dashboard_mean < 2.0:
        perf_verdict = "EXCELLENT (< 2s)"
    elif dashboard_mean < 5.0:
        perf_verdict = "ACCEPTABLE (< 5s)"
    elif dashboard_mean < 10.0:
        perf_verdict = "SLOW (< 10s)"
    else:
        perf_verdict = "CRITICAL (> 10s)"

    print(f"  Performance:   {perf_verdict} — dashboard mean {dashboard_mean:.3f}s")
    print(f"  P&L Integrity: {'PASS' if pnl_results['passed'] else 'FAIL'}")
    print(f"  SQL Indexes:   {'Verified' if idx_results['indexes_verified'] else 'Not checked'}")
    print(f"  Memory (peak): {mem_after_bench.get('tracemalloc_peak_mb', 0):.1f}MB tracemalloc")
    if psutil:
        print(f"  Memory (RSS):  {mem_after_bench.get('rss_mb', 0):.1f}MB")
    print()

    if not pnl_results["passed"]:
        print("  WARNING: P&L integrity checks FAILED. Review the details above.")
        sys.exit(2)

    print("  All checks passed.")


if __name__ == "__main__":
    main()
