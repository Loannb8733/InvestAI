"""Plus-values crypto 2086 : méthode du portefeuille (art. 150 VH bis CGI), cas calculés à la main.

Règles (BOFiP BOI-RPPM-PVBMC-30-20, notice 2086 n° 16043*07) :

* PV = prix de cession net de frais (l. 218) − PTA net (l. 223) × prix de cession hors frais (l. 217)
  / valeur globale du portefeuille (l. 212) ; les frais n'entrent pas dans le quotient (§ 50).
* V comprend les actifs cédés : c'est la valeur du portefeuille **avant** la cession (§ 140).
* Après chaque cession, le PTA est diminué de la fraction de capital initial PTA net × C / V (§ 100-110),
  y compris pour les cessions des années précédentes et des années exonérées ; les achats ultérieurs s'ajoutent.
* Les échanges crypto → crypto sans soulte, stablecoins compris, sont en sursis (BOI-RPPM-PVBMC-30-10 § 80).
* Exonération si la somme des prix de cession de l'année (l. 51 = Σ l. 218) n'excède pas 305 € (§ 90-110).
* Les moins-values ne s'imputent que sur les plus-values de la même année (§ 160-170).
* PFU : 12,8 % + 17,2 % = 30 % jusqu'aux revenus 2024, 12,8 % + 18,6 % = 31,4 % dès les revenus 2025 (LFSS 2026).

Tous les montants sont en EUR, transactions saisies en EUR (conversion_rate absent).
"""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from app.domains.market_data.history.models import AssetPriceHistory
from app.domains.portfolio.models import Asset, AssetType, Portfolio
from app.domains.reports.service import ReportService
from app.domains.transactions.models import Transaction, TransactionType

TxType = TransactionType
EUR = 0.005


async def _portefeuille(db_session, user, *symboles, exchange="binance"):
    portfolio = Portfolio(user_id=user.id, name="2086")
    db_session.add(portfolio)
    await db_session.commit()
    await db_session.refresh(portfolio)
    actifs = {}
    for symbole in symboles:
        actif = Asset(
            portfolio_id=portfolio.id,
            symbol=symbole,
            asset_type=AssetType.CRYPTO,
            quantity=Decimal("0"),
            avg_buy_price=Decimal("0"),
            current_price=Decimal("0"),
            exchange=exchange,
        )
        db_session.add(actif)
        actifs[symbole] = actif
    await db_session.commit()
    for actif in actifs.values():
        await db_session.refresh(actif)
    return actifs


def _tx(actif, nature, quantite, prix, quand, *, frais=0, ref=None, notes=None):
    return Transaction(
        asset_id=actif.id,
        transaction_type=nature,
        quantity=Decimal(str(quantite)),
        price=Decimal(str(prix)),
        fee=Decimal(str(frais)),
        currency="EUR",
        executed_at=quand,
        exchange=actif.exchange,
        external_id=ref,
        notes=notes,
    )


def _cours(symbole, jour, prix):
    return AssetPriceHistory(symbol=symbole, price_date=jour, price_eur=Decimal(str(prix)), source="test")


def _le(a, m, j):
    return datetime(a, m, j, 10, 0, tzinfo=UTC)


async def _synthese(db_session, user, annee):
    return await ReportService().compute_tax_2086(db_session, str(user.id), annee)


class TestExempleOfficielBofip:
    """BOFiP 30-20 § 110 et notice 2086 p. 7 : achat 1 000 €, cession 450 € (V 1 200), puis solde (V 1 300)."""

    async def _seed(self, db_session, user, annee_solde):
        x = (await _portefeuille(db_session, user, "XXX"))["XXX"]
        db_session.add(_tx(x, TxType.BUY, 10, 100, _le(2025, 1, 10), ref="a"))
        db_session.add(_tx(x, TxType.SELL, "3.75", 120, _le(2025, 3, 10), ref="c1"))
        db_session.add(_tx(x, TxType.SELL, "6.25", 208, _le(annee_solde, 8, 10), ref="c2"))
        await db_session.commit()

    async def test_deux_cessions_la_meme_annee(self, db_session, regular_user):
        await self._seed(db_session, regular_user, 2025)

        s = await _synthese(db_session, regular_user, 2025)

        c1, c2 = s.events
        assert c1.portfolio_value == pytest.approx(1200, abs=EUR)
        assert c1.total_acquisition_cost == pytest.approx(1000, abs=EUR)
        assert c1.acquisition_fraction == pytest.approx(375, abs=EUR)
        assert c1.gain_loss == pytest.approx(75, abs=EUR)
        assert c2.portfolio_value == pytest.approx(1300, abs=EUR)
        assert c2.total_acquisition_cost == pytest.approx(625, abs=EUR)
        assert c2.acquisition_fraction == pytest.approx(625, abs=EUR)
        assert c2.gain_loss == pytest.approx(675, abs=EUR)
        assert s.total_cessions == pytest.approx(1750, abs=EUR)
        assert s.net_plus_value == pytest.approx(750, abs=EUR)

    async def test_la_fraction_d_une_annee_anterieure_reduit_le_pta(self, db_session, regular_user):
        await self._seed(db_session, regular_user, 2026)

        s2026 = await _synthese(db_session, regular_user, 2026)

        assert s2026.nb_cessions == 1
        c2 = s2026.events[0]
        assert c2.total_acquisition_cost == pytest.approx(625, abs=EUR)
        assert c2.gain_loss == pytest.approx(675, abs=EUR)
        assert s2026.pfu_total == pytest.approx(675 * 0.314, abs=EUR)


