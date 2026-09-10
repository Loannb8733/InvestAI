"""Filet sur la modification et la suppression d'une transaction.

Ces deux routes sont celles qui **défont** l'effet d'une transaction sur la
quantité détenue et sur le prix de revient moyen. C'est le lieu classique de
l'asymétrie : créer ajoute, défaire retire — mais pas tout à fait la même chose.

`endpoints/transactions.py` est couvert à **12 %** ; `update_transaction`
(138 lignes) et `delete_transaction` (100 lignes) ne l'étaient pas du tout,
alors que ce sont les deux gestes que l'utilisateur pose le plus souvent sur ses
840 transactions, et que leur résultat alimente la plus-value imposable.

Le filet épingle le comportement actuel, ses trous compris : deux d'entre eux
sont signalés dans les tests qui les couvrent (NEW-56 et NEW-57).
"""

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.security import create_access_token
from app.models.asset import Asset
from app.models.transaction import Transaction
from app.models.user import User


async def _portefeuille_avec_actif(client: AsyncClient, token: str, *, plateforme: str = "Kraken") -> tuple[str, str]:
    entetes = {"Authorization": f"Bearer {token}"}
    portefeuille = await client.post("/api/v1/portfolios", json={"name": "Portefeuille"}, headers=entetes)
    pid = portefeuille.json()["id"]
    actif = await client.post(
        "/api/v1/assets",
        json={
            "portfolio_id": pid,
            "symbol": "BTC",
            "asset_type": "crypto",
            "quantity": "1",
            "avg_buy_price": "40000",
            "exchange": plateforme,
        },
        headers=entetes,
    )
    return pid, actif.json()["id"]


async def _creer(client: AsyncClient, entetes: dict, actif_id: str, **champs) -> dict:
    corps = {
        "asset_id": actif_id,
        "transaction_type": "buy",
        "quantity": "0.5",
        "price": "42000",
        "fee": "0",
        "currency": "EUR",
    }
    corps.update(champs)
    reponse = await client.post("/api/v1/transactions", json=corps, headers=entetes)
    assert reponse.status_code == 201, reponse.text
    return reponse.json()


@pytest.fixture
def entetes(regular_user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(subject=str(regular_user.id))}"}


async def _actif(db_session, actif_id) -> Asset:
    resultat = await db_session.execute(select(Asset).where(Asset.id == actif_id))
    actif = resultat.scalar_one()
    await db_session.refresh(actif)
    return actif


class TestModificationDeQuantite:
    async def test_l_ancien_effet_est_annule_avant_le_nouveau(self, client, entetes, db_session):
        """Une quantité corrigée ne s'ajoute pas : elle remplace.

        L'actif part de 1 BTC ; l'achat de 0,5 le porte à 1,5. Corriger l'achat
        à 2 doit donner 3 (1,5 − 0,5 + 2), non 3,5.
        """
        _, actif_id = await _portefeuille_avec_actif(client, entetes["Authorization"].split()[1])
        transaction = await _creer(client, entetes, actif_id)
        assert float((await _actif(db_session, actif_id)).quantity) == pytest.approx(1.5)

        reponse = await client.patch(
            f"/api/v1/transactions/{transaction['id']}", json={"quantity": "2"}, headers=entetes
        )

        assert reponse.status_code == 200
        assert float((await _actif(db_session, actif_id)).quantity) == pytest.approx(3.0)

    async def test_changer_le_type_bascule_le_signe(self, client, entetes, db_session):
        # Achat de 0,5 (actif à 1,5) requalifié en vente : 1,5 − 0,5 − 0,5 = 0,5.
        _, actif_id = await _portefeuille_avec_actif(client, entetes["Authorization"].split()[1])
        transaction = await _creer(client, entetes, actif_id)

        await client.patch(
            f"/api/v1/transactions/{transaction['id']}", json={"transaction_type": "sell"}, headers=entetes
        )

        assert float((await _actif(db_session, actif_id)).quantity) == pytest.approx(0.5)

    async def test_une_quantite_qui_rendrait_negatif_est_ramenee_a_zero(self, client, entetes, db_session):
        """Le portefeuille ne descend jamais sous zéro.

        Une vente de 10 BTC sur 1,5 détenus donnerait −8,5 ; la quantité est
        bornée à 0. Le geste est journalisé côté serveur mais la réponse HTTP ne
        le signale pas — l'utilisateur ne voit pas que sa saisie a été bornée.
        """
        _, actif_id = await _portefeuille_avec_actif(client, entetes["Authorization"].split()[1])
        transaction = await _creer(client, entetes, actif_id, transaction_type="sell", quantity="0.2")

        reponse = await client.patch(
            f"/api/v1/transactions/{transaction['id']}", json={"quantity": "10"}, headers=entetes
        )

        assert reponse.status_code == 200
        assert float((await _actif(db_session, actif_id)).quantity) == 0

    async def test_les_types_de_staking_ne_touchent_pas_la_quantite(self, client, entetes, db_session):
        """`staking` et `unstaking` ne figurent dans aucune des deux listes.

        Mettre en staking ne fait pas sortir l'actif du portefeuille : la
        quantité doit rester inchangée. Les trois routes — création,
        modification, suppression — s'accordent sur ce point, ce qui en fait un
        choix et non un oubli.
        """
        _, actif_id = await _portefeuille_avec_actif(client, entetes["Authorization"].split()[1])
        transaction = await _creer(client, entetes, actif_id, transaction_type="staking")
        assert float((await _actif(db_session, actif_id)).quantity) == pytest.approx(1.0)

        await client.patch(f"/api/v1/transactions/{transaction['id']}", json={"quantity": "7"}, headers=entetes)

        assert float((await _actif(db_session, actif_id)).quantity) == pytest.approx(1.0)


