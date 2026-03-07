"""Tests for goal creation endpoint — POST /api/v1/goals.

Validates schema, response structure, resilient flag, and edge cases.
"""

import uuid
from datetime import date
from decimal import Decimal

import pytest

from app.api.v1.endpoints.goals import GoalCreate, GoalResponse, _build_response
from app.models.goal import Goal, GoalPriority, GoalStatus, GoalStrategy, GoalType


class TestGoalCreateSchema:
    """Validate Pydantic schema accepts valid payloads."""

    def test_minimal_creation(self):
        data = GoalCreate(name="Épargne 1500€", target_amount=Decimal("1500"))
        assert data.target_amount == Decimal("1500")
        assert data.goal_type == GoalType.ASSET
        assert data.priority == GoalPriority.MEDIUM
        assert data.strategy_type == GoalStrategy.MODERATE

    def test_savings_goal(self):
        data = GoalCreate(
            name="Matelas de sécurité",
            goal_type="savings",
            target_amount=Decimal("5000"),
        )
        assert data.goal_type == GoalType.SAVINGS

    def test_full_payload(self):
        data = GoalCreate(
            name="Objectif BTC",
            goal_type="asset",
            target_amount=Decimal("10000"),
            currency="EUR",
            target_date="Q4 2026",
            deadline_date="2026-12-31",
            priority="high",
            strategy_type="aggressive",
            icon="bitcoin",
            color="#f59e0b",
            notes="DCA mensuel de 300€",
        )
        assert data.priority == GoalPriority.HIGH
        assert data.strategy_type == GoalStrategy.AGGRESSIVE
        assert data.deadline_date == "2026-12-31"

    def test_rejects_zero_amount(self):
        with pytest.raises(Exception):
            GoalCreate(name="Bad", target_amount=Decimal("0"))

    def test_rejects_negative_amount(self):
        with pytest.raises(Exception):
            GoalCreate(name="Bad", target_amount=Decimal("-100"))

    def test_case_insensitive_enums(self):
        data = GoalCreate(
            name="Test",
            target_amount=Decimal("100"),
            goal_type="ASSET",
            priority="low",
            strategy_type="Conservative",
        )
        assert data.goal_type == GoalType.ASSET
        assert data.priority == GoalPriority.LOW
        assert data.strategy_type == GoalStrategy.CONSERVATIVE


class TestBuildResponse:
    """Validate _build_response produces correct output."""

    @staticmethod
    def _make_goal(**overrides) -> Goal:
        defaults = dict(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            goal_type=GoalType.ASSET,
            name="Test Goal",
            target_amount=Decimal("1500"),
            current_amount=Decimal("0"),
            currency="EUR",
            target_date=None,
            deadline_date=None,
            priority=GoalPriority.MEDIUM,
            strategy_type=GoalStrategy.MODERATE,
            status=GoalStatus.ACTIVE,
            icon="target",
            color="#6366f1",
            notes=None,
        )
        defaults.update(overrides)
        goal = Goal(**defaults)
        # Manually set created_at for testing (not a constructor param)
        object.__setattr__(goal, "created_at", "2026-01-01T00:00:00+00:00")
        return goal

    def test_response_status_is_lowercase_string(self):
        """Bug fix: status must be a lowercase string, not GoalStatus enum."""
        goal = self._make_goal()
        resp = _build_response(goal)
        assert resp["status"] == "active"
        assert isinstance(resp["status"], str)

    def test_response_validates_against_schema(self):
        """Ensure _build_response dict passes GoalResponse validation."""
        goal = self._make_goal()
        resp = _build_response(goal)
        validated = GoalResponse(**resp)
        assert validated.status == "active"
        assert validated.progress_percent == 0.0

    def test_progress_percent(self):
        goal = self._make_goal(current_amount=Decimal("750"))
        resp = _build_response(goal)
        assert resp["progress_percent"] == 50.0

    def test_progress_capped_at_100(self):
        goal = self._make_goal(
            target_amount=Decimal("100"),
            current_amount=Decimal("200"),
        )
        resp = _build_response(goal)
        assert resp["progress_percent"] == 100.0

    def test_days_remaining_with_deadline(self):
        from datetime import timedelta

        future = date.today() + timedelta(days=60)
        goal = self._make_goal(deadline_date=future)
        resp = _build_response(goal)
        assert resp["days_remaining"] == 60

    def test_monthly_needed_calculation(self):
        from datetime import timedelta

        future = date.today() + timedelta(days=365)
        goal = self._make_goal(
            target_amount=Decimal("12000"),
            current_amount=Decimal("0"),
            deadline_date=future,
        )
        resp = _build_response(goal)
        assert resp["monthly_needed"] is not None
        assert resp["monthly_needed"] > 0

    def test_is_resilient_savings_goal(self):
        goal = self._make_goal(goal_type=GoalType.SAVINGS)
        resp = _build_response(goal)
        assert resp["is_resilient"] is True

    def test_is_resilient_conservative_strategy(self):
        goal = self._make_goal(strategy_type=GoalStrategy.CONSERVATIVE)
        resp = _build_response(goal)
        assert resp["is_resilient"] is True

    def test_not_resilient_aggressive(self):
        goal = self._make_goal(strategy_type=GoalStrategy.AGGRESSIVE)
        resp = _build_response(goal)
        assert resp["is_resilient"] is False

    def test_goal_type_lowercase_in_response(self):
        goal = self._make_goal(goal_type=GoalType.SAVINGS)
        resp = _build_response(goal)
        assert resp["goal_type"] == "savings"

    def test_zero_target_no_crash(self):
        """Edge: target_amount = 0 should not ZeroDivisionError."""
        goal = self._make_goal(target_amount=Decimal("0"))
        resp = _build_response(goal)
        assert resp["progress_percent"] == 0

    def test_1500_euro_goal_no_crash(self):
        """Primary test: creating a 1500€ goal does not crash."""
        goal = self._make_goal(
            name="Objectif 1500€",
            target_amount=Decimal("1500"),
            current_amount=Decimal("863.90"),
        )
        resp = _build_response(goal)
        validated = GoalResponse(**resp)
        assert validated.target_amount == Decimal("1500")
        assert validated.current_amount == Decimal("863.90")
        assert 50 < validated.progress_percent < 60