class TestExempleTroisCessions:
    """Exemple C de la note de règles : frais, achat intercalé, moins-value, deux actifs.

    AAA est cédé ; BBB est seulement détenu, valorisé par l'historique de cours du jour de cession.
    """

    async def _seed(self, db_session, user):
        actifs = await _portefeuille(db_session, user, "AAA", "BBB")
        a, b = actifs["AAA"], actifs["BBB"]
        db_session.add_all(
            [
                _tx(a, TxType.BUY, 40, 100, _le(2025, 1, 10), ref="a1"),
                _tx(b, TxType.BUY, 20, 100, _le(2025, 2, 15), ref="a2"),
                _tx(a, TxType.SELL, 10, 150, _le(2025, 4, 10), frais=15, ref="c1"),
                _tx(b, TxType.BUY, 20, 50, _le(2025, 6, 1), ref="a3"),
                _tx(a, TxType.SELL, 20, 100, _le(2025, 9, 1), frais=20, ref="c2"),
                _tx(a, TxType.SELL, 10, 300, _le(2025, 12, 1), frais=30, ref="c3"),
                _cours("BBB", date(2025, 4, 10), 75),
                _cours("BBB", date(2025, 9, 1), 50),
                _cours("BBB", date(2025, 12, 1), 75),
            ]
        )
        await db_session.commit()

    async def test_chaque_cession(self, db_session, regular_user):
        await self._seed(db_session, regular_user)

        c1, c2, c3 = (await _synthese(db_session, regular_user, 2025)).events

        assert c1.portfolio_value == pytest.approx(7500, abs=EUR)
        assert c1.cession_price == pytest.approx(1485, abs=EUR)
        assert c1.total_acquisition_cost == pytest.approx(6000, abs=EUR)
        assert c1.acquisition_fraction == pytest.approx(1200, abs=EUR), "frais hors du quotient : pas 1 188"
        assert c1.gain_loss == pytest.approx(285, abs=EUR)
        assert c2.portfolio_value == pytest.approx(5000, abs=EUR)
        assert c2.total_acquisition_cost == pytest.approx(5800, abs=EUR)
        assert c2.acquisition_fraction == pytest.approx(2320, abs=EUR)
        assert c2.gain_loss == pytest.approx(-340, abs=EUR)
        assert c3.portfolio_value == pytest.approx(6000, abs=EUR)
        assert c3.total_acquisition_cost == pytest.approx(3480, abs=EUR)
        assert c3.acquisition_fraction == pytest.approx(1740, abs=EUR)
        assert c3.gain_loss == pytest.approx(1230, abs=EUR)

    async def test_lignes_du_formulaire(self, db_session, regular_user):
        await self._seed(db_session, regular_user)

        c1, c2, c3 = (await _synthese(db_session, regular_user, 2025)).events

        assert (c1.gross_cession_price, c1.fees) == pytest.approx((1500, 15), abs=EUR)
        assert (c1.acquisition_cost_gross, c1.prior_fractions) == pytest.approx((6000, 0), abs=EUR)
        assert (c2.acquisition_cost_gross, c2.prior_fractions) == pytest.approx((7000, 1200), abs=EUR)
        assert (c3.acquisition_cost_gross, c3.prior_fractions) == pytest.approx((7000, 3520), abs=EUR)

    async def test_recapitulatif_et_pfu_2025(self, db_session, regular_user):
        await self._seed(db_session, regular_user)

        s = await _synthese(db_session, regular_user, 2025)

        assert s.total_cessions == pytest.approx(6435, abs=EUR)
        assert s.total_plus_values == pytest.approx(1515, abs=EUR)
        assert s.total_moins_values == pytest.approx(-340, abs=EUR)
        assert s.net_plus_value == pytest.approx(1175, abs=EUR)
        assert s.exempt is False
        assert s.pfu_ir == pytest.approx(150.40, abs=EUR)
        assert s.pfu_ps == pytest.approx(218.55, abs=EUR)
        assert s.pfu_total == pytest.approx(368.95, abs=EUR)


