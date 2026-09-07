"""Filet de caractérisation des frais payés et des revenus passifs.

Deux méthodes d'`insights_service` que l'utilisateur consulte pour savoir ce
que lui coûte sa gestion et ce qu'elle lui rapporte. Le module était couvert à
31 % après le filet sur l'optimisation fiscale.

Elles lisent la base : le filet s'appuie sur la fixture `db_session` du projet.

Comportement actuel épinglé, pas spécification approuvée — et deux écarts
mesurés y sont nommés sans être corrigés.
"""

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.models.asset import Asset, AssetType
from app.models.portfolio import Portfolio
from app.models.transaction import Transaction, TransactionType
from app.services.insights_service import InsightsService


@pytest.fixture
def service():
    return InsightsService()


async def portefeuille(db_session, user, nom="Test") -> Portfolio:
    pf = Portfolio(user_id=user.id, name=nom)
    db_session.add(pf)
    await db_session.flush()
    return pf


async def actif(db_session, pf, symbole="BTC") -> Asset:
    a = Asset(
        portfolio_id=pf.id,
        symbol=symbole,
        name=symbole,
        asset_type=AssetType.CRYPTO,
        quantity=Decimal("1"),
        avg_buy_price=Decimal("40000"),
    )
    db_session.add(a)
    await db_session.flush()
    return a


def mouvement(
    asset,
    *,
    type_tx=TransactionType.BUY,
    quantite="1",
    prix="40000",
    frais="0",
    devise_frais="EUR",
    quand="2026-03-15",
    exchange="Binance",
):
    return Transaction(
        asset_id=asset.id,
        transaction_type=type_tx,
        quantity=Decimal(quantite),
        price=Decimal(prix),
        fee=Decimal(frais),
        fee_currency=devise_frais,
        exchange=exchange,
        executed_at=datetime.fromisoformat(quand).replace(tzinfo=timezone.utc),
    )


