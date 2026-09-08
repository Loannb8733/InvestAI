"""Filet de caractérisation du rapport de rebalancement.

`get_rebalancing_report` produit les **ordres d'achat et de vente** qu'un
utilisateur exécute réellement pour ramener son allocation crypto sur sa cible.
`report_rebalancing` était couvert à 44 %.

Le rapport lit le patrimoine via `metrics_service` : ce point d'entrée est
doublé pour que le test décrive une composition connue plutôt que celle du jour.

Comportement actuel épinglé, pas spécification approuvée.
"""

import pytest

from app.services import report_rebalancing as module_rebal
from app.services.report_service import report_service


@pytest.fixture
def patrimoine(monkeypatch):
    """Fixe ce que le dashboard rapporte : total et lignes agrégées."""
    etat: dict = {"total_value": 0.0, "aggregated_assets": []}

    async def _metrics(db, user_id, currency="EUR"):
        return etat

    monkeypatch.setattr(module_rebal.metrics_service, "get_user_dashboard_metrics", _metrics)
    return etat


def ligne(symbole, valeur, asset_type="crypto", prix=None):
    """Une entrée d'`aggregated_assets`, telle que `metrics_service` la produit.

    `current_price` en fait partie : l'estimation fiscale s'en sert pour
    convertir un montant à céder en quantité. Un double qui l'omettrait
    laisserait passer le défaut que ce filet a mis au jour — voir
    `test_les_agregats_du_dashboard_portent_bien_un_prix_courant`.
    """
    return {
        "symbol": symbole,
        "current_value": valeur,
        "asset_type": asset_type,
        "current_price": prix if prix is not None else valeur,
    }


async def rapport(db_session, user, cibles, **kwargs):
    return await report_service.get_rebalancing_report(db_session, str(user.id), cibles, estimate_tax=False, **kwargs)


class TestPortefeuilleVide:
    async def test_un_patrimoine_nul_ne_produit_aucun_ordre(self, db_session, regular_user, patrimoine):
        res = await rapport(db_session, regular_user, {"L1": 1.0})

        assert res.total_value == 0
        assert res.orders == []
        assert res.categories == []

    async def test_un_patrimoine_sans_crypto_ne_produit_aucun_ordre(self, db_session, regular_user, patrimoine):
        # Le rebalancement ne porte que sur la poche crypto : un patrimoine
        # entièrement en crowdfunding n'a rien à arbitrer ici.
        patrimoine["total_value"] = 10000.0
        patrimoine["aggregated_assets"] = [ligne("PROJET", 10000.0, asset_type="crowdfunding")]

        res = await rapport(db_session, regular_user, {"L1": 1.0})

        assert res.total_value == 10000.0
        assert res.orders == []


class TestClassement:
    async def test_les_actifs_sont_ranges_par_classe(self, db_session, regular_user, patrimoine):
        patrimoine["total_value"] = 10000.0
        patrimoine["aggregated_assets"] = [
            ligne("BTC", 5000.0),
            ligne("ARB", 3000.0),
            ligne("USDT", 2000.0),
        ]

        res = await rapport(db_session, regular_user, {"L1": 0.5, "L2": 0.3, "Stable": 0.2})

        par_classe = {c["category"]: c["current_pct"] for c in res.categories}
        assert par_classe == {"L1": 50.0, "L2": 30.0, "Stable": 20.0}

    async def test_un_symbole_inconnu_tombe_dans_other(self, db_session, regular_user, patrimoine):
        patrimoine["total_value"] = 1000.0
        patrimoine["aggregated_assets"] = [ligne("ZZZINCONNU", 1000.0)]

        res = await rapport(db_session, regular_user, {"Other": 1.0})

        assert [c["category"] for c in res.categories] == ["Other"]

    async def test_les_poussieres_sont_ecartees(self, db_session, regular_user, patrimoine):
        """Sous dix centimes, une ligne ne compte pas.

        Sans ce filtre, un reliquat de 0,004 EUR ouvrirait une catégorie et
        fausserait les pourcentages de toutes les autres.
        """
        patrimoine["total_value"] = 1000.09
        patrimoine["aggregated_assets"] = [ligne("BTC", 1000.0), ligne("PEPE", 0.09)]

        res = await rapport(db_session, regular_user, {"L1": 1.0})

        assert [c["category"] for c in res.categories] == ["L1"]

    async def test_les_pourcentages_portent_sur_la_poche_crypto_pas_le_patrimoine(
        self, db_session, regular_user, patrimoine
    ):
        # 5 000 EUR de crypto dans un patrimoine de 20 000 : BTC pèse 100 % de
        # la poche, pas 25 % du total. C'est bien la poche qu'on rééquilibre.
        patrimoine["total_value"] = 20000.0
        patrimoine["aggregated_assets"] = [
            ligne("BTC", 5000.0),
            ligne("PROJET", 15000.0, asset_type="crowdfunding"),
        ]

        res = await rapport(db_session, regular_user, {"L1": 1.0})

        assert res.categories[0]["current_pct"] == 100.0
        assert res.total_value == 20000.0
        # Et la dérive suit la même base : viser 100 % de L1 quand la poche est
        # déjà entièrement en L1 ne demande aucun ordre. Rapporter la dérive au
        # patrimoine total réclamerait au contraire 15 000 EUR d'achat.
        assert res.orders == []


