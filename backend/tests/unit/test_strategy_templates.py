"""Modèles de stratégie paramétrés : échéancier, description de la règle, simulation sur l'historique.

Tout découle des paramètres saisis : les fonctions testées ne reçoivent ni l'utilisateur, ni ses positions, ni
sa liquidité, et les modules du simulateur n'importent rien qui puisse les lire.
"""

import inspect
from datetime import UTC, date, datetime, timedelta

import pytest
from pydantic import TypeAdapter, ValidationError

from app.domains.strategies import backtest, router, schemas, templates
from app.domains.strategies.backtest import simulate_on_history
from app.domains.strategies.disclaimer import AI_DISCLAIMER, BACKTEST_NOTE, SIMULATION_DISCLAIMER
from app.domains.strategies.schemas import TemplateParams
from app.domains.strategies.templates import (
    actions_from_schedule,
    build_schedule,
    describe_rule,
    parse_template_params,
    schedule_dates,
    schedule_totals,
)

ADAPTER = TypeAdapter(TemplateParams)
D0 = date(2026, 1, 5)


def _params(**raw):
    return ADAPTER.validate_python(raw)


def _dca(**over):
    raw = {
        "template": "dca",
        "assets": [{"symbol": "btc", "weight_pct": 60}, {"symbol": "ETH", "weight_pct": 40}],
        "amount_per_period": 100,
        "frequency": "monthly",
        "periods": 3,
        "start_date": "2026-01-31",
    }
    return _params(**{**raw, **over})


def _series(before: float, after: float, switch_day: int = 21, days: int = 30) -> list[tuple[date, float]]:
    return [(D0 + timedelta(days=i), before if i < switch_day else after) for i in range(days + 1)]


class TestSchedule:
    def test_dca_splits_the_budget_by_the_chosen_weights_on_each_date(self) -> None:
        schedule = build_schedule(_dca())
        assert [(line.date, line.symbol, line.amount) for line in schedule] == [
            (date(2026, 1, 31), "BTC", 60.0),
            (date(2026, 1, 31), "ETH", 40.0),
            (date(2026, 2, 28), "BTC", 60.0),
            (date(2026, 2, 28), "ETH", 40.0),
            (date(2026, 3, 31), "BTC", 60.0),
            (date(2026, 3, 31), "ETH", 40.0),
        ]
        assert schedule_totals(schedule) == (300.0, 0.0, False)

    def test_frequencies(self) -> None:
        assert schedule_dates(D0, "weekly", 3) == [D0, date(2026, 1, 12), date(2026, 1, 19)]
        assert schedule_dates(D0, "biweekly", 2) == [D0, date(2026, 1, 19)]
        assert schedule_dates(date(2026, 11, 30), "quarterly", 2) == [date(2026, 11, 30), date(2027, 2, 28)]

    def test_vca_only_fixes_the_first_amount_the_others_follow_the_line_value(self) -> None:
        params = _params(
            template="vca",
            symbol="SOL",
            target_increment=50,
            max_per_period=30,
            frequency="weekly",
            periods=3,
            start_date=D0.isoformat(),
        )
        schedule = build_schedule(params)
        assert [(line.amount, line.target_value) for line in schedule] == [(30.0, 50.0), (None, 100.0), (None, 150.0)]
        assert schedule_totals(schedule) == (30.0, 0.0, True)

    def test_profit_tiers_are_sorted_by_price_and_sell_a_share_of_the_given_quantity(self) -> None:
        params = _params(
            template="profit_taking",
            symbol="BTC",
            quantity=0.5,
            tiers=[{"price": 100000, "sell_pct": 50}, {"price": 80000, "sell_pct": 25}],
        )
        schedule = build_schedule(params)
        assert [(line.trigger_price, line.quantity, line.amount, line.date) for line in schedule] == [
            (80000, 0.125, 10000.0, None),
            (100000, 0.25, 25000.0, None),
        ]
        assert {line.action for line in schedule} == {"SELL"}

    def _rebalance(self, threshold: float, contribution: float = 0.0):
        return _params(
            template="rebalance",
            lines=[
                {"symbol": "BTC", "target_pct": 50, "current_value": 700},
                {"symbol": "ETH", "target_pct": 50, "current_value": 300},
            ],
            contribution=contribution,
            threshold_pct=threshold,
            frequency="quarterly",
            periods=3,
            start_date=D0.isoformat(),
        )

    def test_rebalance_brings_the_entered_values_back_to_the_target(self) -> None:
        schedule = build_schedule(self._rebalance(threshold=5))
        assert [(line.action, line.symbol, line.amount) for line in schedule] == [
            ("SELL", "BTC", 200.0),
            ("BUY", "ETH", 200.0),
            ("REVIEW", None, None),
            ("REVIEW", None, None),
        ]

    def test_rebalance_does_nothing_inside_the_threshold(self) -> None:
        schedule = build_schedule(self._rebalance(threshold=25))
        assert [line.action for line in schedule] == ["REVIEW", "REVIEW", "REVIEW"]
        assert actions_from_schedule(schedule) == []

    def test_a_contribution_is_spread_even_inside_the_threshold(self) -> None:
        schedule = build_schedule(self._rebalance(threshold=25, contribution=100))
        assert [(line.action, line.symbol, line.amount) for line in schedule[:2]] == [
            ("SELL", "BTC", 150.0),
            ("BUY", "ETH", 250.0),
        ]

    def test_actions_carry_the_schedule_date_and_rule_note(self) -> None:
        actions = actions_from_schedule(build_schedule(_dca(periods=1)))
        assert actions[0] == {
            "action": "BUY",
            "symbol": "BTC",
            "amount": 60.0,
            "currency": "EUR",
            "reason": "Échéance 1/1 : 60,00 € sur BTC (60 % de 100,00 €)",
            "scheduled_at": datetime(2026, 1, 31, tzinfo=UTC),
        }


