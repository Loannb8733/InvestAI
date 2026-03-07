"""Stress-test Or : simule une chute BTC -15% et vérifie la résilience de l'Or.

Tests:
1. Gold maintains its value when BTC crashes -15%.
2. Flash Crash impact is dampened by gold holdings.
3. is_safe_haven correctly identifies gold symbols.
4. Gold beta vs BTC is < 0.1 (décorrélation systémique).
"""

import numpy as np

from app.services.metrics_service import is_safe_haven

# ── Helper: generate synthetic price series ──────────────────────


def _btc_crash_series(days: int = 90, crash_pct: float = -0.15) -> list:
    """Generate BTC prices: steady then -15% crash in last 5 days."""
    prices = [40_000.0]
    np.random.seed(42)
    for _ in range(days - 6):
        prices.append(prices[-1] * (1 + np.random.normal(0.001, 0.02)))
    # Crash: spread -15% over 5 days
    daily_crash = (1 + crash_pct) ** (1 / 5)
    for _ in range(5):
        prices.append(prices[-1] * daily_crash)
    return prices


def _gold_stable_series(days: int = 90) -> list:
    """Generate gold (PAXG) prices: low-vol, uncorrelated to BTC."""
    prices = [2_300.0]
    np.random.seed(7)  # different seed = uncorrelated
    for _ in range(days - 1):
        prices.append(prices[-1] * (1 + np.random.normal(0.0002, 0.005)))
    return prices


# ── Tests ────────────────────────────────────────────────────────


class TestSafeHavenIdentification:
    """is_safe_haven correctly recognises gold symbols."""

    def test_paxg_is_safe_haven(self):
        assert is_safe_haven("PAXG") is True

    def test_xaut_is_safe_haven(self):
        assert is_safe_haven("XAUT") is True

    def test_gld_etf_is_safe_haven(self):
        assert is_safe_haven("GLD") is True

    def test_btc_is_not_safe_haven(self):
        assert is_safe_haven("BTC") is False

    def test_eth_is_not_safe_haven(self):
        assert is_safe_haven("ETH") is False

    def test_case_insensitive(self):
        assert is_safe_haven("paxg") is True


class TestGoldBetaVsBTC:
    """Gold should have Beta < 0.1 vs BTC (décorrélation systémique)."""

    def test_gold_beta_below_threshold(self):
        btc = _btc_crash_series(90)
        gold = _gold_stable_series(90)
        _min = min(len(btc), len(gold))
        btc_r = np.diff(np.log(np.array(btc[-_min:], dtype=float)))
        gold_r = np.diff(np.log(np.array(gold[-_min:], dtype=float)))
        cov = np.cov(gold_r, btc_r)
        btc_var = cov[1, 1]
        beta = cov[0, 1] / btc_var if btc_var > 0 else 0.0
        assert abs(beta) < 0.10, f"Gold beta vs BTC should be < 0.1, got {beta:.4f}"


class TestBTCCrashGoldResilient:
    """Simulate BTC -15% and verify gold maintains value."""

    def test_gold_holds_value_during_btc_crash(self):
        btc = _btc_crash_series(90, crash_pct=-0.15)
        gold = _gold_stable_series(90)

        # BTC lost ~15% in last 5 days
        btc_crash_impact = (btc[-1] / btc[-6] - 1) * 100
        assert btc_crash_impact < -10, f"BTC should crash > 10%, got {btc_crash_impact:.1f}%"

        # Gold should be within ±3% over same period
        gold_change = (gold[-1] / gold[-6] - 1) * 100
        assert abs(gold_change) < 3.0, f"Gold should be stable, got {gold_change:.1f}%"

    def test_flash_crash_dampened_by_gold(self):
        """Portfolio with 10% gold should lose less than 100% crypto portfolio."""
        btc = _btc_crash_series(90, crash_pct=-0.15)
        gold = _gold_stable_series(90)

        # Portfolio A: 100% BTC (1000 EUR)
        btc_return = btc[-1] / btc[-6] - 1
        loss_all_btc = 1000 * btc_return

        # Portfolio B: 90% BTC + 10% Gold
        gold_return = gold[-1] / gold[-6] - 1
        loss_with_gold = 900 * btc_return + 100 * gold_return

        # Gold portfolio loses less
        assert loss_with_gold > loss_all_btc, (
            f"Gold hedge should reduce loss: all-BTC={loss_all_btc:.2f}, " f"with-gold={loss_with_gold:.2f}"
        )
        # The dampening should be at least 1 EUR on a 1000 EUR portfolio
        dampening = loss_with_gold - loss_all_btc
        assert dampening > 1.0, f"Dampening too small: {dampening:.2f} EUR"
