"""Filet sur la détection et le comblement des écarts de solde.

Quand un exchange annonce plus d'unités que l'historique n'en explique — un bon
Binance Earn, un airdrop non reconnu, une récompense manquée — l'écart apparaît
dans `/balance-gaps`, et `/balance-gaps/credit-all` le comble en créant un
**AIRDROP** par actif concerné.

Ces deux routes n'avaient aucun test, et la seconde **écrit en base d'un clic**.
Zéro crédit automatique a été passé à ce jour : le filet vient donc avant le
premier usage, pas après.

Un trou est épinglé là où il apparaît : la somme des transactions ignore quatre
types de mouvement (NEW-62).
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.core.security import create_access_token
from app.models.asset import Asset, AssetType
from app.models.portfolio import Portfolio
from app.models.transaction import Transaction, TransactionType
from app.models.user import User

MAINTENANT = datetime.now(timezone.utc)


@pytest.fixture
def entetes(regular_user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(subject=str(regular_user.id))}"}


@pytest.fixture
async def portefeuille(db_session, regular_user: User) -> Portfolio:
    p = Portfolio(user_id=regular_user.id, name="Principal")
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p)
    return p


async def _actif(
    db_session,
    portefeuille: Portfolio,
    *,
    symbole: str = "BTC",
    detenu: str = "1.5",
    cours: str = "30000",
    type_actif: AssetType = AssetType.CRYPTO,
) -> Asset:
    """Un actif dont la quantité stockée est celle que l'exchange annonce."""
    a = Asset(
        portfolio_id=portefeuille.id,
        symbol=symbole,
        name=symbole,
        asset_type=type_actif,
        quantity=Decimal(detenu),
        avg_buy_price=Decimal("0"),
        current_price=Decimal(cours) if cours else None,
        exchange="Binance",
    )
    db_session.add(a)
    await db_session.commit()
    await db_session.refresh(a)
    return a


async def _mouvement(
    db_session, actif: Asset, type_: TransactionType, quantite: str, *, quand: datetime = MAINTENANT
) -> None:
    db_session.add(
        Transaction(
            asset_id=actif.id,
            transaction_type=type_,
            quantity=Decimal(quantite),
            price=Decimal("30000"),
            fee=Decimal("0"),
            currency="EUR",
            executed_at=quand,
        )
    )
    await db_session.commit()


async def _ecarts(client, entetes, **parametres) -> dict:
    reponse = await client.get("/api/v1/transactions/balance-gaps", params=parametres, headers=entetes)
    assert reponse.status_code == 200, reponse.text
    return reponse.json()