class TestSursisDesEchanges:
    async def test_une_conversion_crypto_crypto_n_est_pas_une_cession(self, db_session, regular_user):
        """1 BTC acheté 1 000 € converti en 10 ETH, puis 5 ETH vendus 1 500 € (V = 3 000)."""
        actifs = await _portefeuille(db_session, regular_user, "BTC", "ETH", exchange="kraken")
        btc, eth = actifs["BTC"], actifs["ETH"]
        db_session.add_all(
            [
                _tx(btc, TxType.BUY, 1, 1000, _le(2025, 1, 10), ref="b"),
                _tx(btc, TxType.CONVERSION_OUT, 1, 2000, _le(2025, 3, 1), ref="convert_sell_K1"),
                _tx(eth, TxType.CONVERSION_IN, 10, 200, _le(2025, 3, 1), ref="convert_buy_K1"),
                _tx(eth, TxType.SELL, 5, 300, _le(2025, 6, 1), ref="v"),
            ]
        )
        await db_session.commit()

        s = await _synthese(db_session, regular_user, 2025)

        assert s.nb_cessions == 1
        (vente,) = s.events
        assert vente.symbol == "ETH"
        assert vente.portfolio_value == pytest.approx(3000, abs=EUR)
        assert vente.total_acquisition_cost == pytest.approx(1000, abs=EUR)
        assert vente.gain_loss == pytest.approx(1000, abs=EUR)

    async def test_une_conversion_vers_un_stablecoin_est_en_sursis(self, db_session, regular_user):
        """BTC → USDC sans soulte : pas de cession ; la vente des USDC contre euros en est une."""
        actifs = await _portefeuille(db_session, regular_user, "BTC", "USDC")
        btc, usdc = actifs["BTC"], actifs["USDC"]
        db_session.add_all(
            [
                _tx(btc, TxType.BUY, 1, 1000, _le(2025, 1, 10), ref="b"),
                _tx(btc, TxType.CONVERSION_OUT, 1, 2000, _le(2025, 3, 1), ref="convert_sell_B1"),
                _tx(usdc, TxType.CONVERSION_IN, 2000, 1, _le(2025, 3, 1), ref="convert_buy_B1"),
                _tx(usdc, TxType.SELL, 2000, 1, _le(2025, 4, 1), ref="v"),
            ]
        )
        await db_session.commit()

        s = await _synthese(db_session, regular_user, 2025)

        assert [e.symbol for e in s.events] == ["USDC"]
        assert s.events[0].gain_loss == pytest.approx(1000, abs=EUR)

    async def test_une_conversion_sans_destination_reste_en_sursis(self, db_session, regular_user):
        btc = (await _portefeuille(db_session, regular_user, "BTC", exchange="kraken"))["BTC"]
        db_session.add(_tx(btc, TxType.BUY, 1, 1000, _le(2025, 1, 10), ref="b"))
        db_session.add(_tx(btc, TxType.CONVERSION_OUT, 1, 2000, _le(2025, 3, 1), ref="convert_sell_ORPHAN"))
        await db_session.commit()

        s = await _synthese(db_session, regular_user, 2025)

        assert s.nb_cessions == 0
        assert s.total_cessions == 0