class TestAnalyseDesFrais:
    async def test_sans_portefeuille_le_resultat_est_vide(self, db_session, regular_user, service):
        res = await service.get_fee_analysis(db_session, str(regular_user.id))

        assert res["total_fees"] == 0
        assert res["by_exchange"] == {}

    async def test_un_portefeuille_sans_actif_rend_le_meme_vide(self, db_session, regular_user, service):
        await portefeuille(db_session, regular_user)
        await db_session.commit()

        res = await service.get_fee_analysis(db_session, str(regular_user.id))

        assert res["total_fees"] == 0

    async def test_les_frais_sont_ventiles_par_plateforme_actif_type_et_mois(self, db_session, regular_user, service):
        pf = await portefeuille(db_session, regular_user)
        btc = await actif(db_session, pf, "BTC")
        db_session.add(mouvement(btc, frais="10", quand="2026-01-10"))
        db_session.add(mouvement(btc, frais="5", quand="2026-02-10", exchange="Kraken"))
        await db_session.commit()

        res = await service.get_fee_analysis(db_session, str(regular_user.id))

        assert res["total_fees"] == 15.0
        assert res["nb_transactions_with_fees"] == 2
        assert res["by_exchange"] == {"Binance": 10.0, "Kraken": 5.0}
        assert res["by_asset"] == {"BTC": 15.0}
        assert res["by_month"] == {"2026-01": 10.0, "2026-02": 5.0}

    async def test_une_transaction_sans_frais_est_ignoree(self, db_session, regular_user, service):
        pf = await portefeuille(db_session, regular_user)
        btc = await actif(db_session, pf)
        db_session.add(mouvement(btc, frais="0"))
        await db_session.commit()

        res = await service.get_fee_analysis(db_session, str(regular_user.id))

        assert res["nb_transactions_with_fees"] == 0

    async def test_une_plateforme_absente_devient_inconnu(self, db_session, regular_user, service):
        pf = await portefeuille(db_session, regular_user)
        btc = await actif(db_session, pf)
        db_session.add(mouvement(btc, frais="3", exchange=""))
        await db_session.commit()

        res = await service.get_fee_analysis(db_session, str(regular_user.id))

        assert res["by_exchange"] == {"Inconnu": 3.0}

    async def test_les_ventilations_sont_triees_par_montant_decroissant(self, db_session, regular_user, service):
        pf = await portefeuille(db_session, regular_user)
        btc = await actif(db_session, pf, "BTC")
        eth = await actif(db_session, pf, "ETH")
        db_session.add(mouvement(btc, frais="2", exchange="A"))
        db_session.add(mouvement(eth, frais="9", exchange="B"))
        await db_session.commit()

        res = await service.get_fee_analysis(db_session, str(regular_user.id))

        assert list(res["by_exchange"]) == ["B", "A"]
        assert list(res["by_asset"]) == ["ETH", "BTC"]

    async def test_la_moyenne_mensuelle_ne_porte_que_sur_les_mois_avec_frais(self, db_session, regular_user, service):
        """`total / len(by_month)` — le dénominateur est le nombre de mois **ayant
        porté des frais**, pas la durée de détention.

        Douze euros payés en janvier et rien les onze mois suivants donnent une
        « moyenne mensuelle » de 12 EUR, non de 1 EUR. Le chiffre répond donc à
        « combien un mois de frais coûte-t-il quand il y en a » et non à
        « combien mes frais me coûtent par mois » — ce que son libellé laisse
        entendre.
        """
        pf = await portefeuille(db_session, regular_user)
        btc = await actif(db_session, pf)
        db_session.add(mouvement(btc, frais="12", quand="2026-01-10"))
        await db_session.commit()

        res = await service.get_fee_analysis(db_session, str(regular_user.id))

        assert res["avg_monthly_fee"] == 12.0

    async def test_les_frais_de_devises_differentes_sont_additionnes_tels_quels(
        self, db_session, regular_user, service
    ):
        """Aucune conversion : 1 EUR + 1 USDC + 0,001 BTC font « 2,001 ».

        `fee_currency` est reporté ligne par ligne dans `recent_fees`, mais le
        total et toutes les ventilations somment les montants bruts. La base de
        développement porte des frais en **sept devises** (EUR, USDC, PAXG, BTC,
        ETH, SOL, TAO) : l'écart y reste faible parce que les montants crypto
        sont minuscules, mais 0,001 BTC compté comme 0,001 EUR au lieu de ~90
        EUR est une sous-estimation de trois ordres de grandeur.

        Épinglé, pas corrigé.
        """
        pf = await portefeuille(db_session, regular_user)
        btc = await actif(db_session, pf)
        db_session.add(mouvement(btc, frais="1", devise_frais="EUR"))
        db_session.add(mouvement(btc, frais="1", devise_frais="USDC"))
        db_session.add(mouvement(btc, frais="0.001", devise_frais="BTC"))
        await db_session.commit()

        res = await service.get_fee_analysis(db_session, str(regular_user.id))

        assert res["total_fees"] == 2.0  # 2,001 arrondi
        assert {f["fee_currency"] for f in res["recent_fees"]} == {"EUR", "USDC", "BTC"}

    async def test_la_ventilation_par_actif_est_tronquee_aux_dix_premiers(self, db_session, regular_user, service):
        # Le total reste complet : la somme des dix lignes affichées ne le
        # retrouve donc pas sur un portefeuille plus large.
        pf = await portefeuille(db_session, regular_user)
        for i in range(12):
            a = await actif(db_session, pf, f"A{i:02d}")
            db_session.add(mouvement(a, frais=str(i + 1)))
        await db_session.commit()

        res = await service.get_fee_analysis(db_session, str(regular_user.id))

        assert len(res["by_asset"]) == 10
        assert res["total_fees"] == 78.0  # 1+2+…+12
        assert sum(res["by_asset"].values()) == 75.0  # les deux plus petites manquent

    async def test_les_frais_recents_sont_limites_a_vingt(self, db_session, regular_user, service):
        pf = await portefeuille(db_session, regular_user)
        btc = await actif(db_session, pf)
        for i in range(25):
            db_session.add(mouvement(btc, frais="1", quand=f"2026-01-{i % 28 + 1:02d}"))
        await db_session.commit()

        res = await service.get_fee_analysis(db_session, str(regular_user.id))

        assert res["nb_transactions_with_fees"] == 25
        assert len(res["recent_fees"]) == 20


