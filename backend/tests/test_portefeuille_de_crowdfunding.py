"""Le portefeuille de crowdfunding se reconnaît à son marqueur, non à son nom.

Il était retrouvé — ou créé — par `Portfolio.name == "Crowdfunding"`, à la casse
exacte, tandis que l'écran l'écartait de la page Portefeuille par
`name.toLowerCase() !== 'crowdfunding'`. Deux règles pour une même question.

Conséquence d'un geste banal, que rien n'empêche : **renommer** ce portefeuille
dispersait les projets à venir dans un second portefeuille créé par le serveur,
tout en faisant réapparaître les actifs existants dans la page Portefeuille
(NEW-68).

Une colonne `kind` porte désormais cette nature, et le nom redevient ce qu'il
doit être : un libellé que l'utilisateur peut changer.
"""

import uuid

import pytest
from sqlalchemy import func, select

from app.api.v1.endpoints.crowdfunding import resoudre_portefeuille_crowdfunding
from app.models.portfolio import PORTEFEUILLE_CROWDFUNDING, Portfolio
from app.models.user import User


@pytest.fixture
async def portefeuille_marque(db_session, regular_user: User) -> Portfolio:
    p = Portfolio(
        id=uuid.uuid4(),
        user_id=regular_user.id,
        name="Crowdfunding",
        kind=PORTEFEUILLE_CROWDFUNDING,
    )
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p)
    return p


async def _resoudre(db_session, utilisateur) -> Portfolio:
    """Appelle la résolution du serveur — celle-ci, non une copie.

    Une première version de ce fichier rejouait la requête à la main. Un canari
    l'a démasquée : revenir à `name == "Crowdfunding"` dans l'endpoint ne faisait
    échouer aucun test, puisque aucun ne passait par lui.
    """
    return await resoudre_portefeuille_crowdfunding(db_session, utilisateur.id)


class TestReconnaissance:
    async def test_un_portefeuille_renomme_reste_reconnu(self, db_session, regular_user, portefeuille_marque):
        """Le cœur du correctif.

        Sous l'ancienne règle, ce renommage rendait le portefeuille invisible au
        serveur, qui en créait un second au projet suivant — les projets se
        répartissant alors entre deux portefeuilles, sans que rien ne le dise.
        """
        portefeuille_marque.name = "Mes prêts participatifs"
        await db_session.commit()

        assert (await _resoudre(db_session, regular_user)).id == portefeuille_marque.id

    async def test_un_portefeuille_existant_sans_marqueur_est_retrouve_et_marque(self, db_session, regular_user):
        """Le repli sur le nom, pour ce qui a été créé avant le marqueur.

        La migration marque les portefeuilles existants ; ce repli couvre ceux
        qu'elle n'aurait pas vus, et le cas d'une base restaurée d'avant.
        """
        ancien = Portfolio(id=uuid.uuid4(), user_id=regular_user.id, name="Crowdfunding")
        db_session.add(ancien)
        await db_session.commit()

        trouve = await _resoudre(db_session, regular_user)

        assert trouve.id == ancien.id
        assert trouve.kind == PORTEFEUILLE_CROWDFUNDING, "marqué au passage, le nom cesse de compter"

    async def test_un_portefeuille_ordinaire_n_est_jamais_confondu(self, db_session, regular_user):
        """Un portefeuille sans marqueur reste hors de portée.

        La résolution en crée alors un nouveau, dédié — c'est son rôle — plutôt
        que de détourner celui des cryptos.
        """
        ordinaire = Portfolio(id=uuid.uuid4(), user_id=regular_user.id, name="Crypto")
        db_session.add(ordinaire)
        await db_session.commit()

        trouve = await _resoudre(db_session, regular_user)

        assert trouve.id != ordinaire.id
        assert trouve.kind == PORTEFEUILLE_CROWDFUNDING

    async def test_le_portefeuille_d_un_autre_utilisateur_n_est_pas_repris(
        self, db_session, regular_user, admin_user, portefeuille_marque
    ):
        # Le marqueur ne dispense pas de la portée : chacun a le sien.
        trouve = await _resoudre(db_session, admin_user)

        assert trouve.id != portefeuille_marque.id
        assert trouve.user_id == admin_user.id

    async def test_un_seul_portefeuille_de_crowdfunding_par_utilisateur(
        self, db_session, regular_user, portefeuille_marque
    ):
        """Ce que le défaut produisait : deux portefeuilles pour un même usage.

        Après renommage, l'ancienne règle ne reconnaissait plus rien et créait
        un doublon. Le marqueur l'empêche.
        """
        portefeuille_marque.name = "Prêts"
        await db_session.commit()
        await _resoudre(db_session, regular_user)

        compte = await db_session.execute(
            select(func.count())
            .select_from(Portfolio)
            .where(Portfolio.user_id == regular_user.id, Portfolio.kind == PORTEFEUILLE_CROWDFUNDING)
        )
        assert compte.scalar() == 1