class TestDetection:
    async def test_un_historique_complet_ne_produit_aucun_ecart(self, client, entetes, db_session, portefeuille):
        actif = await _actif(db_session, portefeuille, detenu="1.5")
        await _mouvement(db_session, actif, TransactionType.BUY, "1.5")

        assert await _ecarts(client, entetes) == {"count": 0, "threshold_eur": 5.0, "gaps": []}

    async def test_un_surplus_est_signale_avec_sa_valeur(self, client, entetes, db_session, portefeuille):
        # 1,5 détenu, 1 seul acheté : l'exchange annonce 0,5 de plus que
        # l'historique n'en explique, soit 15 000 € au cours de 30 000 €.
        actif = await _actif(db_session, portefeuille, detenu="1.5", cours="30000")
        await _mouvement(db_session, actif, TransactionType.BUY, "1")

        resultat = await _ecarts(client, entetes)

        assert resultat["count"] == 1
        ecart = resultat["gaps"][0]
        assert ecart["missing_qty"] == pytest.approx(0.5)
        assert ecart["missing_eur"] == pytest.approx(15000)
        assert ecart["suggested_action"] == "credit_airdrop"

    async def test_un_deficit_n_est_pas_signale(self, client, entetes, db_session, portefeuille):
        """Seul le surplus est traité.

        Moins d'unités que l'historique n'en compte relève d'un retrait manqué,
        non d'un bon à créditer : le combler par un AIRDROP aggraverait l'écart.
        """
        actif = await _actif(db_session, portefeuille, detenu="0.5")
        await _mouvement(db_session, actif, TransactionType.BUY, "2")

        assert (await _ecarts(client, entetes))["count"] == 0

    async def test_un_deficit_reste_ecarte_meme_sous_un_seuil_negatif(self, client, entetes, db_session, portefeuille):
        """Le cas de bord que le seuil ne couvre pas.

        Un déficit vaut un montant **négatif** en euros : le seuil de 5 € l'écarte
        de lui-même, ce qui rend la garde sur le signe invisible tant que le seuil
        reste positif. Or rien ne l'oblige à l'être — `threshold_eur` n'a aucune
        borne dans la signature. Sous un seuil négatif, sans cette garde, un
        déficit remonterait avec une quantité manquante négative, et `credit-all`
        créerait un AIRDROP de quantité négative.
        """
        actif = await _actif(db_session, portefeuille, detenu="0.5")
        await _mouvement(db_session, actif, TransactionType.BUY, "2")

        assert (await _ecarts(client, entetes, threshold_eur=-1_000_000))["count"] == 0

    async def test_un_ecart_sous_le_seuil_est_ignore(self, client, entetes, db_session, portefeuille):
        # 0,0001 BTC à 30 000 € = 3 €, sous le seuil de 5 €.
        actif = await _actif(db_session, portefeuille, detenu="1.0001", cours="30000")
        await _mouvement(db_session, actif, TransactionType.BUY, "1")

        assert (await _ecarts(client, entetes))["count"] == 0
        assert (await _ecarts(client, entetes, threshold_eur=1))["count"] == 1

    async def test_un_actif_sans_cours_reste_invisible(self, client, entetes, db_session, portefeuille):
        """Sans prix, l'écart vaut zéro euro et tombe sous n'importe quel seuil.

        La quantité manquante est pourtant bien réelle : c'est le cours qui
        manque, pas l'écart. Un seuil à zéro le ferait apparaître.
        """
        actif = await _actif(db_session, portefeuille, detenu="2", cours=None)
        await _mouvement(db_session, actif, TransactionType.BUY, "1")

        assert (await _ecarts(client, entetes))["count"] == 0
        assert (await _ecarts(client, entetes, threshold_eur=0))["count"] == 1

    async def test_un_actif_en_staking_est_exclu(self, client, entetes, db_session, portefeuille):
        """Le principal placé en Earn vit hors du journal des transactions.

        Il crée un écart permanent qui n'est pas un bon manquant : le créditer
        en AIRDROP doublerait la position.
        """
        actif = await _actif(db_session, portefeuille, detenu="1.5")
        await _mouvement(db_session, actif, TransactionType.BUY, "1")
        await _mouvement(db_session, actif, TransactionType.STAKING, "0.5")

        assert (await _ecarts(client, entetes))["count"] == 0

    async def test_le_crowdfunding_est_hors_de_portee(self, client, entetes, db_session, portefeuille):
        actif = await _actif(db_session, portefeuille, symbole="PROJ", detenu="2", type_actif=AssetType.CROWDFUNDING)
        await _mouvement(db_session, actif, TransactionType.BUY, "1")

        assert (await _ecarts(client, entetes))["count"] == 0

    async def test_les_ecarts_sont_ordonnes_du_plus_gros_au_plus_petit(self, client, entetes, db_session, portefeuille):
        petit = await _actif(db_session, portefeuille, symbole="ETH", detenu="1.1", cours="2000")
        await _mouvement(db_session, petit, TransactionType.BUY, "1")
        gros = await _actif(db_session, portefeuille, symbole="BTC", detenu="1.5", cours="30000")
        await _mouvement(db_session, gros, TransactionType.BUY, "1")

        resultat = await _ecarts(client, entetes)

        assert [g["symbol"] for g in resultat["gaps"]] == ["BTC", "ETH"]