class TestValidation:
    @pytest.mark.parametrize(
        "raw",
        [
            {"assets": [{"symbol": "BTC", "weight_pct": 60}, {"symbol": "ETH", "weight_pct": 30}]},
            {"assets": [{"symbol": "BTC", "weight_pct": 50}, {"symbol": "btc", "weight_pct": 50}]},
            {"amount_per_period": 0},
            {"periods": 121},
            {"frequency": "daily"},
            {"unexpected": 1},
        ],
    )
    def test_invalid_dca(self, raw) -> None:
        with pytest.raises(ValidationError):
            _dca(**raw)

    def test_tiers_cannot_sell_more_than_the_quantity(self) -> None:
        with pytest.raises(ValidationError):
            _params(
                template="profit_taking",
                symbol="BTC",
                quantity=1,
                tiers=[{"price": 1, "sell_pct": 60}, {"price": 2, "sell_pct": 50}],
            )

    def test_amounts_are_never_defaulted(self) -> None:
        with pytest.raises(ValidationError, match="amount_per_period"):
            _params(
                template="dca",
                assets=[{"symbol": "BTC", "weight_pct": 100}],
                frequency="monthly",
                periods=1,
                start_date="2026-01-01",
            )


class TestRuleSummary:
    def test_describes_the_users_own_parameters(self) -> None:
        assert describe_rule(_dca()) == (
            "Achat périodique : 100,00 € chaque mois, 3 échéances à partir du 31/01/2026, répartis BTC 60 % · ETH 40 %."
        )

    def test_legacy_or_free_params_have_no_summary(self) -> None:
        assert parse_template_params({"type": "vca", "available_liquidity": 3000}) is None
        assert parse_template_params({}) is None
        assert parse_template_params({"template": "dca"}) is None
        assert parse_template_params(_dca().model_dump(mode="json")) == _dca()

    def test_disclaimers(self) -> None:
        assert "pas un conseil en investissement" in SIMULATION_DISCLAIMER
        assert "Simulation" in SIMULATION_DISCLAIMER
        assert "aucune valeur prédictive" in BACKTEST_NOTE
        assert "ne constitue pas un conseil en investissement" in AI_DISCLAIMER