class TestSeuilDe305Euros:
    async def test_trois_cessions_de_100_euros_sont_exonerees(self, db_session, regular_user):
        """BOFiP 30-10 § 100 : la PV existe (3 × 90 €) mais le total des prix (300 €) n'excède pas 305 €."""
        x = (await _portefeuille(db_session, regular_user, "XXX"))["XXX"]
        db_session.add(_tx(x, TxType.BUY, 10, 10, _le(2025, 1, 10), ref="a"))
        for i, mois in enumerate((3, 4, 5)):
            db_session.add(_tx(x, TxType.SELL, 1, 100, _le(2025, mois, 1), ref=f"c{i}"))
        await db_session.commit()

        s = await _synthese(db_session, regular_user, 2025)

        assert [e.gain_loss for e in s.events] == pytest.approx([90, 90, 90], abs=EUR)
        assert s.total_cessions == pytest.approx(300, abs=EUR)
        assert s.net_plus_value == pytest.approx(270, abs=EUR)
        assert s.exempt is True
        assert (s.pfu_ir, s.pfu_ps, s.pfu_total) == (0, 0, 0)

    @pytest.mark.parametrize(("frais", "exonere"), [("5", True), ("4.99", False)])
    async def test_le_seuil_porte_sur_les_prix_nets_de_frais_et_305_est_inclus(
        self, db_session, regular_user, frais, exonere
    ):
        x = (await _portefeuille(db_session, regular_user, "XXX"))["XXX"]
        db_session.add(_tx(x, TxType.BUY, 10, 10, _le(2025, 1, 10), ref="a"))
        db_session.add(_tx(x, TxType.SELL, 1, 310, _le(2025, 3, 1), frais=frais, ref="c"))
        await db_session.commit()

        s = await _synthese(db_session, regular_user, 2025)

        assert s.exempt is exonere
        assert (s.pfu_total > 0) is not exonere

    async def test_une_annee_exoneree_reduit_quand_meme_le_pta(self, db_session, regular_user):
        """2025 : 1 X cédé 200 € (V 2 000, fraction 100, exonéré). 2026 : 9 X cédés 1 800 € sur un PTA net de 900."""
        x = (await _portefeuille(db_session, regular_user, "XXX"))["XXX"]
        db_session.add(_tx(x, TxType.BUY, 10, 100, _le(2025, 1, 10), ref="a"))
        db_session.add(_tx(x, TxType.SELL, 1, 200, _le(2025, 3, 1), ref="c1"))
        db_session.add(_tx(x, TxType.SELL, 9, 200, _le(2026, 3, 1), ref="c2"))
        await db_session.commit()

        s2025 = await _synthese(db_session, regular_user, 2025)
        s2026 = await _synthese(db_session, regular_user, 2026)

        assert s2025.exempt is True
        assert s2025.events[0].acquisition_fraction == pytest.approx(100, abs=EUR)
        assert s2026.events[0].total_acquisition_cost == pytest.approx(900, abs=EUR)
        assert s2026.net_plus_value == pytest.approx(900, abs=EUR)
        assert s2026.pfu_total == pytest.approx(282.60, abs=EUR)


class TestMoinsValuesEtTaux:
    async def test_une_moins_value_ne_se_reporte_pas_sur_l_annee_suivante(self, db_session, regular_user):
        """2025 : MV de −400 ; 2026 : PV de 400 entièrement imposable."""
        x = (await _portefeuille(db_session, regular_user, "XXX"))["XXX"]
        db_session.add(_tx(x, TxType.BUY, 10, 100, _le(2025, 1, 10), ref="a"))
        db_session.add(_tx(x, TxType.SELL, 5, 20, _le(2025, 3, 1), ref="c1"))
        db_session.add(_tx(x, TxType.SELL, 5, 180, _le(2026, 3, 1), ref="c2"))
        await db_session.commit()

        s2025 = await _synthese(db_session, regular_user, 2025)
        s2026 = await _synthese(db_session, regular_user, 2026)

        assert s2025.net_plus_value == pytest.approx(-400, abs=EUR)
        assert s2025.pfu_total == 0
        assert s2026.net_plus_value == pytest.approx(400, abs=EUR)
        assert s2026.pfu_total == pytest.approx(400 * 0.314, abs=EUR)

    @pytest.mark.parametrize(
        ("annee", "ir", "ps", "total"),
        [(2024, 0.128, 0.172, 0.30), (2025, 0.128, 0.186, 0.314), (2026, 0.128, 0.186, 0.314)],
    )
    async def test_le_pfu_suit_l_annee_d_imposition(self, db_session, regular_user, annee, ir, ps, total):
        x = (await _portefeuille(db_session, regular_user, "XXX"))["XXX"]
        db_session.add(_tx(x, TxType.BUY, 10, 100, _le(annee, 1, 10), ref="a"))
        db_session.add(_tx(x, TxType.SELL, 10, 200, _le(annee, 6, 1), ref="c"))
        await db_session.commit()

        s = await _synthese(db_session, regular_user, annee)

        assert s.net_plus_value == pytest.approx(1000, abs=EUR)
        assert s.pfu_ir == pytest.approx(1000 * ir, abs=EUR)
        assert s.pfu_ps == pytest.approx(1000 * ps, abs=EUR)
        assert s.pfu_total == pytest.approx(1000 * total, abs=EUR)