class TestIndiceDeProvenance:
    async def test_une_recompense_recente_suggere_un_earn_en_attente(self, client, entetes, db_session, portefeuille):
        actif = await _actif(db_session, portefeuille, detenu="1.6")
        await _mouvement(db_session, actif, TransactionType.BUY, "1")
        await _mouvement(db_session, actif, TransactionType.STAKING_REWARD, "0.1", quand=MAINTENANT - timedelta(days=3))

        assert (await _ecarts(client, entetes))["gaps"][0]["source_hint"] == "earn_pending"

    async def test_une_recompense_ancienne_ne_suffit_plus(self, client, entetes, db_session, portefeuille):
        # Au-delà de trente jours, la piste Earn n'est plus la plus probable.
        actif = await _actif(db_session, portefeuille, detenu="1.6")
        await _mouvement(db_session, actif, TransactionType.BUY, "1")
        await _mouvement(
            db_session, actif, TransactionType.STAKING_REWARD, "0.1", quand=MAINTENANT - timedelta(days=45)
        )

        assert (await _ecarts(client, entetes))["gaps"][0]["source_hint"] == "unknown"

    async def test_un_airdrop_passe_oriente_vers_un_airdrop(self, client, entetes, db_session, portefeuille):
        actif = await _actif(db_session, portefeuille, detenu="1.6")
        await _mouvement(db_session, actif, TransactionType.BUY, "1")
        await _mouvement(db_session, actif, TransactionType.AIRDROP, "0.1", quand=MAINTENANT - timedelta(days=200))

        assert (await _ecarts(client, entetes))["gaps"][0]["source_hint"] == "airdrop"

    async def test_sans_precedent_l_origine_reste_inconnue(self, client, entetes, db_session, portefeuille):
        actif = await _actif(db_session, portefeuille, detenu="1.5")
        await _mouvement(db_session, actif, TransactionType.BUY, "1")

        assert (await _ecarts(client, entetes))["gaps"][0]["source_hint"] == "unknown"


class TestTousLesTypesQuiDeplacentLaQuantite:
    """NEW-62 : quatre types manquaient à la somme.

    La somme SQL ne connaissait que sept types : achat, transferts, conversions,
    airdrop et récompense de staking. **Dividende, intérêt, frais et unstaking
    tombaient dans le `ELSE 0`**, alors que les listes de `create_transaction`
    et de l'import CSV les comptent bien.

    Un dividende versé en jetons augmentait la quantité détenue sans entrer dans
    la somme : l'écart qui en résultait était proposé au crédit, et `credit-all`
    aurait créé un AIRDROP par-dessus le dividende — la même quantité comptée
    deux fois dans l'historique.

    Aucune transaction de ces types n'existe aujourd'hui en base : le trou était
    latent, comme l'était celui du « W » avant lui.
    """

    @pytest.mark.parametrize("type_", [TransactionType.DIVIDEND, TransactionType.INTEREST])
    async def test_un_revenu_percu_en_nature_entre_dans_la_somme(
        self, client, entetes, db_session, portefeuille, type_
    ):
        actif = await _actif(db_session, portefeuille, detenu="1.5")
        await _mouvement(db_session, actif, TransactionType.BUY, "1")
        await _mouvement(db_session, actif, type_, "0.5")

        assert (await _ecarts(client, entetes))["count"] == 0

    async def test_des_frais_preleves_en_nature_sortent_de_la_somme(self, client, entetes, db_session, portefeuille):
        # 2 achetés, 0,5 payés en frais, 1,5 détenus : rien ne manque.
        actif = await _actif(db_session, portefeuille, detenu="1.5")
        await _mouvement(db_session, actif, TransactionType.BUY, "2")
        await _mouvement(db_session, actif, TransactionType.FEE, "0.5")

        assert (await _ecarts(client, entetes))["count"] == 0

    async def test_une_position_sortie_du_staking_redevient_visible(self, client, entetes, db_session, portefeuille):
        """Le dé-staking rend le principal au journal.

        `staking_qty` sommait les mises en staking sans en déduire les sorties :
        un actif passé par Earn restait exclu de la détection **pour toujours**,
        même une fois entièrement dé-staké.
        """
        actif = await _actif(db_session, portefeuille, detenu="1.5")
        await _mouvement(db_session, actif, TransactionType.BUY, "1")
        await _mouvement(db_session, actif, TransactionType.STAKING, "0.5")
        assert (await _ecarts(client, entetes))["count"] == 0

        await _mouvement(db_session, actif, TransactionType.UNSTAKING, "0.5")

        assert (await _ecarts(client, entetes))["count"] == 1


