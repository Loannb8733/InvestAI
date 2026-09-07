"""Filet de caractérisation de l'optimisation fiscale (`get_tax_loss_harvesting`).

Le service recense les positions en moins-value latente qu'il serait fiscalement
intéressant de vendre. `insights_service` était couvert à **13 %**.

Contrairement aux filets précédents, cette fonction lit la base : elle s'appuie
donc sur la fixture `db_session` du projet. Le prix courant, lui, vient du
réseau et est remplacé par un double — sans quoi le test dépendrait du cours du
jour.

Comportement actuel épinglé, pas spécification approuvée.
"""

from decimal import Decimal

import pytest

from app.models.asset import Asset, AssetType
from app.models.portfolio import Portfolio
from app.services import insights_service as module_insights
from app.services.insights_service import InsightsService


@pytest.fixture
def prix(monkeypatch):
    """Fixe le prix courant par symbole ; les absents rendent None."""
    cotations: dict[str, float] = {}

    async def _get_price(symbol, asset_type):
        valeur = cotations.get(symbol.upper())
        return {"price": valeur} if valeur is not None else None

    monkeypatch.setattr(module_insights.price_service, "get_price", _get_price)
    return cotations


async def portefeuille_avec(db_session, user, *actifs) -> Portfolio:
    pf = Portfolio(user_id=user.id, name="Test")
    db_session.add(pf)
    await db_session.flush()
    for symbole, quantite, prix_moyen in actifs:
        db_session.add(
            Asset(
                portfolio_id=pf.id,
                symbol=symbole,
                name=symbole,
                asset_type=AssetType.CRYPTO,
                quantity=Decimal(str(quantite)),
                avg_buy_price=Decimal(str(prix_moyen)),
            )
        )
    await db_session.commit()
    return pf


@pytest.fixture
def service():
    return InsightsService()


class TestSansPortefeuille:
    async def test_un_utilisateur_sans_portefeuille_recoit_un_resultat_vide(self, db_session, regular_user, service):
        res = await service.get_tax_loss_harvesting(db_session, str(regular_user.id))

        assert res["opportunities"] == []
        assert res["total_harvestable"] == 0
        assert res["estimated_tax_saving"] == 0
        # Le raccourci sans portefeuille ne passe pas par la même sortie que le
        # cas nominal : il n'expose ni `nb_candidates` ni `note`.
        assert "nb_candidates" not in res


class TestDetectionDesMoinsValues:
    async def test_une_position_en_perte_devient_une_opportunite(self, db_session, regular_user, service, prix):
        await portefeuille_avec(db_session, regular_user, ("BTC", 1, 50000))
        prix["BTC"] = 40000.0

        res = await service.get_tax_loss_harvesting(db_session, str(regular_user.id))

        assert res["nb_candidates"] == 1
        opp = res["opportunities"][0]
        assert opp["unrealized_loss"] == -10000.0
        assert opp["unrealized_loss_pct"] == -20.0

    async def test_une_position_en_gain_est_ignoree(self, db_session, regular_user, service, prix):
        await portefeuille_avec(db_session, regular_user, ("BTC", 1, 40000))
        prix["BTC"] = 50000.0

        res = await service.get_tax_loss_harvesting(db_session, str(regular_user.id))

        assert res["opportunities"] == []
        assert res["nb_candidates"] == 0

    async def test_une_position_a_l_equilibre_est_ignoree(self, db_session, regular_user, service, prix):
        # Le test est `< 0` strict : une plus-value nulle n'ouvre aucun droit.
        await portefeuille_avec(db_session, regular_user, ("BTC", 1, 40000))
        prix["BTC"] = 40000.0

        res = await service.get_tax_loss_harvesting(db_session, str(regular_user.id))

        assert res["opportunities"] == []

    async def test_les_opportunites_sont_triees_par_perte_decroissante(self, db_session, regular_user, service, prix):
        await portefeuille_avec(db_session, regular_user, ("BTC", 1, 50000), ("ETH", 10, 3000), ("SOL", 100, 200))
        prix.update({"BTC": 45000.0, "ETH": 2000.0, "SOL": 150.0})

        res = await service.get_tax_loss_harvesting(db_session, str(regular_user.id))

        pertes = [o["unrealized_loss"] for o in res["opportunities"]]
        assert pertes == sorted(pertes)  # la plus lourde en tête
        assert res["opportunities"][0]["symbol"] == "ETH"  # -10 000 EUR


class TestCalculFiscal:
    async def test_l_economie_est_estimee_a_trente_pour_cent(self, db_session, regular_user, service, prix):
        """La flat tax française est codée en dur à 30 %.

        Ni le taux du profil investisseur ni celui d'un projet ne sont
        consultés : un utilisateur en enveloppe défiscalisée verrait la même
        économie annoncée qu'un autre au barème.
        """
        await portefeuille_avec(db_session, regular_user, ("BTC", 1, 50000))
        prix["BTC"] = 40000.0

        res = await service.get_tax_loss_harvesting(db_session, str(regular_user.id))

        assert res["estimated_tax_saving"] == 3000.0
        assert res["opportunities"][0]["potential_tax_saving"] == 3000.0

    async def test_le_montant_recoltable_est_negatif_l_economie_positive(self, db_session, regular_user, service, prix):
        await portefeuille_avec(db_session, regular_user, ("BTC", 1, 50000), ("ETH", 10, 3000))
        prix.update({"BTC": 45000.0, "ETH": 2500.0})

        res = await service.get_tax_loss_harvesting(db_session, str(regular_user.id))

        assert res["total_harvestable"] == -10000.0
        assert res["estimated_tax_saving"] == 3000.0

    async def test_sans_moins_value_l_economie_reste_nulle(self, db_session, regular_user, service, prix):
        await portefeuille_avec(db_session, regular_user, ("BTC", 1, 40000))
        prix["BTC"] = 50000.0

        res = await service.get_tax_loss_harvesting(db_session, str(regular_user.id))

        assert res["total_harvestable"] == 0
        assert res["estimated_tax_saving"] == 0