class TestOrdres:
    async def test_un_surpoids_donne_un_ordre_de_vente(self, db_session, regular_user, patrimoine):
        patrimoine["total_value"] = 10000.0
        patrimoine["aggregated_assets"] = [ligne("BTC", 8000.0), ligne("USDT", 2000.0)]

        res = await rapport(db_session, regular_user, {"L1": 0.5, "Stable": 0.5})

        ordres = {o.category: (o.action, o.amount_eur) for o in res.orders}
        assert ordres == {"L1": ("sell", 3000.0), "Stable": ("buy", 3000.0)}

    async def test_les_ventes_et_les_achats_s_equilibrent(self, db_session, regular_user, patrimoine):
        patrimoine["total_value"] = 10000.0
        patrimoine["aggregated_assets"] = [
            ligne("BTC", 6000.0),
            ligne("ARB", 3000.0),
            ligne("USDT", 1000.0),
        ]

        res = await rapport(db_session, regular_user, {"L1": 0.4, "L2": 0.3, "Stable": 0.3})

        assert res.total_sell_amount == res.total_buy_amount

    async def test_une_derive_sous_un_euro_ne_declenche_rien(self, db_session, regular_user, patrimoine):
        # Le seuil évite de proposer un arbitrage dont les frais dépasseraient
        # l'enjeu.
        patrimoine["total_value"] = 10000.0
        patrimoine["aggregated_assets"] = [ligne("BTC", 5000.5), ligne("USDT", 4999.5)]

        res = await rapport(db_session, regular_user, {"L1": 0.5, "Stable": 0.5})

        assert res.orders == []

    async def test_une_classe_visee_mais_absente_devient_un_achat(self, db_session, regular_user, patrimoine):
        patrimoine["total_value"] = 10000.0
        patrimoine["aggregated_assets"] = [ligne("BTC", 10000.0)]

        res = await rapport(db_session, regular_user, {"L1": 0.7, "Stable": 0.3})

        ordres = {o.category: o.action for o in res.orders}
        assert ordres == {"L1": "sell", "Stable": "buy"}

    async def test_une_classe_detenue_mais_hors_cible_est_soldee(self, db_session, regular_user, patrimoine):
        """Ce qui n'est pas dans la cible part en vente **intégrale**.

        Omettre une classe de la cible ne signifie pas « laisse-la tranquille »
        mais « ramène-la à zéro » : sa part visée vaut 0.
        """
        patrimoine["total_value"] = 10000.0
        patrimoine["aggregated_assets"] = [ligne("BTC", 7000.0), ligne("DOGE", 3000.0)]

        res = await rapport(db_session, regular_user, {"L1": 1.0})

        meme = next(o for o in res.orders if o.category == "Meme")
        assert (meme.action, meme.amount_eur) == ("sell", 3000.0)

    async def test_le_service_n_impose_pas_que_les_cibles_somment_a_cent(self, db_session, regular_user, patrimoine):
        """La validation `0.99 <= total <= 1.01` vit dans le schéma de l'endpoint.

        Appelé directement, le service accepte une cible à 50 % et lit les
        50 % manquants comme une consigne de tout vendre. Même partage des
        responsabilités que `ALLOWED_DELAY_MONTHS` pour le stress test : tout
        autre appelant contourne le contrôle.
        """
        patrimoine["total_value"] = 10000.0
        patrimoine["aggregated_assets"] = [ligne("BTC", 10000.0)]

        res = await rapport(db_session, regular_user, {"L1": 0.5})

        assert res.orders[0].action == "sell"
        assert res.orders[0].amount_eur == 5000.0