class TestPrixDeRevient:
    async def test_le_prix_de_revient_est_recalcule_depuis_les_transactions(self, client, entetes, db_session):
        """Le prix saisi à la création de l'actif ne survit pas au premier achat.

        Il est recalculé à partir des seules transactions d'entrée, frais
        compris : (0,5 × 42 000 + 10) / 0,5 = 42 020 — et non les 40 000 posés
        à la main sur l'actif.
        """
        _, actif_id = await _portefeuille_avec_actif(client, entetes["Authorization"].split()[1])

        await _creer(client, entetes, actif_id, fee="10")

        assert float((await _actif(db_session, actif_id)).avg_buy_price) == pytest.approx(42020)

    async def test_modifier_le_prix_recalcule_le_prix_de_revient(self, client, entetes, db_session):
        _, actif_id = await _portefeuille_avec_actif(client, entetes["Authorization"].split()[1])
        transaction = await _creer(client, entetes, actif_id)

        await client.patch(f"/api/v1/transactions/{transaction['id']}", json={"price": "30000"}, headers=entetes)

        assert float((await _actif(db_session, actif_id)).avg_buy_price) == pytest.approx(30000)

    async def test_modifier_les_frais_seuls_recalcule_le_prix_de_revient(self, client, entetes, db_session):
        """NEW-56 : les frais entrent dans le prix de revient.

        `_recalculate_avg_buy_price` somme `quantité × prix + frais`. Le
        recalcul n'était pourtant déclenché que par un changement de quantité,
        de type ou de prix : corriger les seuls frais laissait le prix de
        revient sur sa valeur d'avant, sans rien signaler, jusqu'à la
        modification suivante.

        Frais portés à 100 : (0,5 × 42 000 + 100) / 0,5 = 42 200.
        """
        _, actif_id = await _portefeuille_avec_actif(client, entetes["Authorization"].split()[1])
        transaction = await _creer(client, entetes, actif_id, fee="0")
        assert float((await _actif(db_session, actif_id)).avg_buy_price) == pytest.approx(42000)

        await client.patch(f"/api/v1/transactions/{transaction['id']}", json={"fee": "100"}, headers=entetes)

        assert float((await _actif(db_session, actif_id)).avg_buy_price) == pytest.approx(42200)