class TestRevenusPassifs:
    async def test_sans_portefeuille_le_resultat_est_vide(self, db_session, regular_user, service):
        res = await service.get_passive_income(db_session, str(regular_user.id))

        assert res["total_income"] == 0
        assert res["nb_events"] == 0

    async def test_les_recompenses_de_staking_et_airdrops_sont_comptes(self, db_session, regular_user, service):
        pf = await portefeuille(db_session, regular_user)
        eth = await actif(db_session, pf, "ETH")
        db_session.add(mouvement(eth, type_tx=TransactionType.STAKING_REWARD, quantite="0.1", prix="2000"))
        db_session.add(mouvement(eth, type_tx=TransactionType.AIRDROP, quantite="10", prix="5"))
        await db_session.commit()

        res = await service.get_passive_income(db_session, str(regular_user.id))

        assert res["total_income"] == 250.0  # 200 + 50
        assert res["nb_events"] == 2
        assert res["by_type"] == {"staking_reward": 200.0, "airdrop": 50.0}

    async def test_les_dividendes_et_interets_ne_sont_pas_comptes(self, db_session, regular_user, service):
        """La docstring annonce « dividends, staking rewards, interest ».

        `passive_types` ne contient pourtant que `STAKING_REWARD` et `AIRDROP` :
        un dividende d'action ou un intérêt obligataire n'apparaît nulle part
        dans le suivi des revenus passifs. Les deux types existent, et tout le
        reste du code les traite bien comme des revenus — ils comptent dans les
        entrées du TRI (`analytics_math._XIRR_INFLOW_TYPES`) et créditent les
        quantités à l'import.

        Exposition mesurée : **zéro transaction** de ces deux types en base de
        développement — l'écart est réel mais dormant. Il se réveillerait au
        premier dividende d'action enregistré.
        """
        pf = await portefeuille(db_session, regular_user)
        aapl = await actif(db_session, pf, "AAPL")
        db_session.add(mouvement(aapl, type_tx=TransactionType.DIVIDEND, quantite="1", prix="100"))
        db_session.add(mouvement(aapl, type_tx=TransactionType.INTEREST, quantite="1", prix="50"))
        await db_session.commit()

        res = await service.get_passive_income(db_session, str(regular_user.id))

        assert res["total_income"] == 0
        assert res["nb_events"] == 0

    async def test_un_revenu_sans_prix_est_valorise_a_zero(self, db_session, regular_user, service):
        # Un airdrop de jeton non coté compte comme un événement mais
        # n'augmente pas le revenu.
        pf = await portefeuille(db_session, regular_user)
        tok = await actif(db_session, pf, "TOK")
        db_session.add(mouvement(tok, type_tx=TransactionType.AIRDROP, quantite="100", prix="0"))
        await db_session.commit()

        res = await service.get_passive_income(db_session, str(regular_user.id))

        assert res["nb_events"] == 1
        assert res["total_income"] == 0

    async def test_le_filtre_par_annee_restreint_la_periode(self, db_session, regular_user, service):
        pf = await portefeuille(db_session, regular_user)
        eth = await actif(db_session, pf, "ETH")
        db_session.add(
            mouvement(eth, type_tx=TransactionType.STAKING_REWARD, quantite="1", prix="100", quand="2025-06-01")
        )
        db_session.add(
            mouvement(eth, type_tx=TransactionType.STAKING_REWARD, quantite="1", prix="200", quand="2026-06-01")
        )
        await db_session.commit()

        tout = await service.get_passive_income(db_session, str(regular_user.id))
        en_2026 = await service.get_passive_income(db_session, str(regular_user.id), year=2026)

        assert tout["total_income"] == 300.0
        assert en_2026["total_income"] == 200.0

    async def test_la_projection_annuelle_extrapole_les_trois_derniers_mois_percus(
        self, db_session, regular_user, service
    ):
        """Les « trois derniers mois » sont les trois derniers **ayant produit un
        revenu**, non les trois derniers mois calendaires.

        Un portefeuille qui a touché 100 EUR par mois en 2025 puis plus rien
        depuis projette donc 1 200 EUR pour l'année à venir, sur la foi de
        données vieilles d'un an.
        """
        pf = await portefeuille(db_session, regular_user)
        eth = await actif(db_session, pf, "ETH")
        # Un premier mois maigre, puis trois mois pleins : la fenêtre de trois
        # doit ignorer le premier. Une série de trois mois seulement ne
        # prouverait rien — `[-3:]` y vaut la liste entière.
        for mois, montant in (("01", "10"), ("02", "100"), ("03", "100"), ("04", "100")):
            db_session.add(
                mouvement(
                    eth, type_tx=TransactionType.STAKING_REWARD, quantite="1", prix=montant, quand=f"2025-{mois}-01"
                )
            )
        await db_session.commit()

        res = await service.get_passive_income(db_session, str(regular_user.id))

        assert res["projected_annual"] == 1200.0  # 100 x 12, le mois maigre écarté
        assert res["avg_monthly"] == 77.5  # 310 / 4, celui-là compte tout

    async def test_l_historique_est_limite_a_trente_evenements(self, db_session, regular_user, service):
        pf = await portefeuille(db_session, regular_user)
        eth = await actif(db_session, pf, "ETH")
        for i in range(35):
            db_session.add(
                mouvement(
                    eth,
                    type_tx=TransactionType.STAKING_REWARD,
                    quantite="1",
                    prix="10",
                    quand=f"2026-01-{i % 28 + 1:02d}",
                )
            )
        await db_session.commit()

        res = await service.get_passive_income(db_session, str(regular_user.id))

        assert res["nb_events"] == 35
        assert len(res["history"]) == 30
