"""Filet sur l'import CSV de transactions.

`import_transactions_csv` fait **380 lignes** et n'avait aucun test. C'est le
chemin par lequel un historique entier entre dans la base en une requête : ses
décisions — quel actif créer, quelle ligne ignorer, quelle valeur borner — ne
produisent ni exception ni trace visible pour l'utilisateur, seulement des
compteurs.

Le filet épingle le comportement d'aujourd'hui, silences compris. Trois d'entre
eux sont commentés là où ils apparaissent : une ligne écartée sans être
comptée, un type que le lecteur de fichier connaît mais que la route refuse, et
un plafond qui tronque (NEW-59).
"""

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.core.security import create_access_token
from app.models.asset import Asset
from app.models.transaction import Transaction
from app.models.user import User

ENTETE_CSV = "symbol,type,quantity,price,fee,date,notes\n"


def csv(*lignes: str) -> bytes:
    return (ENTETE_CSV + "".join(ligne + "\n" for ligne in lignes)).encode()


@pytest.fixture
def entetes(regular_user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(subject=str(regular_user.id))}"}


async def _portefeuille(client: AsyncClient, entetes: dict) -> str:
    reponse = await client.post("/api/v1/portfolios", json={"name": "Portefeuille"}, headers=entetes)
    return reponse.json()["id"]


async def _importer(client: AsyncClient, entetes: dict, portefeuille: str, contenu: bytes, **parametres):
    requete = {"portfolio_id": portefeuille, **parametres}
    return await client.post(
        "/api/v1/transactions/import-csv",
        params=requete,
        files={"file": ("historique.csv", contenu, "text/csv")},
        headers=entetes,
    )


class TestRefus:
    async def test_un_fichier_qui_n_est_pas_un_csv_est_refuse(self, client, entetes):
        portefeuille = await _portefeuille(client, entetes)

        reponse = await client.post(
            "/api/v1/transactions/import-csv",
            params={"portfolio_id": portefeuille},
            files={"file": ("releve.pdf", b"%PDF-1.4", "application/pdf")},
            headers=entetes,
        )

        assert reponse.status_code == 400
        assert "CSV" in reponse.json()["detail"]

    async def test_sans_portefeuille_l_import_est_refuse(self, client, entetes):
        reponse = await client.post(
            "/api/v1/transactions/import-csv",
            files={"file": ("h.csv", csv("BTC,buy,1,30000,0,2026-01-15,"), "text/csv")},
            headers=entetes,
        )

        assert reponse.status_code == 400

    async def test_le_portefeuille_d_un_autre_utilisateur_est_introuvable(self, client, entetes, admin_user):
        autre = {"Authorization": f"Bearer {create_access_token(subject=str(admin_user.id))}"}
        portefeuille = await _portefeuille(client, autre)

        reponse = await _importer(client, entetes, portefeuille, csv("BTC,buy,1,30000,0,2026-01-15,"))

        assert reponse.status_code == 404

    async def test_une_plateforme_inconnue_est_refusee(self, client, entetes):
        portefeuille = await _portefeuille(client, entetes)

        reponse = await _importer(
            client, entetes, portefeuille, csv("BTC,buy,1,30000,0,2026-01-15,"), platform="Revolut"
        )

        assert reponse.status_code == 400

    async def test_un_format_non_reconnu_sans_plateforme_est_refuse(self, client, entetes):
        portefeuille = await _portefeuille(client, entetes)

        reponse = await _importer(client, entetes, portefeuille, b"colonne_a;colonne_b\n1;2\n")

        assert reponse.status_code == 400
        assert "non reconnu" in reponse.json()["detail"]


