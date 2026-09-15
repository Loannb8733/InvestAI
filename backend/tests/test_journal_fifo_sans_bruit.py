"""Les dumps FIFO du BTC ne sortent plus en WARNING à chaque recalcul.

Le diagnostic posé pour l'issue #228 (couches BTC finales, entrées et sorties
par actif) était journalisé en WARNING : à chaque tableau de bord recalculé,
dix lignes dont une de 4 Ko (54 couches Tangem) — journaux Render du
2026-09-15. Un avertissement qui tombe toutes les deux minutes n'alerte plus
personne et noie les vrais. Le diagnostic reste disponible en DEBUG (NEW-91).
"""

import logging

import pytest

from app.models.transaction import TransactionType as TxType
from tests.test_fifo_replay_characterization import _dt, _make_asset, _make_portfolio, _metrics, _tx

_JOURNAL = "app.services.metrics_service"


async def _portefeuille_btc(db_session, regular_user):
    portfolio = await _make_portfolio(db_session, regular_user, name="Journal")
    btc = await _make_asset(db_session, portfolio, symbol="BTC", qty=1, current_price=40000)
    db_session.add(_tx(btc, TxType.BUY, qty=1, price=30000, when=_dt(2025, 6, 1), ext="j1"))
    await db_session.commit()
    return portfolio


def _dumps(caplog, niveau_min):
    return [
        r for r in caplog.records if r.name == _JOURNAL and r.levelno >= niveau_min and "[FIFO_DEBUG]" in r.getMessage()
    ]


@pytest.mark.asyncio
async def test_aucun_dump_fifo_en_warning(db_session, regular_user, caplog):
    portfolio = await _portefeuille_btc(db_session, regular_user)
    caplog.set_level(logging.DEBUG, logger=_JOURNAL)

    await _metrics(db_session, portfolio, {"BTC": 40000.0})

    assert _dumps(caplog, logging.WARNING) == []


@pytest.mark.asyncio
async def test_le_diagnostic_reste_disponible_en_debug(db_session, regular_user, caplog):
    portfolio = await _portefeuille_btc(db_session, regular_user)
    caplog.set_level(logging.DEBUG, logger=_JOURNAL)

    await _metrics(db_session, portfolio, {"BTC": 40000.0})

    messages = [r.getMessage() for r in _dumps(caplog, logging.DEBUG)]
    assert any("BTC final" in m for m in messages)
    assert any("metrics_output" in m for m in messages)