class TestConcentration:
    async def test_le_hhi_est_rendu_sur_l_echelle_zero_dix_mille(self, db_session, regular_user, patrimoine):
        """Troisième échelle de HHI du projet, sur les **classes**.

        Ici `sum(w**2)` avec des poids en pourcentages : un portefeuille
        mono-classe vaut 10 000. `snapshot_risk.calculate_hhi` emploie la même
        échelle sur les **actifs** ; `analytics_scoring._hhi` rend, lui, une
        fraction 0-1. Trois calculs, deux échelles, aucun nom pour les
        distinguer.
        """
        patrimoine["total_value"] = 10000.0
        patrimoine["aggregated_assets"] = [ligne("BTC", 10000.0)]

        res = await rapport(db_session, regular_user, {"L1": 1.0})

        assert res.hhi_before == 10000.0
        assert res.hhi_after == 10000.0

    async def test_une_cible_diversifiee_abaisse_le_hhi_projete(self, db_session, regular_user, patrimoine):
        patrimoine["total_value"] = 10000.0
        patrimoine["aggregated_assets"] = [ligne("BTC", 10000.0)]

        res = await rapport(db_session, regular_user, {"L1": 0.5, "Stable": 0.5})

        assert res.hhi_before == 10000.0
        assert res.hhi_after == 5000.0  # 50² + 50²


class TestFiscalite:
    async def test_l_estimation_fiscale_est_desactivable(self, db_session, regular_user, patrimoine):
        """`estimate_tax=False` évite le rejeu FIFO complet.

        Le widget de dérive du tableau de bord n'a pas besoin du montant
        d'impôt : lui épargner le rejeu de tout l'historique est ce qui le rend
        utilisable. Les champs restent à zéro plutôt que d'être absents.
        """
        patrimoine["total_value"] = 10000.0
        patrimoine["aggregated_assets"] = [ligne("BTC", 8000.0), ligne("USDT", 2000.0)]

        res = await rapport(db_session, regular_user, {"L1": 0.5, "Stable": 0.5})

        assert any(o.action == "sell" for o in res.orders)
        assert res.total_estimated_tax == 0
        assert res.total_estimated_gain == 0

    async def test_une_vente_chiffre_la_plus_value_et_l_impot(self, db_session, regular_user, patrimoine):
        """Avec `estimate_tax=True`, la vente est chiffrée par rejeu FIFO.

        Le portefeuille détient 1 BTC acheté 20 000 EUR et coté 40 000 : la
        poche vaut 40 000, dont il faut céder la moitié pour revenir à 50 %.
        La plus-value latente correspondante et l'impôt au PFU sont estimés à
        partir des couches FIFO réelles, pas d'une moyenne.
        """
        from datetime import datetime, timezone
        from decimal import Decimal

        from app.models.asset import Asset, AssetType
        from app.models.portfolio import Portfolio
        from app.models.transaction import Transaction, TransactionType

        pf = Portfolio(user_id=regular_user.id, name="P")
        db_session.add(pf)
        await db_session.flush()
        btc = Asset(
            portfolio_id=pf.id,
            symbol="BTC",
            name="BTC",
            asset_type=AssetType.CRYPTO,
            quantity=Decimal("1"),
            avg_buy_price=Decimal("20000"),
            current_price=Decimal("40000"),
        )
        db_session.add(btc)
        await db_session.flush()
        db_session.add(
            Transaction(
                asset_id=btc.id,
                transaction_type=TransactionType.BUY,
                quantity=Decimal("1"),
                price=Decimal("20000"),
                fee=Decimal("0"),
                executed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            )
        )
        await db_session.commit()

        patrimoine["total_value"] = 40000.0
        patrimoine["aggregated_assets"] = [ligne("BTC", 40000.0, prix=40000.0)]

        res = await report_service.get_rebalancing_report(
            db_session, str(regular_user.id), {"L1": 0.5, "Stable": 0.5}, estimate_tax=True
        )

        # Céder 20 000 EUR au cours de 40 000 revient à vendre 0,5 BTC, dont la
        # couche FIFO coûte 20 000 : 0,5 x (40 000 - 20 000) = 10 000 EUR de
        # plus-value, taxée à 30 %.
        vente = next(o for o in res.orders if o.action == "sell")
        assert vente.amount_eur == 20000.0
        assert res.total_estimated_gain == 10000.0
        assert res.total_estimated_tax == 3000.0

    async def test_sans_portefeuille_l_estimation_fiscale_ne_leve_pas(self, db_session, regular_user, patrimoine):
        # `estimate_tax=True` sur un utilisateur sans portefeuille en base :
        # la méthode sort tôt, sans toucher au FIFO.
        patrimoine["total_value"] = 10000.0
        patrimoine["aggregated_assets"] = [ligne("BTC", 8000.0), ligne("USDT", 2000.0)]

        res = await report_service.get_rebalancing_report(
            db_session, str(regular_user.id), {"L1": 0.5, "Stable": 0.5}, estimate_tax=True
        )

        assert res.total_estimated_tax == 0


