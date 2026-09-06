"""Un import qui échoue ne doit rien laisser en base.

Les gestionnaires d'erreur appelaient `classify_and_mark_error` puis
`db.commit()`. L'intention était de garder la trace de l'échec sur la clé —
mais `commit()` valide **toute la session**, pas seulement ce marquage.

Or ces blocs enveloppent des imports qui écrivent au fil de l'eau : mesuré
avant correction, `import_trade_history` comptait 7 `db.add()` et 8
`db.flush()` répartis sur un `try` de 1 147 lignes, pour un seul `commit()`
normal à la toute fin. Une erreur survenant dans l'un des 1 065 lignes situées
avant ce commit faisait donc valider les écritures en attente : un import
interrompu laissait en base une moitié de transactions.

C'est la mécanique des écritures fantômes de NEW-02/NEW-03, sous une autre
forme.
"""

from uuid import uuid4

import pytest

from app.services.exchange_error_classifier import rollback_puis_marquer


class CleFactice:
    def __init__(self, cle_id):
        self.id = cle_id
        self.appels = []

    def mark_auth_failure(self, message):
        self.appels.append(("auth", message))

    def mark_rate_limited(self, message):
        self.appels.append(("debit", message))

    def mark_error(self, message):
        self.appels.append(("generique", message))


class SessionFactice:
    """Journalise l'ordre des opérations : c'est lui qui est en cause."""

    def __init__(self, cle=None):
        self.journal = []
        self._cle = cle

    async def rollback(self):
        self.journal.append("rollback")

    async def commit(self):
        self.journal.append("commit")

    async def get(self, modele, identifiant):
        self.journal.append("get")
        return self._cle


@pytest.fixture
def cle_id():
    return uuid4()


class TestOrdreDesOperations:
    async def test_le_rollback_precede_le_commit(self, cle_id):
        """Sans cet ordre, le commit validerait l'import partiel."""
        cle = CleFactice(cle_id)
        db = SessionFactice(cle)

        await rollback_puis_marquer(db, object, cle_id, Exception("panne"))

        assert db.journal.index("rollback") < db.journal.index("commit")

    async def test_la_cle_est_rechargee_apres_le_rollback(self, cle_id):
        """Le rollback expire les objets : toucher l'ancienne instance
        déclencherait un chargement paresseux hors contexte async."""
        db = SessionFactice(CleFactice(cle_id))

        await rollback_puis_marquer(db, object, cle_id, Exception("panne"))

        assert db.journal == ["rollback", "get", "commit"]

    async def test_un_seul_commit(self, cle_id):
        db = SessionFactice(CleFactice(cle_id))
        await rollback_puis_marquer(db, object, cle_id, Exception("panne"))
        assert db.journal.count("commit") == 1


class TestMarquageDeLaCle:
    async def test_l_echec_reste_inscrit_sur_la_cle(self, cle_id):
        """Le rollback ne doit pas faire perdre la trace de l'erreur."""
        cle = CleFactice(cle_id)
        await rollback_puis_marquer(SessionFactice(cle), object, cle_id, Exception("timeout réseau"))
        assert cle.appels == [("generique", "timeout réseau")]

    async def test_une_erreur_d_authentification_reste_qualifiee(self, cle_id):
        cle = CleFactice(cle_id)
        await rollback_puis_marquer(SessionFactice(cle), object, cle_id, Exception("EAPI:Invalid key"))
        assert cle.appels == [("auth", "EAPI:Invalid key")]


class TestCleDisparue:
    async def test_cle_supprimee_entre_temps(self, cle_id):
        """Suppression concurrente : rien à marquer, et surtout pas de commit
        qui validerait l'import partiel que le rollback vient d'annuler."""
        db = SessionFactice(cle=None)

        await rollback_puis_marquer(db, object, cle_id, Exception("panne"))

        assert db.journal == ["rollback", "get"]
        assert "commit" not in db.journal
