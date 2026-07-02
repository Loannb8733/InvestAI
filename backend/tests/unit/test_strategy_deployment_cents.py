"""Advisory euro amounts must be clean to the cent.

The deployment-capacity guidance derives from float dashboard aggregates. Those
carry binary-float artefacts (e.g. 1234.5600000000001); the advisory response must
round them to cents so the UI never shows a 12-decimal euro amount. This is the
right fix here — the projection/Monte-Carlo services legitimately stay in float.
"""

from unittest.mock import AsyncMock, patch

import pytest

from app.services.strategy_service import StrategyService


@pytest.mark.asyncio
async def test_deployment_euro_amounts_are_cent_quantized():
    svc = StrategyService()

    dashboard = {
        "available_liquidity": 1000 / 3,  # 333.3333333333...
        "total_value": 2000 / 3,  # 666.6666666666...
    }
    strategy = {"assets": [{"symbol": "BTC", "action": "ACHAT", "impact_eur": 100 / 3}]}

    with (
        patch(
            "app.services.metrics_service.metrics_service.get_user_dashboard_metrics",
            new=AsyncMock(return_value=dashboard),
        ),
        patch(
            "app.services.prediction_service.prediction_service.get_strategy_map",
            new=AsyncMock(return_value=strategy),
        ),
    ):
        cap = await svc.get_deployment_capacity(db=None, user_id="u1", monthly_dca=300.0)

    for field in (cap.available_liquidity, cap.total_value, cap.next_signal_amount, cap.shortfall):
        assert round(field, 2) == field, f"{field!r} is not cent-clean"
    assert cap.next_signal_amount == 33.33