class TestPortee:
    async def test_une_transaction_d_un_autre_utilisateur_est_introuvable(self, client, entetes, admin_user):
        """404, non 403 : l'existence même de la transaction n'est pas révélée."""
        autre = {"Authorization": f"Bearer {create_access_token(subject=str(admin_user.id))}"}
        _, actif_id = await _portefeuille_avec_actif(client, autre["Authorization"].split()[1])
        transaction = await _creer(client, autre, actif_id)

        modification = await client.patch(
            f"/api/v1/transactions/{transaction['id']}", json={"quantity": "9"}, headers=entetes
        )
        suppression = await client.delete(f"/api/v1/transactions/{transaction['id']}", headers=entetes)

        assert modification.status_code == 404
        assert suppression.status_code == 404

    async def test_un_champ_inconnu_du_schema_est_ignore(self, client, entetes):
        """Déplacer une transaction d'un actif à l'autre laisserait les deux
        quantités fausses. `asset_id` est donc refusé — par le schéma Pydantic,
        qui ne le déclare pas : c'est lui qui filtre ici, non la liste blanche
        de la route (voir le test de forme ci-dessous)."""
        _, actif_id = await _portefeuille_avec_actif(client, entetes["Authorization"].split()[1])
        _, autre_actif_id = await _portefeuille_avec_actif(
            client, entetes["Authorization"].split()[1], plateforme="Bybit"
        )
        transaction = await _creer(client, entetes, actif_id)

        reponse = await client.patch(
            f"/api/v1/transactions/{transaction['id']}",
            json={"asset_id": autre_actif_id, "notes": "annotation"},
            headers=entetes,
        )

        assert reponse.json()["asset_id"] == actif_id
        assert reponse.json()["notes"] == "annotation"

    def test_la_liste_blanche_de_la_route_ne_deborde_pas_du_schema(self):
        """La liste blanche `_PATCHABLE` est une défense en profondeur — et,
        telle quelle, **inerte** : elle énumère exactement les champs que
        `TransactionUpdate` déclare, donc rien ne peut la franchir que Pydantic
        n'ait déjà laissé passer. Un canari qui la retire ne fait échouer aucun
        test comportemental, et c'est normal.

        Ce qu'elle protège vraiment, c'est l'avenir : le jour où un champ est
        ajouté au schéma, il n'atteindra la transaction que si quelqu'un l'a
        aussi inscrit ici. Ce test surveille l'écart entre les deux listes,
        seule chose qu'un test puisse observer d'une garde inerte.
        """
        import inspect

        from app.api.v1.endpoints.transactions import update_transaction
        from app.schemas.transaction import TransactionUpdate

        source = inspect.getsource(update_transaction)
        bloc = source.split("_PATCHABLE = {")[1].split("}")[0]
        liste_blanche = {ligne.strip().strip('",') for ligne in bloc.splitlines() if ligne.strip()}

        assert liste_blanche <= set(
            TransactionUpdate.model_fields
        ), "la liste blanche cite un champ que le schéma ne déclare pas"
        assert "asset_id" not in liste_blanche and "internal_hash" not in liste_blanche


class TestSuppression:
    async def test_supprimer_un_achat_retire_sa_quantite(self, client, entetes, db_session):
        _, actif_id = await _portefeuille_avec_actif(client, entetes["Authorization"].split()[1])
        transaction = await _creer(client, entetes, actif_id)

        reponse = await client.delete(f"/api/v1/transactions/{transaction['id']}", headers=entetes)

        assert reponse.status_code == 204
        assert float((await _actif(db_session, actif_id)).quantity) == pytest.approx(1.0)

    async def test_supprimer_une_vente_rend_sa_quantite(self, client, entetes, db_session):
        _, actif_id = await _portefeuille_avec_actif(client, entetes["Authorization"].split()[1])
        transaction = await _creer(client, entetes, actif_id, transaction_type="sell", quantity="0.4")
        assert float((await _actif(db_session, actif_id)).quantity) == pytest.approx(0.6)

        await client.delete(f"/api/v1/transactions/{transaction['id']}", headers=entetes)

        assert float((await _actif(db_session, actif_id)).quantity) == pytest.approx(1.0)

    async def test_supprimer_le_dernier_achat_remet_le_prix_de_revient_a_zero(self, client, entetes, db_session):
        """Sans transaction d'entrée, il n'y a plus de prix de revient à afficher.

        Zéro plutôt que la dernière valeur connue : garder l'ancienne ferait
        croire à un coût qu'aucune transaction ne justifie plus.
        """
        _, actif_id = await _portefeuille_avec_actif(client, entetes["Authorization"].split()[1])
        transaction = await _creer(client, entetes, actif_id)

        await client.delete(f"/api/v1/transactions/{transaction['id']}", headers=entetes)

        assert float((await _actif(db_session, actif_id)).avg_buy_price) == 0

    async def test_supprimer_un_achat_parmi_deux_recalcule_sur_le_reste(self, client, entetes, db_session):
        _, actif_id = await _portefeuille_avec_actif(client, entetes["Authorization"].split()[1])
        premier = await _creer(client, entetes, actif_id, quantity="1", price="30000")
        await _creer(client, entetes, actif_id, quantity="1", price="50000")
        assert float((await _actif(db_session, actif_id)).avg_buy_price) == pytest.approx(40000)

        await client.delete(f"/api/v1/transactions/{premier['id']}", headers=entetes)

        assert float((await _actif(db_session, actif_id)).avg_buy_price) == pytest.approx(50000)

    async def test_une_transaction_inexistante_rend_404(self, client, entetes):
        reponse = await client.delete("/api/v1/transactions/00000000-0000-0000-0000-000000000000", headers=entetes)

        assert reponse.status_code == 404


