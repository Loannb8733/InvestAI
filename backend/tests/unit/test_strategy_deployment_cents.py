"""Les montants en euros de la capacité de déploiement sont arrondis au centime, sans signal d'achat.

La capacité dérive d'agrégats flottants du dashboard, qui portent des artefacts binaires (1234.5600000000001) ;
la réponse les arrondit au centime. Elle ne propose plus d'ordre : le « prochain signal Alpha » a été retiré
(l'application ne rend pas de conseil en investissement personnalisé).
"""

from unittest.mock import AsyncMock, patch

import pytest

from app.domains.strategies.service import StrategyService


@pytest.mark.asyncio
async def test_deployment_euro_amounts_are_cent_quantized_and_carry_no_buy_signal():
    svc = StrategyService()
    dashboard = {
        "available_liquidity": 1000 / 3,  # 333.3333333333...
        "total_value": 2000 / 3,  # 666.6666666666...
    }

    with patch(
        "app.domains.dashboard.metrics.service.metrics_service.get_user_dashboard_metrics",
        new=AsyncMock(return_value=dashboard),
    ):
        cap = await svc.get_deployment_capacity(db=None, user_id="u1", monthly_dca=1000 / 3)

    for field in (cap.available_liquidity, cap.total_value, cap.deploy_to_risk, cap.keep_in_reserve):
        assert round(field, 2) == field, f"{field!r} is not cent-clean"
    assert cap.next_signal_symbol is None
    assert cap.next_signal_action is None
    assert cap.next_signal_amount == 0.0
    assert cap.can_execute is True
    assert cap.message is None
