"""Golden test: the French 2086 tax form must be computed in EUR.

``compute_tax_2086`` previously read ``tx.price``/``tx.fee`` raw (in the
transaction currency), diverging from the dashboard (``metrics_service`` applies
``conversion_rate``). A USD/USDT-pair cession was therefore reported ~8-9% off and
inconsistent with the displayed P&L — a tax-compliance bug.

Convention (same as the FIFO cost-basis engine):
    amount (EUR) = qty * price_in_tx_ccy * conversion_rate
where ``conversion_rate`` = EUR per 1 unit of the trade currency (≈0.92 for USD).
"""

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.models.asset import Asset, AssetType
from app.models.portfolio import Portfolio
from app.models.transaction import Transaction, TransactionType
from app.services.report_service import ReportService


async def _portfolio(db_session, user):
    p = Portfolio(user_id=user.id, name="Tax")
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p)
    return p


async def _asset(db_session, portfolio, symbol="BTC"):
    a = Asset(
        portfolio_id=portfolio.id,
        symbol=symbol,
        asset_type=AssetType.CRYPTO,
        quantity=Decimal("1"),
        avg_buy_price=Decimal("0"),
        current_price=Decimal("0"),
        exchange="binance",
    )
    db_session.add(a)
    await db_session.commit()
    await db_session.refresh(a)
    return a


def _tx(asset, ttype, *, qty, price, rate, currency, when, ext):
    return Transaction(
        asset_id=asset.id,
        transaction_type=ttype,
        quantity=Decimal(str(qty)),
        price=Decimal(str(price)),
        fee=Decimal("0"),
        currency=currency,
        conversion_rate=Decimal(str(rate)) if rate is not None else None,
        executed_at=when,
        exchange="binance",
        external_id=ext,
    )


@pytest.mark.asyncio
async def test_usd_cession_converted_to_eur(db_session, regular_user):
    """1 BTC sold at 60000 USD (rate 0.92) -> cession 55200 EUR on the 2086, not 60000."""
    p = await _portfolio(db_session, regular_user)
    btc = await _asset(db_session, p)
    db_session.add(
        _tx(
            btc,
            TransactionType.BUY,
            qty=2,
            price=50000,
            rate="0.90",
            currency="USD",
            when=datetime(2026, 1, 15, tzinfo=timezone.utc),
            ext="b1",
        )
    )
    db_session.add(
        _tx(
            btc,
            TransactionType.SELL,
            qty=1,
            price=60000,
            rate="0.92",
            currency="USD",
            when=datetime(2026, 6, 15, tzinfo=timezone.utc),
            ext="s1",
        )
    )
    await db_session.commit()

    summary = await ReportService().compute_tax_2086(db_session, str(regular_user.id), 2026)

    assert len(summary.events) == 1
    assert summary.events[0].cession_price == pytest.approx(55200.0, abs=0.5)
    assert summary.total_cessions == pytest.approx(55200.0, abs=0.5)


@pytest.mark.asyncio
async def test_eur_cession_unchanged(db_session, regular_user):
    """EUR cession (conversion_rate None -> fx=1) is untouched. No regression."""
    p = await _portfolio(db_session, regular_user)
    btc = await _asset(db_session, p)
    db_session.add(
        _tx(
            btc,
            TransactionType.BUY,
            qty=2,
            price=48000,
            rate=None,
            currency="EUR",
            when=datetime(2026, 1, 15, tzinfo=timezone.utc),
            ext="b1",
        )
    )
    db_session.add(
        _tx(
            btc,
            TransactionType.SELL,
            qty=1,
            price=55000,
            rate=None,
            currency="EUR",
            when=datetime(2026, 6, 15, tzinfo=timezone.utc),
            ext="s1",
        )
    )
    await db_session.commit()

    summary = await ReportService().compute_tax_2086(db_session, str(regular_user.id), 2026)

    assert len(summary.events) == 1
    assert summary.events[0].cession_price == pytest.approx(55000.0, abs=0.5)
