"""Tests for strategy service — deployment capacity and munitions logic."""


from app.services.strategy_service import PROFILE_ALLOCATION, DeploymentCapacity


class TestProfileAllocation:
    """Verify DCA split percentages by profile."""

    def test_aggressive_profile(self):
        alloc = PROFILE_ALLOCATION["aggressive"]
        assert alloc["risk_pct"] == 90
        assert alloc["reserve_pct"] == 10
        assert alloc["risk_pct"] + alloc["reserve_pct"] == 100

    def test_moderate_profile(self):
        alloc = PROFILE_ALLOCATION["moderate"]
        assert alloc["risk_pct"] == 70
        assert alloc["reserve_pct"] == 30
        assert alloc["risk_pct"] + alloc["reserve_pct"] == 100

    def test_conservative_profile(self):
        alloc = PROFILE_ALLOCATION["conservative"]
        assert alloc["risk_pct"] == 40
        assert alloc["reserve_pct"] == 60
        assert alloc["risk_pct"] + alloc["reserve_pct"] == 100


class TestDeploymentCapacity:
    """Test the DeploymentCapacity dataclass logic."""

    def test_can_execute_when_enough_liquidity(self):
        dc = DeploymentCapacity(
            available_liquidity=200,
            total_value=1000,
            liquidity_pct=20,
            invested_pct=80,
            next_signal_symbol="BTC",
            next_signal_action="DCA",
            next_signal_amount=43.20,
            can_execute=True,
            shortfall=0,
        )
        assert dc.can_execute is True
        assert dc.shortfall == 0

    def test_cannot_execute_when_insufficient(self):
        dc = DeploymentCapacity(
            available_liquidity=20,
            total_value=1000,
            liquidity_pct=2,
            invested_pct=98,
            next_signal_symbol="ETH",
            next_signal_action="ACHAT FORT",
            next_signal_amount=43.20,
            can_execute=False,
            shortfall=23.20,
            message="Liquidité insuffisante pour le signal Alpha sur ETH (43.20 € requis, 20.00 € disponible).",
        )
        assert dc.can_execute is False
        assert dc.shortfall == 23.20
        assert "ETH" in dc.message

    def test_dca_split_moderate(self):
        alloc = PROFILE_ALLOCATION["moderate"]
        monthly = 300
        risk = monthly * alloc["risk_pct"] / 100
        reserve = monthly * alloc["reserve_pct"] / 100
        assert risk == 210
        assert reserve == 90
        assert risk + reserve == monthly

    def test_dca_split_aggressive(self):
        alloc = PROFILE_ALLOCATION["aggressive"]
        monthly = 300
        risk = monthly * alloc["risk_pct"] / 100
        reserve = monthly * alloc["reserve_pct"] / 100
        assert risk == 270
        assert reserve == 30

    def test_dca_split_conservative(self):
        alloc = PROFILE_ALLOCATION["conservative"]
        monthly = 300
        risk = monthly * alloc["risk_pct"] / 100
        reserve = monthly * alloc["reserve_pct"] / 100
        assert risk == 120
        assert reserve == 180


class TestSegregation:
    """Verify munitions are segregated from invested assets."""

    def test_liquidity_plus_invested_equals_total(self):
        """Parity: liquidity_pct + invested_pct = 100%."""
        dc = DeploymentCapacity(
            available_liquidity=150,
            total_value=863.90,
            liquidity_pct=17.4,
            invested_pct=82.6,
        )
        assert abs(dc.liquidity_pct + dc.invested_pct - 100) < 0.1

    def test_zero_liquidity(self):
        dc = DeploymentCapacity(
            available_liquidity=0,
            total_value=1000,
            liquidity_pct=0,
            invested_pct=100,
        )
        assert dc.liquidity_pct == 0
        assert dc.invested_pct == 100

    def test_all_liquidity(self):
        dc = DeploymentCapacity(
            available_liquidity=500,
            total_value=500,
            liquidity_pct=100,
            invested_pct=0,
        )
        assert dc.liquidity_pct == 100
        assert dc.invested_pct == 0

    def test_no_signal_means_can_execute(self):
        """When no alpha signal exists, can_execute defaults True."""
        dc = DeploymentCapacity(
            available_liquidity=100,
            total_value=1000,
            liquidity_pct=10,
            invested_pct=90,
            can_execute=True,
        )
        assert dc.can_execute is True
        assert dc.next_signal_symbol is None