class TestImportNominal:
    async def test_l_actif_absent_est_cree_et_la_transaction_enregistree(self, client, entetes, db_session):
        portefeuille = await _portefeuille(client, entetes)

        reponse = await _importer(client, entetes, portefeuille, csv("BTC,buy,0.5,30000,10,2026-01-15 10:00:00,"))

        assert reponse.status_code == 200
        assert reponse.json()["success_count"] == 1
        assert reponse.json()["error_count"] == 0
        actif = (await db_session.execute(select(Asset).where(Asset.symbol == "BTC"))).scalar_one()
        assert float(actif.quantity) == pytest.approx(0.5)
        assert actif.exchange == "InvestAI / Generic"

    async def test_l_ordre_des_lignes_du_fichier_ne_change_pas_le_resultat(self, client, entetes, db_session):
        """Une vente écrite avant son achat donne la même quantité finale.

        La route trie bien le fichier par date avant de le parcourir, mais ce
        tri est **sans effet observable** : un second passage, après le commit,
        recalcule la quantité de chaque actif à partir de la somme de ses
        transactions. Retirer le tri ne fait échouer aucun test, et c'est
        normal — c'est le recalcul qui tient le résultat, pas l'ordre.

        Le test épingle donc ce qui protège réellement l'utilisateur : le fait
        qu'un fichier désordonné n'aboutisse pas à une quantité fausse.
        """
        portefeuille = await _portefeuille(client, entetes)

        reponse = await _importer(
            client,
            entetes,
            portefeuille,
            csv(
                "BTC,sell,1,40000,0,2026-02-10 10:00:00,",
                "BTC,buy,3,30000,0,2026-01-15 10:00:00,",
            ),
        )

        assert reponse.json()["success_count"] == 2
        actif = (await db_session.execute(select(Asset).where(Asset.symbol == "BTC"))).scalar_one()
        assert float(actif.quantity) == pytest.approx(2.0)

    async def test_les_frais_sont_libelles_dans_l_actif_echange(self, client, entetes, db_session):
        """`fee_currency` reçoit le symbole de l'actif dès que les frais sont
        non nuls — que le fichier les ait exprimés dans ce jeton ou en euros.

        Un CSV Crypto.com facture ses frais en euros ; ils seront donc lus comme
        des BTC en aval. La conversion des frais (NEW-21) s'en accommode, mais
        l'origine de l'ambiguïté est ici.
        """
        portefeuille = await _portefeuille(client, entetes)

        await _importer(client, entetes, portefeuille, csv("BTC,buy,1,30000,5,2026-01-15 10:00:00,"))

        transaction = (await db_session.execute(select(Transaction))).scalars().first()
        assert transaction.fee_currency == "BTC"

    async def test_des_frais_nuls_ne_donnent_pas_de_devise_de_frais(self, client, entetes, db_session):
        portefeuille = await _portefeuille(client, entetes)

        await _importer(client, entetes, portefeuille, csv("BTC,buy,1,30000,0,2026-01-15 10:00:00,"))

        transaction = (await db_session.execute(select(Transaction))).scalars().first()
        assert transaction.fee_currency is None