class TestContratDesAgregats:
    async def test_les_agregats_du_dashboard_portent_bien_un_prix_courant(self):
        """Garde-fou contre un double plus complaisant que la réalité.

        Les tests ci-dessus remplacent `get_user_dashboard_metrics` : ils ne
        peuvent donc rien dire de ce que la vraie méthode produit. Or c'est
        exactement là que le défaut se logeait — `aggregated_assets` n'exposait
        pas `current_price`, si bien que l'estimation fiscale valorisait chaque
        ligne à zéro et annonçait un impôt nul quelle que soit la plus-value.

        Ce test lit la source de la projection plutôt que de la monter : la
        faire tourner demanderait tout le dashboard, alors que la régression à
        verrouiller est déclarative.
        """
        from pathlib import Path

        import app.services.metrics_service as module_metrics

        source = Path(module_metrics.__file__).read_text()
        debut = source.index('"aggregated_assets": [')
        # La borne est la clause `for` de la compréhension : un `],` naïf
        # tomberait sur le premier `a["symbol"]` venu.
        projection = source[debut : source.index("for a in aggregated", debut)]

        for cle in ("symbol", "asset_type", "current_value", "current_price"):
            assert f'"{cle}"' in projection, f"`{cle}` a disparu des agrégats du dashboard"


class TestQuantiteAgregee:
    async def test_la_quantite_projetee_permet_de_retrouver_le_prix_unitaire(self, db_session, regular_user):
        """Le résumé Earn calcule `current_value / quantity` pour son prix unitaire.

        Ce test appelle le vrai `get_user_dashboard_metrics` — pas un double —
        et vérifie que le quotient retombe sur le cours de l'actif. Deux
        positions du même symbole sur deux plateformes sont agrégées : la
        quantité doit être leur somme, sans quoi le prix unitaire serait faux
        d'un facteur deux.
        """
        from decimal import Decimal

        from app.models.asset import Asset, AssetType
        from app.models.portfolio import Portfolio
        from app.services.metrics_service import metrics_service

        pf = Portfolio(user_id=regular_user.id, name="P")
        db_session.add(pf)
        await db_session.flush()
        for plateforme in ("Binance", "Kraken"):
            db_session.add(
                Asset(
                    portfolio_id=pf.id,
                    symbol="ETH",
                    name="Ethereum",
                    asset_type=AssetType.CRYPTO,
                    quantity=Decimal("2"),
                    avg_buy_price=Decimal("1500"),
                    current_price=Decimal("2000"),
                    exchange=plateforme,
                )
            )
        await db_session.commit()

        metrics = await metrics_service.get_user_dashboard_metrics(db_session, str(regular_user.id))
        eth = next(a for a in metrics["aggregated_assets"] if a["symbol"] == "ETH")

        assert eth["quantity"] == 4.0  # 2 + 2, les deux plateformes
        # Le cours retenu est celui que le service est allé chercher, pas
        # forcément celui écrit en base : l'assertion porte donc sur la
        # cohérence interne des trois clés, seule chose dont dépend le résumé
        # Earn.
        assert eth["current_value"] / eth["quantity"] == pytest.approx(eth["current_price"], rel=1e-6)
