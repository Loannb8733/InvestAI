"""L'effort mensuel affiché sur un objectif (FIN-07, second point d'appel).

`_build_response` calculait les mois restants en divisant les jours par 30,44,
alors que `GoalProjectionService` compte des mois calendaires depuis FIN-07.
Les deux chiffres s'affichent à l'utilisateur sous le même libellé.

Ces tests exercent la fonction de production, pas une copie locale.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from dateutil.relativedelta import relativedelta

from app.api.v1.endpoints.goals import _build_response
from app.models.goal import Goal
from app.services.goal_projection_service import GoalProjectionService


def _objectif(*, restant: Decimal, echeance: date) -> Goal:
    """Objectif minimal : seuls les champs lus par `_build_response`."""
    return Goal(
        id=None,
        name="Test",
        target_amount=restant,
        current_amount=Decimal("0"),
        currency="EUR",
        target_date=None,
        deadline_date=echeance,
        goal_type=None,
        priority=None,
        strategy_type=None,
        status=None,
        icon=None,
        color=None,
        notes=None,
        created_at=None,
    )


class TestMoisCalendaires:
    def test_echeance_imminente_ne_gonfle_pas_le_montant(self):
        """À un jour du terme, il reste le montant — pas 30 fois le montant.

        C'est le cas que `jours / 30,44` rendait absurde : 0,03 mois
        transformait 10 000 € restants en 304 400 €/mois.
        """
        objectif = _objectif(restant=Decimal("10000"), echeance=date.today() + timedelta(days=1))
        assert _build_response(objectif)["monthly_needed"] == 10000.00

    @pytest.mark.parametrize("jours", [1, 5, 15, 29])
    def test_dernier_mois_plancher_a_un_mois(self, jours):
        """Sous un mois calendaire, le plancher évite la division par une fraction."""
        objectif = _objectif(restant=Decimal("1200"), echeance=date.today() + timedelta(days=jours))
        assert _build_response(objectif)["monthly_needed"] == 1200.00

    def test_un_an_donne_douze_mois(self):
        objectif = _objectif(restant=Decimal("12000"), echeance=date.today() + relativedelta(years=1))
        assert _build_response(objectif)["monthly_needed"] == 1000.00

    def test_six_mois(self):
        objectif = _objectif(restant=Decimal("3000"), echeance=date.today() + relativedelta(months=6))
        assert _build_response(objectif)["monthly_needed"] == 500.00


class TestCoherenceAvecLaProjection:
    """Les deux écrans affichent le même chiffre pour le même objectif."""

    @pytest.mark.parametrize("mois", [1, 2, 3, 6, 12, 24, 60, 120])
    def test_meme_chiffre_que_le_service_de_projection(self, mois):
        restant = Decimal("10000")
        echeance = date.today() + relativedelta(months=mois)

        via_endpoint = _build_response(_objectif(restant=restant, echeance=echeance))["monthly_needed"]

        ecart = relativedelta(echeance, date.today())
        mois_calendaires = max(ecart.years * 12 + ecart.months, 1)
        via_service = round(
            GoalProjectionService().compute_rmc(0.0, float(restant), mois_calendaires),
            2,
        )

        assert via_endpoint == via_service


class TestComportementPreserve:
    def test_objectif_atteint_pas_d_effort(self):
        objectif = _objectif(restant=Decimal("1000"), echeance=date.today() + relativedelta(months=6))
        objectif.current_amount = Decimal("1000")
        assert _build_response(objectif)["monthly_needed"] is None

    def test_echeance_passee_pas_d_effort(self):
        objectif = _objectif(restant=Decimal("1000"), echeance=date.today() - timedelta(days=1))
        reponse = _build_response(objectif)
        assert reponse["monthly_needed"] is None
        assert reponse["days_remaining"] == 0

    def test_montant_reste_borne(self):
        """Le garde-fou de sérialisation tient toujours."""
        objectif = _objectif(restant=Decimal("999999999999"), echeance=date.today() + timedelta(days=10))
        assert _build_response(objectif)["monthly_needed"] == 9_999_999.99