class TestLignesEcartees:
    async def test_une_devise_fiat_est_ecartee_sans_etre_comptee(self, client, entetes, db_session):
        """Ni succès ni erreur : la ligne disparaît des trois compteurs.

        L'utilisateur qui importe un relevé mêlant euros et cryptos voit un
        total inférieur au nombre de lignes de son fichier, sans explication.
        """
        portefeuille = await _portefeuille(client, entetes)

        reponse = await _importer(
            client,
            entetes,
            portefeuille,
            csv("EUR,buy,1000,1,0,2026-01-15 10:00:00,", "BTC,buy,1,30000,0,2026-01-16 10:00:00,"),
        )

        assert reponse.json() == {
            "success_count": 1,
            "error_count": 0,
            "skipped_count": 0,
            "errors": [],
            "created_transactions": reponse.json()["created_transactions"],
        }
        assert (await db_session.execute(select(func.count(Asset.id)))).scalar() == 1

    async def test_une_quantite_negligeable_est_ecartee_sans_etre_comptee(self, client, entetes):
        # Seuil à 1e-8 : la poussière de solde n'est pas importée, et ne compte
        # ni en succès ni en erreur.
        portefeuille = await _portefeuille(client, entetes)

        reponse = await _importer(
            client, entetes, portefeuille, csv("BTC,buy,0.000000001,30000,0,2026-01-15 10:00:00,")
        )

        assert reponse.json()["success_count"] == 0
        assert reponse.json()["error_count"] == 0

    async def test_un_type_inconnu_est_compte_en_erreur(self, client, entetes):
        portefeuille = await _portefeuille(client, entetes)

        reponse = await _importer(client, entetes, portefeuille, csv("BTC,donation,1,30000,0,2026-01-15 10:00:00,"))

        assert reponse.json()["error_count"] == 1
        assert "donation" in reponse.json()["errors"][0]

    async def test_le_staking_est_lu_par_le_fichier_mais_refuse_par_la_route(self, client, entetes):
        """Les deux tables de correspondance divergent.

        `GenericCSVParser` connaît « staking » et « unstaking » ; la table de la
        route ne les contient pas. Une ligne de staking traverse donc la lecture
        du fichier pour être rejetée juste après, avec un message qui la
        présente comme un type inconnu alors que le fichier l'a bien comprise.
        """
        portefeuille = await _portefeuille(client, entetes)

        reponse = await _importer(client, entetes, portefeuille, csv("BTC,staking,1,30000,0,2026-01-15 10:00:00,"))

        assert reponse.json()["error_count"] == 1
        assert "staking" in reponse.json()["errors"][0]


class TestDoublons:
    """Deux dispositifs se superposent, et un seul décide.

    La route construit une clé `(symbole, type, quantité, prix, seconde)` à
    partir des transactions déjà en base, puis, juste après, recalcule le
    `internal_hash` de chaque ligne et interroge la base une seconde fois.

    Le hash est **plus large** que la clé : il n'horodate qu'au *jour*
    (`%Y-%m-%d`), là où la clé descend à la seconde. Tout ce que la clé écarte,
    le hash l'écarte donc aussi — la clé est redondante, et la retirer ne fait
    échouer aucun test. Ce sont les tests qui suivent qui disent lequel des deux
    tranche vraiment.
    """

    async def test_deux_imports_du_meme_fichier_ne_doublent_pas_l_historique(self, client, entetes, db_session):
        portefeuille = await _portefeuille(client, entetes)
        fichier = csv("BTC,buy,1,30000,0,2026-01-15 10:00:00,")

        premier = await _importer(client, entetes, portefeuille, fichier)
        second = await _importer(client, entetes, portefeuille, fichier)

        assert premier.json()["success_count"] == 1
        assert second.json()["success_count"] == 0
        assert (await db_session.execute(select(func.count(Transaction.id)))).scalar() == 1

    async def test_deux_achats_identiques_du_meme_jour_sont_fusionnes(self, client, entetes, db_session):
        """C'est le hash qui tranche, et il ne voit que le jour (NEW-61).

        Deux achats de 1 BTC à 30 000 €, l'un le matin l'autre le soir du même
        jour — deux exécutions partielles d'un même ordre, ou deux achats
        programmés — portent le même hash et ne comptent que pour un. La clé de
        dédoublonnage, elle, les aurait distingués : elle descend à la seconde.

        Épinglé tel quel : élargir le hash toucherait aussi la synchronisation
        des exchanges, qui s'en sert pour ne pas réimporter l'historique.
        """
        portefeuille = await _portefeuille(client, entetes)

        reponse = await _importer(
            client,
            entetes,
            portefeuille,
            csv("BTC,buy,1,30000,0,2026-01-15 10:00:00,", "BTC,buy,1,30000,0,2026-01-15 18:30:00,"),
        )

        assert reponse.json()["success_count"] == 1
        actif = (await db_session.execute(select(Asset).where(Asset.symbol == "BTC"))).scalar_one()
        assert float(actif.quantity) == pytest.approx(1.0)

    async def test_une_ligne_repetee_dans_le_meme_fichier_n_est_prise_qu_une_fois(self, client, entetes, db_session):
        portefeuille = await _portefeuille(client, entetes)
        ligne = "BTC,buy,1,30000,0,2026-01-15 10:00:00,"

        reponse = await _importer(client, entetes, portefeuille, csv(ligne, ligne))

        assert reponse.json()["success_count"] == 1
        actif = (await db_session.execute(select(Asset).where(Asset.symbol == "BTC"))).scalar_one()
        assert float(actif.quantity) == pytest.approx(1.0)

    async def test_deux_achats_a_la_meme_seconde_mais_de_prix_differents_sont_distincts(
        self, client, entetes, db_session
    ):
        # La clé de dédoublonnage retient le prix : deux exécutions partielles
        # d'un même ordre restent deux transactions.
        portefeuille = await _portefeuille(client, entetes)

        reponse = await _importer(
            client,
            entetes,
            portefeuille,
            csv("BTC,buy,1,30000,0,2026-01-15 10:00:00,", "BTC,buy,1,30001,0,2026-01-15 10:00:00,"),
        )

        assert reponse.json()["success_count"] == 2


