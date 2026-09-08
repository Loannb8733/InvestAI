"""Ce que devient une alerte quand le cours n'est pas disponible.

`_get_asset_price` rattrape toute erreur du service de prix et retombe sur
`avg_buy_price`. Ce repli est indistinguable d'un cours réel : le garde
`if current_price == 0: return None` ne se déclenche jamais, puisque le prix de
revient n'est pas nul.

Conséquences, selon la condition surveillée :

- `CHANGE_PERCENT_*` compare le cours au prix de revient. Le repli les rend
  égaux, l'écart vaut donc **exactement 0** et l'alerte ne se déclenche jamais —
  au moment précis où le fournisseur de prix est en panne ;
- `PRICE_BELOW` / `PRICE_ABOVE` comparent au seuil : le prix de revient peut
  franchir un seuil que le cours réel ne franchit pas, et l'alerte se déclenche
  **à tort**.

Ces tests épinglent d'abord le comportement fautif, puis le comportement voulu
après correction.
"""

from decimal import Decimal

import pytest

from app.models.alert import Alert, AlertCondition
from app.models.asset import Asset, AssetType
from app.models.portfolio import Portfolio
from app.services.alert_service import AlertService


@pytest.fixture
def service():
    return AlertService()


@pytest.fixture
def cours(monkeypatch, service):
    """Cours renvoyé par le service de prix ; `None` simule une panne."""
    etat = {"valeur": None, "panne": False}

    async def _crypto(symbol):
        if etat["panne"]:
            raise RuntimeError("fournisseur indisponible")
        return etat["valeur"]

    monkeypatch.setattr(service.price_service, "get_crypto_price", _crypto)
    return etat


async def actif_et_alerte(db_session, user, condition, seuil, prix_revient="100"):
    pf = Portfolio(user_id=user.id, name="P")
    db_session.add(pf)
    await db_session.flush()
    a = Asset(
        portfolio_id=pf.id,
        symbol="BTC",
        name="BTC",
        asset_type=AssetType.CRYPTO,
        quantity=Decimal("1"),
        avg_buy_price=Decimal(prix_revient),
    )
    db_session.add(a)
    await db_session.flush()
    alerte = Alert(
        user_id=user.id,
        asset_id=a.id,
        name="test",
        condition=condition,
        threshold=Decimal(str(seuil)),
        is_active=True,
    )
    db_session.add(alerte)
    await db_session.commit()
    return a, alerte


class TestCoursDisponible:
    async def test_une_baisse_reelle_declenche_l_alerte(self, db_session, regular_user, service, cours):
        actif, alerte = await actif_et_alerte(db_session, regular_user, AlertCondition.CHANGE_PERCENT_DOWN, 20)
        cours["valeur"] = 50.0  # -50 % depuis 100

        resultat = await service._check_single_alert(db_session, alerte)

        assert resultat is not None

    async def test_une_baisse_sous_le_seuil_ne_declenche_pas(self, db_session, regular_user, service, cours):
        actif, alerte = await actif_et_alerte(db_session, regular_user, AlertCondition.CHANGE_PERCENT_DOWN, 20)
        cours["valeur"] = 90.0  # -10 %, sous le seuil de 20

        assert await service._check_single_alert(db_session, alerte) is None


class TestCoursIndisponible:
    async def test_une_panne_du_fournisseur_ne_declenche_aucune_alerte_de_variation(
        self, db_session, regular_user, service, cours
    ):
        """Sans cours, la variation est inconnue — l'alerte doit se taire.

        Avant correction elle se taisait aussi, mais pour une mauvaise raison :
        le repli sur le prix de revient rendait l'écart exactement nul. La
        différence se voit sur le cas suivant, où le repli faisait **déclencher**
        une alerte à tort.
        """
        actif, alerte = await actif_et_alerte(db_session, regular_user, AlertCondition.CHANGE_PERCENT_DOWN, 20)
        cours["panne"] = True

        assert await service._check_single_alert(db_session, alerte) is None

    async def test_une_panne_ne_doit_pas_declencher_une_alerte_de_seuil(self, db_session, regular_user, service, cours):
        """Le cœur du défaut : `PRICE_BELOW` se déclenchait sur le prix de revient.

        Un actif acheté 100 avec une alerte « sous 150 » : le cours réel est
        peut-être à 200, mais le repli renvoie 100, qui passe sous le seuil.
        L'utilisateur reçoit une alerte de baisse alors que rien n'a baissé —
        et il n'a aucun moyen de savoir que le cours manquait.
        """
        actif, alerte = await actif_et_alerte(
            db_session, regular_user, AlertCondition.PRICE_BELOW, 150, prix_revient="100"
        )
        cours["panne"] = True

        assert await service._check_single_alert(db_session, alerte) is None

    async def test_un_cours_nul_est_traite_comme_une_panne(self, db_session, regular_user, service, cours):
        actif, alerte = await actif_et_alerte(
            db_session, regular_user, AlertCondition.PRICE_BELOW, 150, prix_revient="100"
        )
        cours["valeur"] = 0.0

        assert await service._check_single_alert(db_session, alerte) is None


class TestActifsNonCotes:
    async def test_un_actif_sans_cotation_garde_son_prix_de_revient(self, db_session, regular_user, service):
        """Immobilier, crowdfunding : il n'y a pas de cours à chercher.

        Pour ces types, `avg_buy_price` **est** la valeur de référence, et le
        repli n'en est pas un. La correction ne doit pas les priver d'alertes.
        """
        pf = Portfolio(user_id=regular_user.id, name="P")
        db_session.add(pf)
        await db_session.flush()
        bien = Asset(
            portfolio_id=pf.id,
            symbol="SCPI",
            name="SCPI",
            asset_type=AssetType.REAL_ESTATE,
            quantity=Decimal("1"),
            avg_buy_price=Decimal("100"),
        )
        db_session.add(bien)
        await db_session.commit()

        assert await service._get_asset_price(bien) == 100.0
