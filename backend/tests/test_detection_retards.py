"""Filet sur la détection des retards de paiement du crowdfunding.

`check_crowdfunding_delays` tourne chaque jour à 8 h 30 UTC : elle passe les
projets en retard au statut « delayed » et prévient l'utilisateur. Sa décision
repose entièrement sur `reconciliation_service.get_overdue_entries`.

La tâche elle-même n'est pas exécutable ici — sa logique vit dans une closure
appelée par `run_async`, qui installe une boucle d'événements neuve puis la
ferme (voir `async_runner`). C'est donc la requête qui décide, testée sur le
même chemin de code.

Ce qui compte ici, ce sont les **abstentions** : une échéance dans le délai de
grâce, une échéance déjà réglée, un projet clos. Une détection trop large
enverrait des alertes de retard pour des paiements arrivés à l'heure.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.models.asset import Asset, AssetType
from app.models.crowdfunding_payment_schedule import CrowdfundingPaymentSchedule
from app.models.crowdfunding_project import CrowdfundingProject, ProjectStatus, RepaymentType
from app.models.portfolio import Portfolio
from app.services.reconciliation_service import reconciliation_service


@pytest.fixture
async def projet(db_session, regular_user):
    pf = Portfolio(user_id=regular_user.id, name="P")
    db_session.add(pf)
    await db_session.flush()
    actif = Asset(
        portfolio_id=pf.id,
        symbol="PROJ",
        name="Projet",
        asset_type=AssetType.CROWDFUNDING,
        quantity=Decimal("1"),
        avg_buy_price=Decimal("1000"),
    )
    db_session.add(actif)
    await db_session.flush()
    p = CrowdfundingProject(
        asset_id=actif.id,
        platform="Test",
        project_name="Résidence",
        invested_amount=Decimal("1000"),
        annual_rate=Decimal("9"),
        duration_months=Decimal("12"),
        repayment_type=RepaymentType.IN_FINE,
        status=ProjectStatus.ACTIVE,
    )
    db_session.add(p)
    await db_session.flush()
    return p


async def _echeance(db, projet, *, jours_avant, reglee=False):
    e = CrowdfundingPaymentSchedule(
        project_id=projet.id,
        due_date=date.today() - timedelta(days=jours_avant),
        expected_capital=Decimal("0"),
        expected_interest=Decimal("75"),
        is_completed=reglee,
    )
    db.add(e)
    await db.flush()
    return e


class TestDelaiDeGrace:
    async def test_une_echeance_depassee_au_dela_du_delai_est_signalee(self, db_session, projet):
        await _echeance(db_session, projet, jours_avant=10)

        retards = await reconciliation_service.get_overdue_entries(db_session, grace_days=5)

        assert len(retards) == 1

    async def test_une_echeance_dans_le_delai_de_grace_ne_l_est_pas(self, db_session, projet):
        """Cinq jours de battement absorbent les virements du vendredi soir.

        Sans ce délai, chaque week-end produirait des alertes de retard pour
        des paiements arrivés à l'heure.
        """
        await _echeance(db_session, projet, jours_avant=3)

        retards = await reconciliation_service.get_overdue_entries(db_session, grace_days=5)

        assert retards == []

    async def test_le_delai_est_un_parametre_et_non_une_constante(self, db_session, projet):
        await _echeance(db_session, projet, jours_avant=3)

        strict = await reconciliation_service.get_overdue_entries(db_session, grace_days=1)

        assert len(strict) == 1


class TestAbstentions:
    async def test_une_echeance_deja_reglee_est_ignoree(self, db_session, projet):
        await _echeance(db_session, projet, jours_avant=30, reglee=True)

        retards = await reconciliation_service.get_overdue_entries(db_session, grace_days=5)

        assert retards == []

    async def test_un_projet_termine_ne_produit_plus_d_alerte(self, db_session, projet):
        """Seuls les projets **actifs** sont surveillés.

        Un projet clos ou déjà marqué en retard garde ses échéances non
        réglées : les inclure réenverrait l'alerte chaque jour.
        """
        projet.status = ProjectStatus.COMPLETED
        await _echeance(db_session, projet, jours_avant=30)

        retards = await reconciliation_service.get_overdue_entries(db_session, grace_days=5)

        assert retards == []

    async def test_un_projet_deja_en_retard_n_est_plus_resignale(self, db_session, projet):
        projet.status = ProjectStatus.DELAYED
        await _echeance(db_session, projet, jours_avant=30)

        retards = await reconciliation_service.get_overdue_entries(db_session, grace_days=5)

        assert retards == []


class TestPlusieursEcheances:
    async def test_chaque_echeance_en_retard_est_rendue(self, db_session, projet):
        # La tâche regroupe ensuite par projet pour ne changer le statut
        # qu'une fois ; la requête, elle, ne filtre pas.
        for jours in (10, 40, 70):
            await _echeance(db_session, projet, jours_avant=jours)

        retards = await reconciliation_service.get_overdue_entries(db_session, grace_days=5)

        assert len(retards) == 3
        assert {p.id for _, p in retards} == {projet.id}
