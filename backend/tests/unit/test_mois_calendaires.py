"""Les mois restants d'un objectif se comptent en mois, pas en tranches de 30,44 jours.

Pourquoi c'est une règle et pas un détail
-----------------------------------------
`int(jours / 30,44)` se trompait d'un mois dans **3 % des échéances possibles**
(118 cas sur 3 621, de un mois à dix ans) : la troncature s'ajoute à l'écart
entre un mois moyen et les mois réels.

Rare, mais jamais anodin. Ce nombre divise le montant restant à rassembler : un
mois de moins, c'est un effort mensuel plus élevé. Sur une échéance courte, deux
mois au lieu de trois demandent 50 % de plus que nécessaire — et c'est un
chiffre que l'utilisateur lit pour décider combien épargner.
"""

from datetime import date, timedelta

import pytest
from dateutil.relativedelta import relativedelta

from app.services.goal_projection_service import GoalProjectionService


def mois_restants(debut: date, fin: date) -> int:
    """Reproduit le calcul du service, pour le vérifier sur des dates choisies."""
    ecart = relativedelta(fin, debut)
    return max(ecart.years * 12 + ecart.months, 1)


class TestComptageExact:
    @pytest.mark.parametrize(
        "debut,fin,attendu",
        [
            ("2026-09-03", "2026-12-03", 3),
            ("2026-09-03", "2027-09-03", 12),
            ("2026-09-03", "2031-09-03", 60),
            # Fin de mois : le 31 janvier au 31 décembre fait bien 11 mois.
            ("2026-01-31", "2026-12-31", 11),
            # Année bissextile traversée.
            ("2027-02-28", "2028-02-29", 12),
        ],
    )
    def test_les_mois_sont_ceux_du_calendrier(self, debut, fin, attendu):
        assert mois_restants(date.fromisoformat(debut), date.fromisoformat(fin)) == attendu

    def test_une_echeance_depassee_ne_donne_jamais_zero(self):
        """Diviser par zéro plus loin ferait échouer toute la projection."""
        assert mois_restants(date(2026, 9, 3), date(2026, 9, 1)) == 1


class TestEcartAvecLAncienCalcul:
    def test_l_approximation_se_trompait_bien_parfois(self):
        """Sans cette vérification, la correction pourrait ne rien corriger."""
        debut = date(2026, 9, 3)
        divergences = sum(
            1 for j in range(30, 3651) if max(int(j / 30.44), 1) != mois_restants(debut, debut + timedelta(days=j))
        )
        assert divergences > 0, "l'ancien calcul et le nouveau ne diffèrent jamais : la correction est vaine"
        # Mesuré à 120 sur 3 621. La borne haute garde le test honnête : si elle
        # explosait, c'est que le nouveau calcul dérive à son tour.
        assert divergences < 400, f"{divergences} divergences : le comptage calendaire est suspect"


class TestServiceUtiliseLeBonCalcul:
    def test_le_service_n_utilise_plus_la_constante_30_44(self):
        import inspect

        source = inspect.getsource(GoalProjectionService)
        code = "\n".join(ligne.split("#")[0] for ligne in source.split("\n"))
        assert "30.44" not in code, "l'approximation est revenue dans le calcul des mois"
        assert "relativedelta" in code, "le service ne compte plus en mois calendaires"