class TestPlafondNumerique:
    async def test_une_quantite_de_memecoin_passe_entiere(self, client, entetes, db_session):
        """NEW-59 : le plafond de 1e10 rognait des avoirs légitimes.

        `create_transaction` a déjà connu ce défaut et l'a corrigé — son
        commentaire le dit mot pour mot : « la limite globale de 1e10 tronquait
        à tort les gros avoirs légitimes (mèmecoins à forte offre comme
        SHIB/PEPE) sans erreur ». Les plafonds y ont été relevés à la capacité
        réelle des colonnes et le dépassement est journalisé.

        Le correctif n'avait pas été reporté sur l'import CSV, qui gardait
        l'ancienne borne — et, contrairement à la création unitaire, ne
        journalisait rien. Un import de 50 milliards de SHIB s'enregistrait à
        9 999 999 999, soit **cinq fois moins**, et la ligne était comptée en
        succès.

        Le portefeuille détient déjà 12,7 millions de PEPE : l'ordre de grandeur
        n'est pas théorique, il manque un facteur 800.
        """
        portefeuille = await _portefeuille(client, entetes)

        reponse = await _importer(
            client, entetes, portefeuille, csv("SHIB,buy,50000000000,0.00001,0,2026-01-15 10:00:00,")
        )

        assert reponse.json()["success_count"] == 1
        assert reponse.json()["error_count"] == 0
        actif = (await db_session.execute(select(Asset).where(Asset.symbol == "SHIB"))).scalar_one()
        assert float(actif.quantity) == pytest.approx(50_000_000_000)

    async def test_les_lignes_deja_presentes_sont_comptees_a_part(self, client, entetes):
        """NEW-60 : un import tout en doublons ne disait plus rien.

        `skipped` était compté puis jeté. Réimporter un fichier déjà traité
        renvoyait `0 succès, 0 erreur` — que l'interface affichait en « Échec de
        l'import — 0 erreurs détectées », le pire message possible : un échec
        annoncé, aucune erreur à montrer, aucune explication.

        C'est pourtant le troisième dénouement possible d'un import, à côté du
        succès et de l'erreur, et il a désormais sa place dans la réponse.
        """
        portefeuille = await _portefeuille(client, entetes)
        fichier = csv("BTC,buy,1,30000,0,2026-01-15 10:00:00,", "ETH,buy,2,2000,0,2026-01-16 10:00:00,")

        premier = await _importer(client, entetes, portefeuille, fichier)
        second = await _importer(client, entetes, portefeuille, fichier)

        assert (premier.json()["success_count"], premier.json()["skipped_count"]) == (2, 0)
        assert (second.json()["success_count"], second.json()["skipped_count"]) == (0, 2)
        assert second.json()["error_count"] == 0