class TestBacktest:
    def test_dca_buys_at_each_close_and_values_at_the_last_one(self) -> None:
        params = _dca(
            assets=[{"symbol": "BTC", "weight_pct": 100}], frequency="weekly", periods=4, start_date=D0.isoformat()
        )
        result = simulate_on_history(params, {"BTC": _series(100, 200)}, D0)
        assert result.available
        assert (result.invested_eur, result.final_value_eur, result.pnl_eur, result.pnl_pct) == (400, 700, 300, 75)
        assert (result.events_planned, result.events_simulated, result.end_date) == (4, 4, D0 + timedelta(days=30))
        assert [t.price for t in result.trades] == [100, 100, 100, 200]
        assert result.note == BACKTEST_NOTE

    @pytest.mark.parametrize(("allow_sell", "expected"), [(False, (300, 0, 600, 300)), (True, (300, 200, 400, 300))])
    def test_vca_invests_the_gap_to_the_target(self, allow_sell, expected) -> None:
        params = _params(
            template="vca",
            symbol="BTC",
            target_increment=100,
            frequency="weekly",
            periods=4,
            start_date=D0.isoformat(),
            allow_sell=allow_sell,
        )
        result = simulate_on_history(params, {"BTC": _series(100, 200)}, D0)
        assert (result.invested_eur, result.withdrawn_eur, result.final_value_eur, result.pnl_eur) == expected

    def test_profit_tiers_sell_at_the_first_close_above_the_threshold(self) -> None:
        params = _params(
            template="profit_taking",
            symbol="BTC",
            quantity=1,
            tiers=[{"price": 150, "sell_pct": 50}, {"price": 300, "sell_pct": 50}],
        )
        result = simulate_on_history(params, {"BTC": _series(100, 200)}, D0)
        assert [(t.date, t.amount) for t in result.trades] == [(D0 + timedelta(days=21), 100.0)]
        assert (result.invested_eur, result.withdrawn_eur, result.final_value_eur, result.pnl_eur) == (
            100,
            100,
            100,
            100,
        )
        assert (result.benchmark_label, result.benchmark_value_eur) == ("Conserver toute la quantité", 200)
        assert (result.events_planned, result.events_simulated) == (2, 1)

    def test_rebalance_compares_with_never_rebalancing(self) -> None:
        params = _params(
            template="rebalance",
            lines=[
                {"symbol": "A", "target_pct": 50, "current_value": 600},
                {"symbol": "B", "target_pct": 50, "current_value": 400},
            ],
            threshold_pct=5,
            frequency="weekly",
            periods=4,
            start_date=D0.isoformat(),
        )
        result = simulate_on_history(params, {"A": _series(100, 100), "B": _series(100, 300)}, D0)
        assert result.invested_eur == 1000
        assert [(t.action, t.symbol, t.amount) for t in result.trades[2:]] == [
            ("BUY", "A", 500.0),
            ("SELL", "B", 500.0),
        ]
        assert (result.final_value_eur, result.benchmark_value_eur, result.pnl_eur) == (2000, 2000, 1000)

    def test_unavailable_without_history_or_with_a_start_after_the_last_close(self) -> None:
        assert simulate_on_history(_dca(), {"BTC": _series(1, 1)}, D0).reason == (
            "Pas d'historique de prix enregistré pour ETH"
        )
        late = simulate_on_history(
            _dca(assets=[{"symbol": "BTC", "weight_pct": 100}]), {"BTC": _series(1, 1)}, D0 + timedelta(days=60)
        )
        assert not late.available and "dernière clôture" in late.reason


class TestIndependenceFromTheUser:
    """Le simulateur ne lit ni positions, ni liquidité, ni signaux, ni scores alpha."""

    FORBIDDEN = (
        "prediction_service",
        "get_strategy_map",
        "alpha_score",
        "available_liquidity",
        "metrics_service",
        "compute_deployment_capacity",
        "get_deployment_capacity",
        "Portfolio",
        "Transaction",
    )

    @pytest.mark.parametrize("module", [templates, backtest, schemas])
    def test_simulator_modules_read_nothing_about_the_user(self, module) -> None:
        source = inspect.getsource(module)
        assert not [token for token in self.FORBIDDEN if token in source]

    def test_the_router_no_longer_generates_suggestions(self) -> None:
        source = inspect.getsource(router)
        for token in (
            "prediction_service",
            "get_strategy_map",
            "alpha_score",
            "ai_strategy_service",
            "get_deployment_capacity",
        ):
            assert token not in source

    def test_pure_functions_take_only_parameters_and_prices(self) -> None:
        assert list(inspect.signature(build_schedule).parameters) == ["params"]
        assert list(inspect.signature(simulate_on_history).parameters) == ["params", "closes", "start"]

    def test_old_generators_are_gone(self) -> None:
        for name in ("suggestions", "builders_buy", "builders_sell", "builders_portfolio", "suggestion_types"):
            with pytest.raises(ModuleNotFoundError):
                __import__(f"app.domains.strategies.{name}")
