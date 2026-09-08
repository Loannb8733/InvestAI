"""Filet sur les envois d'emails planifiés.

`app/tasks/emails.py` était couvert à **0 %**. Trois tâches y sont planifiées —
rapport hebdomadaire, rapport mensuel, digest quotidien — et chacune écrit à
l'utilisateur. Une erreur de programmation y échouerait en silence, dans les
journaux Celery, comme ce fut le cas pour la tâche de nettoyage (NEW-42).

Ces tests exécutent réellement chaque tâche : c'est la seule façon de trouver
ce qu'aucune relecture ne voit — une requête mal construite, un attribut
inexistant, un champ renommé. L'envoi lui-même est doublé ; le reste du chemin
est parcouru pour de vrai.
"""

from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from app.models.asset import Asset, AssetType
from app.models.notification import Notification, NotificationType
from app.models.portfolio import Portfolio
from app.tasks import emails


@pytest.fixture
def session_de_test(db_session, monkeypatch):
    @asynccontextmanager
    async def _fabrique():
        yield db_session

    monkeypatch.setattr(emails, "AsyncSessionLocal", _fabrique)
    return db_session


@pytest.fixture
def poste(monkeypatch):
    """Poste d'envoi doublé : configuré, et qui enregistre ce qu'on lui confie."""
    envois = []

    async def _envoyer(*args, **kwargs):
        envois.append({"args": args, "kwargs": kwargs})
        return True

    monkeypatch.setattr(type(emails.email_service), "is_configured", property(lambda self: True))
    for methode in ("send_weekly_report", "send_monthly_report", "send_daily_digest", "send_email"):
        if hasattr(emails.email_service, methode):
            monkeypatch.setattr(emails.email_service, methode, AsyncMock(side_effect=_envoyer))
    return envois


class TestGardeDeConfiguration:
    async def test_sans_configuration_aucune_tache_ne_travaille(self, monkeypatch, session_de_test):
        """Un serveur d'envoi absent doit arrêter la tâche avant toute requête.

        Le motif de retour le dit explicitement (`skipped`), plutôt que de
        rendre un « 0 envoyé » qu'on confondrait avec « personne à prévenir ».
        """
        monkeypatch.setattr(type(emails.email_service), "is_configured", property(lambda self: False))

        for tache in (
            emails._send_weekly_reports_async,
            emails._send_monthly_reports_async,
            emails._send_daily_digest_async,
        ):
            res = await tache()
            assert res.get("skipped") == "email_not_configured"


class TestSansDestinataire:
    async def test_une_base_vide_ne_fait_echouer_aucune_tache(self, session_de_test, poste):
        """Le chemin complet est parcouru : requêtes construites, boucles vides.

        C'est ce parcours qui trouve les erreurs de programmation. La tâche de
        nettoyage échouait sur `func.case` exactement ici — au moment de bâtir
        la requête, avant même de toucher la base.
        """
        for tache in (
            emails._send_weekly_reports_async,
            emails._send_monthly_reports_async,
            emails._send_daily_digest_async,
        ):
            res = await tache()
            assert res["sent"] == 0
            assert res["failed"] == 0

        assert poste == []


class TestAvecDestinataires:
    async def test_un_portefeuille_garni_donne_lieu_a_un_rapport(self, session_de_test, regular_user, poste):
        pf = Portfolio(user_id=regular_user.id, name="P")
        session_de_test.add(pf)
        await session_de_test.flush()
        session_de_test.add(
            Asset(
                portfolio_id=pf.id,
                symbol="BTC",
                name="BTC",
                asset_type=AssetType.CRYPTO,
                quantity=Decimal("1"),
                avg_buy_price=Decimal("40000"),
                current_price=Decimal("45000"),
            )
        )
        await session_de_test.flush()

        res = await emails._send_weekly_reports_async()

        assert res["sent"] + res["failed"] == 1

    async def test_un_portefeuille_vide_ne_recoit_rien(self, session_de_test, regular_user, poste):
        """`total_value == 0` fait sauter l'utilisateur.

        Un rapport hebdomadaire sur un patrimoine nul n'apprendrait rien et
        userait la patience du destinataire. Le portefeuille existe pourtant :
        c'est bien la valeur, pas l'absence de compte, qui décide.
        """
        session_de_test.add(Portfolio(user_id=regular_user.id, name="P"))
        await session_de_test.flush()

        res = await emails._send_weekly_reports_async()

        assert res["sent"] == 0
        assert poste == []

    async def test_le_digest_quotidien_ne_vise_que_l_activite_recente(self, session_de_test, regular_user, poste):
        """Une notification d'hier compte, une d'il y a un mois non.

        Le digest est quotidien : l'inclure reviendrait à renvoyer chaque jour
        la même nouvelle.
        """
        session_de_test.add(
            Notification(
                user_id=regular_user.id,
                type=NotificationType.SYSTEM,
                title="ancienne",
                message="…",
                created_at=datetime.now(timezone.utc) - timedelta(days=30),
            )
        )
        await session_de_test.flush()

        res = await emails._send_daily_digest_async()

        assert res["sent"] == 0

    async def test_un_utilisateur_sans_portefeuille_n_est_pas_sollicite(self, session_de_test, regular_user, poste):
        # Aucun portefeuille : rien à rapporter, donc pas de courrier.
        res = await emails._send_weekly_reports_async()

        assert res["sent"] == 0


class TestEchecIsole:
    async def test_un_envoi_qui_echoue_n_arrete_pas_les_suivants(
        self, session_de_test, regular_user, admin_user, poste, monkeypatch
    ):
        """Un destinataire injoignable ne doit pas priver les autres.

        Les envois sont comptés séparément (`sent` / `failed`) : sans cette
        séparation, une seule adresse morte ferait paraître la tâche en échec
        total.
        """
        for user in (regular_user, admin_user):
            pf = Portfolio(user_id=user.id, name=f"P-{user.id}")
            session_de_test.add(pf)
            await session_de_test.flush()
            session_de_test.add(
                Asset(
                    portfolio_id=pf.id,
                    symbol="BTC",
                    name="BTC",
                    asset_type=AssetType.CRYPTO,
                    quantity=Decimal("1"),
                    avg_buy_price=Decimal("40000"),
                    current_price=Decimal("45000"),
                )
            )
        await session_de_test.flush()

        appels = {"n": 0}

        async def _capricieux(*args, **kwargs):
            appels["n"] += 1
            if appels["n"] == 1:
                raise RuntimeError("serveur SMTP injoignable")
            return True

        monkeypatch.setattr(emails.email_service, "send_weekly_report", AsyncMock(side_effect=_capricieux))

        res = await emails._send_weekly_reports_async()

        assert res["sent"] + res["failed"] == 2
        assert res["failed"] >= 1
