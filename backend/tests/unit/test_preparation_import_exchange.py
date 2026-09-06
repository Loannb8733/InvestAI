"""Tests directs des fonctions extraites de `import_trade_history`.

Ces deux gestes — déchiffrer pour instancier le service, résoudre le
portefeuille « Crypto » — étaient recopiés à l'identique dans trois endpoints et
une tâche Celery. Enfermés dans un bloc de 1 174 lignes, ils n'étaient
atteignables qu'en montant tout l'import. Ils se testent maintenant seuls.
"""

from unittest.mock import patch

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.core.security import encrypt_api_key, hash_password
from app.models.portfolio import Portfolio
from app.models.user import User, UserRole
from app.services.exchange_import_preparation import (
    construire_service_exchange,
    fusionner_portefeuilles_herites,
    resoudre_portefeuille_crypto,
)


class CleFactice:
    def __init__(self, avec_secret=True, avec_phrase=False):
        self.exchange = "binance"
        self.encrypted_api_key = encrypt_api_key("ma-cle")
        self.encrypted_secret_key = encrypt_api_key("mon-secret") if avec_secret else None
        self.encrypted_passphrase = encrypt_api_key("ma-phrase") if avec_phrase else None


class ServiceEspion:
    recu = None

    def __init__(self, cle, secret, phrase):
        ServiceEspion.recu = (cle, secret, phrase)


class TestConstructionDuService:
    def test_les_trois_secrets_sont_dechiffres(self):
        with patch(
            "app.services.exchange_import_preparation.get_exchange_service",
            return_value=ServiceEspion,
        ):
            construire_service_exchange(CleFactice(avec_secret=True, avec_phrase=True))

        assert ServiceEspion.recu == ("ma-cle", "mon-secret", "ma-phrase")

    def test_secret_absent_reste_none(self):
        """Tous les exchanges n'exigent pas de secret : `None` doit passer tel
        quel, et non une chaîne vide déchiffrée."""
        with patch(
            "app.services.exchange_import_preparation.get_exchange_service",
            return_value=ServiceEspion,
        ):
            construire_service_exchange(CleFactice(avec_secret=False))

        assert ServiceEspion.recu == ("ma-cle", None, None)

    def test_le_service_correspond_a_l_exchange_de_la_cle(self):
        appels = []

        def faux_get(nom):
            appels.append(nom)
            return ServiceEspion

        with patch("app.services.exchange_import_preparation.get_exchange_service", faux_get):
            construire_service_exchange(CleFactice())

        assert appels == ["binance"]


@pytest.fixture
def user_id(regular_user):
    """Un identifiant réel : `portfolios.user_id` porte une clé étrangère."""
    return regular_user.id


@pytest_asyncio.fixture
async def autre_user_id(db_session):
    """Un second utilisateur, pour vérifier le cloisonnement."""
    voisin = User(
        email="voisin@test.com",
        password_hash=hash_password("motdepasse"),
        role=UserRole.USER,
        first_name="Voisin",
        last_name="Test",
    )
    db_session.add(voisin)
    await db_session.flush()
    return voisin.id


class TestResolutionDuPortefeuille:
    async def test_cree_le_portefeuille_quand_il_manque(self, db_session, user_id):
        portefeuille = await resoudre_portefeuille_crypto(db_session, user_id, "Binance")

        assert portefeuille.name == "Crypto"
        assert portefeuille.id is not None, "le flush doit donner un identifiant utilisable"

    async def test_rend_le_portefeuille_existant(self, db_session, user_id):
        premier = await resoudre_portefeuille_crypto(db_session, user_id, "Binance")
        second = await resoudre_portefeuille_crypto(db_session, user_id, "Binance")

        assert premier.id == second.id
        tous = (await db_session.execute(select(Portfolio).where(Portfolio.user_id == user_id))).scalars().all()
        assert len(tous) == 1, "aucun doublon ne doit être créé"

    async def test_renomme_un_portefeuille_herite(self, db_session, user_id):
        """Un compte d'avant la consolidation garde son historique : le
        portefeuille est renommé, pas abandonné au profit d'un neuf."""
        ancien = Portfolio(user_id=user_id, name="Binance", description="ancien")
        db_session.add(ancien)
        await db_session.flush()
        id_ancien = ancien.id

        portefeuille = await resoudre_portefeuille_crypto(db_session, user_id, "Binance")

        assert portefeuille.id == id_ancien
        assert portefeuille.name == "Crypto"

    async def test_sans_nom_d_exchange_aucun_heritage_n_est_repris(self, db_session, user_id):
        ancien = Portfolio(user_id=user_id, name="Binance", description="ancien")
        db_session.add(ancien)
        await db_session.flush()

        portefeuille = await resoudre_portefeuille_crypto(db_session, user_id, None)

        assert portefeuille.id != ancien.id
        assert ancien.name == "Binance", "l'ancien reste intact"

    async def test_le_portefeuille_d_un_autre_utilisateur_est_ignore(self, db_session, user_id, autre_user_id):
        autre = Portfolio(user_id=autre_user_id, name="Crypto", description="voisin")
        db_session.add(autre)
        await db_session.flush()

        portefeuille = await resoudre_portefeuille_crypto(db_session, user_id, "Binance")

        assert portefeuille.id != autre.id
        assert portefeuille.user_id == user_id


class TestFusionDesHeritages:
    async def test_fusionne_et_supprime_les_anciens(self, db_session, user_id):
        cible = await resoudre_portefeuille_crypto(db_session, user_id, None)
        for nom in ("Binance", "Kraken"):
            db_session.add(Portfolio(user_id=user_id, name=nom, description="ancien"))
        await db_session.flush()

        fusionnes = await fusionner_portefeuilles_herites(db_session, cible, user_id)

        assert fusionnes == 2
        restants = (await db_session.execute(select(Portfolio).where(Portfolio.user_id == user_id))).scalars().all()
        assert [p.name for p in restants] == ["Crypto"]

    async def test_additionne_les_soldes_en_especes(self, db_session, user_id):
        cible = await resoudre_portefeuille_crypto(db_session, user_id, None)
        cible.cash_balances = {"EUR": 100}
        db_session.add(
            Portfolio(
                user_id=user_id,
                name="Binance",
                description="a",
                cash_balances={"EUR": 50},
            )
        )
        await db_session.flush()

        await fusionner_portefeuilles_herites(db_session, cible, user_id)

        assert cible.cash_balances["EUR"] == 150

    async def test_ne_touche_pas_aux_portefeuilles_hors_liste(self, db_session, user_id):
        cible = await resoudre_portefeuille_crypto(db_session, user_id, None)
        db_session.add(Portfolio(user_id=user_id, name="Bourse", description="autre"))
        await db_session.flush()

        fusionnes = await fusionner_portefeuilles_herites(db_session, cible, user_id)

        assert fusionnes == 0
        noms = sorted(
            p.name
            for p in (await db_session.execute(select(Portfolio).where(Portfolio.user_id == user_id))).scalars().all()
        )
        assert noms == ["Bourse", "Crypto"]

    async def test_ne_se_fusionne_pas_avec_lui_meme(self, db_session, user_id):
        """La cible est exclue par son identifiant : sans cela, un portefeuille
        nommé « Binance » servant de cible se supprimerait lui-même."""
        cible = Portfolio(user_id=user_id, name="Binance", description="cible")
        db_session.add(cible)
        await db_session.flush()

        fusionnes = await fusionner_portefeuilles_herites(db_session, cible, user_id)

        assert fusionnes == 0