class TestPrixIndisponible:
    async def test_un_prix_absent_fait_disparaitre_l_opportunite(self, db_session, regular_user, service, prix):
        """Sans cours, le prix courant retombe sur le prix de revient.

        La position affiche alors une plus-value **exactement nulle** et sort
        de la liste : l'utilisateur ne voit pas la ligne, et rien ne lui dit que
        le cours manquait. Une position réellement en moins-value passe donc
        inaperçue plutôt que d'être signalée comme non valorisable.
        """
        await portefeuille_avec(db_session, regular_user, ("XYZ", 1, 50000))
        # `prix` reste vide : le double rend None.

        res = await service.get_tax_loss_harvesting(db_session, str(regular_user.id))

        assert res["opportunities"] == []

    async def test_un_prix_nul_est_traite_comme_absent(self, db_session, regular_user, service, prix):
        # `price_data.get("price")` est testé en truthiness : un cours à 0 —
        # un jeton effondré — est confondu avec une absence de cotation, et la
        # perte totale n'apparaît pas.
        await portefeuille_avec(db_session, regular_user, ("DEAD", 1000, 5))
        prix["DEAD"] = 0.0

        res = await service.get_tax_loss_harvesting(db_session, str(regular_user.id))

        assert res["opportunities"] == []


class TestPositionsEcartees:
    async def test_une_position_soldee_est_ecartee(self, db_session, regular_user, service, prix):
        await portefeuille_avec(db_session, regular_user, ("BTC", 0, 50000))
        prix["BTC"] = 40000.0

        res = await service.get_tax_loss_harvesting(db_session, str(regular_user.id))

        assert res["opportunities"] == []

    async def test_un_prix_de_revient_nul_est_ecarte(self, db_session, regular_user, service, prix):
        """Sans prix de revient, il n'y a pas de moins-value à constater.

        Un airdrop reçu gratuitement ne se solde pas fiscalement à perte.

        Le garde-fou `if qty <= 0 or avg_price <= 0: continue` qui l'exprime est
        toutefois **redondant** : le retirer ne change aucun résultat. Une
        quantité nulle est déjà écartée par la requête (`Asset.quantity > 0`),
        et un prix de revient nul donne une base de coût nulle, donc une
        plus-value positive — écartée par le test `unrealized_pnl < 0`. Aucun
        prix courant ne pouvant être négatif, le cas n'existe pas.

        Le comportement est épinglé ; le garde-fou lui-même ne peut pas l'être,
        et ce n'est pas un trou du filet.
        """
        await portefeuille_avec(db_session, regular_user, ("FREE", 100, 0))
        prix["FREE"] = 1.0

        res = await service.get_tax_loss_harvesting(db_session, str(regular_user.id))

        assert res["opportunities"] == []

    async def test_la_base_interdit_les_quantites_negatives(self, db_session, regular_user):
        """Le vrai garde-fou est une contrainte de base, pas le code applicatif.

        Trois filtres écartent les positions vides — `Asset.quantity > 0` en
        SQL, `qty <= 0` en Python, et le test `unrealized_pnl < 0` en aval — et
        les retirer **tous les trois** ne change aucun résultat de cette suite.
        Une position à quantité nulle a une base et une valeur nulles, donc une
        plus-value nulle : le dernier test l'écarte de toute façon.

        Le seul cas où ils compteraient est une quantité **négative** : à −1 BTC
        acheté 40 000 et coté 50 000, la base vaut −40 000 et la valeur −50 000,
        soit une « moins-value » de 10 000 EUR entièrement fictive. Mais ce cas
        ne peut pas se produire — `ck_assets_quantity_positive` le refuse à
        l'écriture.

        Les trois gardes applicatives sont donc de la défense en profondeur
        derrière une contrainte qui tient déjà. C'est la contrainte qui mérite
        un test, et le voici.
        """
        import pytest as _pytest
        from sqlalchemy.exc import IntegrityError

        pf = Portfolio(user_id=regular_user.id, name="Corrompu")
        db_session.add(pf)
        await db_session.flush()
        db_session.add(
            Asset(
                portfolio_id=pf.id,
                symbol="NEG",
                name="NEG",
                asset_type=AssetType.CRYPTO,
                quantity=Decimal("-1"),
                avg_buy_price=Decimal("40000"),
            )
        )

        with _pytest.raises(IntegrityError, match="ck_assets_quantity_positive"):
            await db_session.commit()

        await db_session.rollback()


class TestAvertissement:
    async def test_la_note_met_en_garde_contre_le_rachat_immediat(self, db_session, regular_user, service, prix):
        """La note cite le « wash sale », règle **américaine**.

        Le droit français ne connaît pas cette interdiction pour les
        particuliers ; la mise en garde reste prudente mais le terme est
        dépaysé. Épinglé tel quel — la formulation relève du produit.
        """
        await portefeuille_avec(db_session, regular_user, ("BTC", 1, 50000))
        prix["BTC"] = 40000.0

        res = await service.get_tax_loss_harvesting(db_session, str(regular_user.id))

        assert "wash sale" in res["note"]
        assert "moins-values" in res["note"]
