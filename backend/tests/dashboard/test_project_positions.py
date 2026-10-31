"""Un bien valorisé à son montant investi peut être le premier actif d'un portefeuille."""

from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.dashboard.metrics.service import metrics_service
from app.domains.identity.models import User
from app.domains.portfolio.models import Asset, AssetType, Portfolio


@pytest.mark.usefixtures("empty_test_redis", "offline")
async def test_real_estate_first_in_portfolio_is_valued_at_its_invested_amount(
    db_session: AsyncSession, regular_user: User
) -> None:
    portfolio = Portfolio(user_id=regular_user.id, name="Immobilier")
    db_session.add(portfolio)
    await db_session.flush()
    db_session.add(
        Asset(
            portfolio_id=portfolio.id,
            symbol="APPART",
            name="Appartement",
            asset_type=AssetType.REAL_ESTATE,
            quantity=Decimal("1"),
            avg_buy_price=Decimal("0"),
            invested_amount=Decimal("150000"),
            project_status="active",
        )
    )
    await db_session.commit()

    metrics = await metrics_service.get_portfolio_metrics(db_session, str(portfolio.id))

    assert metrics["total_value"] == 150000.0
    assert metrics["assets"][0]["breakeven_price"] == 150000.0
    assert metrics["crowdfunding_summary"]["active_projects"] == 1
