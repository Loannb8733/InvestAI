from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.domains.analytics.service import AnalyticsService
from app.domains.portfolio.models import Asset, AssetType

BTC_SERIES = [100.0 + (i % 3) for i in range(29)] + [100.0]
ETH_SERIES = [50.0 + (i % 2) for i in range(29)] + [50.0]
SHORT_SERIES = [10.0, 11.0, 10.0]


def _asset(symbol: str, quantity: str, avg_buy_price: str, current_price: str | None = None) -> Asset:
    return Asset(
        symbol=symbol,
        asset_type=AssetType.CRYPTO,
        quantity=Decimal(quantity),
        avg_buy_price=Decimal(avg_buy_price),
        current_price=Decimal(current_price) if current_price is not None else None,
    )


def _service(assets: list[Asset], series: dict[str, list[float]]) -> AnalyticsService:
    service = AnalyticsService()
    service._get_user_assets = AsyncMock(return_value=assets)  # type: ignore[method-assign]
    service._history_prices = AsyncMock(  # type: ignore[method-assign]
        side_effect=lambda symbol, days: series.get(symbol, [])
    )
    return service


async def _simulation_args(service: AnalyticsService, **kwargs: object) -> tuple[list[float], float]:
    with patch("app.domains.analytics.monte_carlo.simulate_monte_carlo") as simulate:
        await service.monte_carlo(MagicMock(), "user", **kwargs)  # type: ignore[arg-type]
    args = simulate.call_args.args
    return [float(x) for x in args[2]], float(args[10])


async def test_asset_without_history_is_valued_at_last_known_price() -> None:
    service = _service([_asset("NOHIST", "2", "100", "200")], {})
    [entry] = await service._build_asset_data(await service._get_user_assets(MagicMock(), "user"))
    assert entry["price"] == 200.0
    assert entry["current_value"] == 400.0
    assert entry["gain_loss"] == 200.0


async def test_asset_without_quote_is_valued_at_last_known_price() -> None:
    service = AnalyticsService()
    with patch("app.domains.analytics.core.price_feed.quote", AsyncMock(return_value=None)):
        assert await service._get_asset_price(_asset("NOQUOTE", "1", "100", "200")) == 200.0


async def test_price_falls_back_to_cost_when_no_price_is_known() -> None:
    service = _service([_asset("NOHIST", "2", "100")], {})
    [entry] = await service._build_asset_data(await service._get_user_assets(MagicMock(), "user"))
    assert entry["current_value"] == 200.0


async def test_reward_asset_bought_at_zero_is_not_dust() -> None:
    reward = _asset("REWARD", "5", "0", "20")
    result = MagicMock()
    result.scalars.return_value.all.return_value = [reward]
    db = MagicMock()
    db.execute = AsyncMock(return_value=result)
    assert await AnalyticsService()._get_user_assets(db, "user", portfolio_id="p") == [reward]


async def test_monte_carlo_values_asset_without_history_at_last_known_price() -> None:
    service = _service([_asset("BTC", "2", "80", "100"), _asset("NOHIST", "3", "5", "20")], {"BTC": BTC_SERIES})
    _, total_value = await _simulation_args(service)
    assert total_value == pytest.approx(260.0)


async def test_beta_values_asset_without_history_at_last_known_price() -> None:
    service = _service([_asset("NOHIST", "3", "5", "20")], {})
    result = await service.compute_beta(MagicMock(), "user")
    assert [a["value"] for a in result["assets"]] == [60.0]


async def test_contribution_goes_to_its_asset_when_an_earlier_symbol_is_not_simulated() -> None:
    assets = [_asset("SHORT", "1", "10", "10"), _asset("BTC", "2", "100", "100"), _asset("ETH", "4", "50", "50")]
    service = _service(assets, {"SHORT": SHORT_SERIES, "BTC": BTC_SERIES, "ETH": ETH_SERIES})
    weights, total_value = await _simulation_args(service, contribution={"BTC": 200.0})
    assert weights == pytest.approx([2 / 3, 1 / 3])
    assert total_value == pytest.approx(610.0)


async def test_contribution_to_last_symbol_does_not_crash_when_an_earlier_one_is_skipped() -> None:
    assets = [_asset("SHORT", "1", "10", "10"), _asset("BTC", "2", "100", "100"), _asset("ETH", "4", "50", "50")]
    service = _service(assets, {"SHORT": SHORT_SERIES, "BTC": BTC_SERIES, "ETH": ETH_SERIES})
    weights, _ = await _simulation_args(service, contribution={"ETH": 200.0})
    assert weights == pytest.approx([1 / 3, 2 / 3])