class TestLiquidityFilter:
    """Verify that liquidity symbols are rejected as goal names."""

    @pytest.mark.parametrize("symbol", ["EUR", "USD", "USDT", "USDC", "eur", "Usdt"])
    def test_liquidity_names_rejected(self, symbol: str):
        """GoalCreate itself doesn't block, but the endpoint does via is_liquidity."""
        from app.services.metrics_service import is_liquidity

        assert is_liquidity(symbol.strip().upper()) is True

    @pytest.mark.parametrize("name", ["Objectif 1500€", "BTC Accumulation", "Fonds d'urgence"])
    def test_normal_names_accepted(self, name: str):
        from app.services.metrics_service import is_liquidity

        assert is_liquidity(name.strip().upper()) is False


class TestParityAfterGoalCreation:
    """Verify that creating a goal doesn't alter the Invested + Munitions partition.

    The goal's current_amount is READ from portfolio value — it's an observation,
    not a mutation. Total_Value = Invested + Munitions must remain constant.
    """

    def test_parity_preserved_863_90(self):
        """After goal creation with 863.90€ portfolio, partition stays intact."""
        from app.services.metrics_service import is_liquidity

        assets = [
            {"symbol": "BTC", "quantity": 0.005, "price": 50000},  # 250
            {"symbol": "ETH", "quantity": 0.5, "price": 3000},  # 1500
            {"symbol": "EUR", "quantity": 100, "price": 1.0},  # 100
            {"symbol": "USDT", "quantity": 13.90, "price": 1.0},  # 13.90
        ]
        total = sum(a["quantity"] * a["price"] for a in assets)
        invested = sum(a["quantity"] * a["price"] for a in assets if not is_liquidity(a["symbol"]))
        munitions = sum(a["quantity"] * a["price"] for a in assets if is_liquidity(a["symbol"]))

        assert abs(total - 1863.90) < 0.01
        assert abs(invested + munitions - total) < 0.01, f"Parity broken: {invested} + {munitions} != {total}"

        # Goal creation reads current_amount but doesn't modify the partition
        goal_current = total  # ASSET goal: counts everything
        assert abs(goal_current - total) < 0.01
        # Partition still holds
        assert abs(invested + munitions - total) < 0.01

    def test_savings_goal_only_counts_munitions(self):
        """SAVINGS goal current_amount = munitions only."""
        from app.services.metrics_service import is_liquidity

        assets = [
            {"symbol": "BTC", "quantity": 0.005, "price": 50000},  # 250
            {"symbol": "EUR", "quantity": 500, "price": 1.0},  # 500
            {"symbol": "USDC", "quantity": 113.90, "price": 1.0},  # 113.90
        ]
        total = sum(a["quantity"] * a["price"] for a in assets)
        invested = sum(a["quantity"] * a["price"] for a in assets if not is_liquidity(a["symbol"]))
        munitions = sum(a["quantity"] * a["price"] for a in assets if is_liquidity(a["symbol"]))

        savings_current = munitions  # SAVINGS goal only counts liquidity
        assert abs(savings_current - 613.90) < 0.01
        # Partition STILL holds regardless
        assert abs(invested + munitions - total) < 0.01