class TestTransfertAvecMiroir:
    async def _transfert(self, client, entetes, db_session):
        jeton = entetes["Authorization"].split()[1]
        _, actif_id = await _portefeuille_avec_actif(client, jeton, plateforme="Kraken")
        await _creer(client, entetes, actif_id, quantity="1", price="30000")
        sortie = await _creer(
            client,
            entetes,
            actif_id,
            transaction_type="transfer_out",
            quantity="0.5",
            price="30000",
            destination_exchange="Tangem",
        )
        resultat = await db_session.execute(select(Asset).where(Asset.exchange == "Tangem", Asset.symbol == "BTC"))
        return actif_id, sortie, resultat.scalar_one()

    async def test_le_transfert_cree_un_miroir_sur_la_plateforme_de_destination(self, client, entetes, db_session):
        _, _, destination = await self._transfert(client, entetes, db_session)

        assert float(destination.quantity) == pytest.approx(0.5)

    async def test_supprimer_le_transfert_supprime_le_miroir_et_sa_quantite(self, client, entetes, db_session):
        actif_id, sortie, destination = await self._transfert(client, entetes, db_session)

        await client.delete(f"/api/v1/transactions/{sortie['id']}", headers=entetes)

        await db_session.refresh(destination)
        restantes = await db_session.execute(select(Transaction).where(Transaction.asset_id == destination.id))
        assert restantes.scalars().all() == []
        assert float(destination.quantity) == 0

    async def test_le_prix_de_revient_du_miroir_est_recalcule(self, client, entetes, db_session):
        """NEW-57 : le miroir aussi perd son prix de revient.

        La suppression recalculait celui de l'actif d'origine, mais pas celui
        de l'actif miroir — alors que `TRANSFER_IN` entre dans ce calcul.
        L'actif de destination conservait le prix de revient d'une transaction
        qui n'existait plus, sur une quantité pourtant devenue nulle.
        """
        actif_id, sortie, destination = await self._transfert(client, entetes, db_session)
        assert float(destination.avg_buy_price) > 0

        await client.delete(f"/api/v1/transactions/{sortie['id']}", headers=entetes)

        await db_session.refresh(destination)
        assert float(destination.avg_buy_price) == 0

    async def test_un_transfert_sans_date_ne_fait_plus_echouer_la_requete(self, client, entetes, db_session):
        """NEW-58 : `executed_at` est facultatif, le miroir ne le supposait pas.

        La détection de doublon compare la date du miroir à une fenêtre de
        ±1 jour. Sans date, la soustraction levait un `TypeError` qui remontait
        en **HTTP 500** sur une requête pourtant valide — et 43 des transferts
        sortants déjà en base n'ont pas de date.

        Le miroir est désormais créé ; seule la déduplication est sautée,
        faute de date sur laquelle la fonder.
        """
        _, _, destination = await self._transfert(client, entetes, db_session)

        assert float(destination.quantity) == pytest.approx(0.5)