class TestCredit:
    async def _crediter(self, client, entetes, **parametres) -> dict:
        reponse = await client.post("/api/v1/transactions/balance-gaps/credit-all", params=parametres, headers=entetes)
        assert reponse.status_code == 201, reponse.text
        return reponse.json()

    async def test_un_ecart_devient_un_airdrop_au_cours_du_jour(self, client, entetes, db_session, portefeuille):
        actif = await _actif(db_session, portefeuille, detenu="1.5", cours="30000")
        await _mouvement(db_session, actif, TransactionType.BUY, "1")

        resultat = await self._crediter(client, entetes)

        assert resultat["credited"] == 1
        airdrops = (
            (
                await db_session.execute(
                    select(Transaction).where(Transaction.transaction_type == TransactionType.AIRDROP)
                )
            )
            .scalars()
            .all()
        )
        assert len(airdrops) == 1
        assert float(airdrops[0].quantity) == pytest.approx(0.5)
        assert float(airdrops[0].price) == pytest.approx(30000)

    async def test_le_credit_referme_l_ecart(self, client, entetes, db_session, portefeuille):
        actif = await _actif(db_session, portefeuille, detenu="1.5")
        await _mouvement(db_session, actif, TransactionType.BUY, "1")
        await self._crediter(client, entetes)

        assert (await _ecarts(client, entetes))["count"] == 0

    async def test_deux_appels_le_meme_jour_ne_creditent_qu_une_fois(self, client, entetes, db_session, portefeuille):
        """L'idempotence tient à un `external_id` daté du jour.

        Le second appel ne trouve d'ailleurs plus d'écart — le premier l'a
        refermé — ce qui protège doublement.
        """
        actif = await _actif(db_session, portefeuille, detenu="1.5")
        await _mouvement(db_session, actif, TransactionType.BUY, "1")

        premier = await self._crediter(client, entetes)
        second = await self._crediter(client, entetes)

        assert (premier["credited"], second["credited"]) == (1, 0)

    async def test_sans_cours_de_marche_l_ecart_n_est_pas_credite(self, client, entetes, db_session, portefeuille):
        """Un airdrop sans prix fausserait le prix de revient plutôt que l'aider."""
        actif = await _actif(db_session, portefeuille, detenu="2", cours=None)
        await _mouvement(db_session, actif, TransactionType.BUY, "1")

        resultat = await self._crediter(client, entetes, threshold_eur=0)

        assert resultat["credited"] == 0
        assert resultat["skipped"] == 1
        assert resultat["details"]["skipped"][0]["reason"] == "no_market_price"

    async def test_sans_ecart_rien_n_est_ecrit(self, client, entetes, db_session, portefeuille):
        actif = await _actif(db_session, portefeuille, detenu="1")
        await _mouvement(db_session, actif, TransactionType.BUY, "1")

        assert await self._crediter(client, entetes) == {"credited": 0, "skipped": 0, "details": []}

    async def test_l_airdrop_cree_porte_une_note_qui_dit_son_origine(self, client, entetes, db_session, portefeuille):
        # La ligne apparaîtra dans l'historique de l'utilisateur : elle doit se
        # distinguer d'un airdrop qu'il aurait saisi lui-même.
        actif = await _actif(db_session, portefeuille, detenu="1.5")
        await _mouvement(db_session, actif, TransactionType.BUY, "1")

        await self._crediter(client, entetes)

        airdrop = (
            (
                await db_session.execute(
                    select(Transaction).where(Transaction.transaction_type == TransactionType.AIRDROP)
                )
            )
            .scalars()
            .one()
        )
        assert "Auto-credit from balance-gaps" in airdrop.notes
        assert airdrop.external_id.startswith("auto_credit_gap_")

    async def test_le_credit_invalide_le_cache_du_tableau_de_bord(
        self, client, entetes, db_session, portefeuille, monkeypatch
    ):
        """Toutes les routes qui écrivent des transactions le font ; celle-ci l'oubliait.

        Sans invalidation, le tableau de bord affiche encore les chiffres d'avant
        le crédit jusqu'à l'expiration du cache — l'utilisateur clique, voit le
        succès annoncé, et rien ne bouge à l'écran.
        """
        invalidations = []
        monkeypatch.setattr("app.api.v1.endpoints.transactions.invalidate_dashboard_cache", invalidations.append)
        actif = await _actif(db_session, portefeuille, detenu="1.5")
        await _mouvement(db_session, actif, TransactionType.BUY, "1")

        await self._crediter(client, entetes)

        assert invalidations != []

    async def test_sans_ecart_le_cache_n_est_pas_touche(self, client, entetes, db_session, portefeuille, monkeypatch):
        # Rien n'a changé : invalider ferait recalculer le tableau de bord pour rien.
        invalidations = []
        monkeypatch.setattr("app.api.v1.endpoints.transactions.invalidate_dashboard_cache", invalidations.append)
        actif = await _actif(db_session, portefeuille, detenu="1")
        await _mouvement(db_session, actif, TransactionType.BUY, "1")

        await self._crediter(client, entetes)

        assert invalidations == []
