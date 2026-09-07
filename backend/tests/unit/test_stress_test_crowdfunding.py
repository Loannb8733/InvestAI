"""Filet de caractérisation du stress test de crowdfunding.

`stress_test_service` décale toutes les échéances d'un projet de N mois et
recalcule le TRI : « et si la plateforme payait avec six mois de retard ? ».
Le module était couvert à 43 %.

Le service travaille sur des objets ORM **détachés** — l'échéancier est
regénéré en mémoire, sans base — ce qui le rend testable directement.

Comportement actuel épinglé, pas spécification approuvée.
"""

from datetime import date
from decimal import Decimal

import pytest

from app.models.crowdfunding_project import CrowdfundingProject, RepaymentType
from app.services.stress_test_service import ALLOWED_DELAY_MONTHS, stress_test_service


def projet(**surcharges) -> CrowdfundingProject:
    """Projet in fine de 10 000 EUR à 9 % sur 24 mois, intérêts à l'échéance."""
    champs = {
        "platform": "Test",
        "invested_amount": Decimal("10000"),
        "annual_rate": Decimal("9"),
        "duration_months": Decimal("24"),
        "repayment_type": RepaymentType.IN_FINE,
        "start_date": date(2026, 1, 1),
        "estimated_end_date": date(2028, 1, 1),
        "interest_frequency": "at_maturity",
        "tax_rate": Decimal("30"),
        "delay_months": Decimal("0"),
        "total_received": Decimal("0"),
    }
    champs.update(surcharges)
    return CrowdfundingProject(**champs)


class TestTriDeBase:
    def test_un_projet_sain_a_un_tri_positif(self):
        res = stress_test_service.compute_stress_test(projet(), 0)

        assert res.base_irr is not None
        assert res.base_irr > 0

    def test_sans_retard_le_tri_stresse_egale_le_tri_de_base(self):
        """À délai nul, le service réutilise le TRI de base sans recalculer.

        Comme le filtre des échéances vides, ce raccourci est une **économie
        de calcul, pas une règle** : forcer le recalcul donnerait exactement la
        même valeur. Aucun test ne peut donc le tenir, et ce n'en est pas un
        qui manque — c'est l'égalité des deux TRI qui est épinglée ici, vraie
        dans les deux cas.
        """
        res = stress_test_service.compute_stress_test(projet(), 0)

        assert res.stressed_irr == res.base_irr

    def test_le_tri_est_rendu_en_pourcentage_arrondi_au_centieme(self):
        res = stress_test_service.compute_stress_test(projet(), 0)

        assert res.base_irr == round(res.base_irr, 2)
        # Un TRI de 6 % s'exprime 6.x, pas 0.06.
        assert 1 < res.base_irr < 100


class TestEffetDuRetard:
    def test_un_retard_degrade_le_tri(self):
        base = stress_test_service.compute_stress_test(projet(), 0).base_irr
        stresse = stress_test_service.compute_stress_test(projet(), 12).stressed_irr

        assert stresse < base

    def test_plus_le_retard_est_long_plus_le_tri_baisse(self):
        tris = [stress_test_service.compute_stress_test(projet(), d).stressed_irr for d in (0, 6, 12, 24)]

        assert tris == sorted(tris, reverse=True)

    def test_le_retard_ne_change_pas_le_tri_de_base(self):
        # Le point de comparaison reste le scénario contractuel.
        sans = stress_test_service.compute_stress_test(projet(), 0)
        avec = stress_test_service.compute_stress_test(projet(), 24)

        assert avec.base_irr == sans.base_irr

    def test_les_montants_recus_ne_changent_pas_avec_le_retard(self):
        """Un retard décale les encaissements, il ne les ampute pas.

        C'est ce qui distingue ce stress test d'un scénario de défaut : le
        capital et les intérêts restent dus en entier, seule leur date bouge.
        La perte est donc purement actuarielle.
        """
        sans = stress_test_service.compute_stress_test(projet(), 0)
        avec = stress_test_service.compute_stress_test(projet(), 12)

        assert sum(c.total for c in avec.cashflows) == sum(c.total for c in sans.cashflows)


class TestEcheancierAffiche:
    def test_les_dates_sont_decalees_du_nombre_de_mois_demande(self):
        sans = stress_test_service.compute_stress_test(projet(), 0).cashflows
        avec = stress_test_service.compute_stress_test(projet(), 6).cashflows

        assert date.fromisoformat(avec[-1].date) == date.fromisoformat(sans[-1].date).replace(month=7)

    def test_le_drapeau_de_retard_suit_le_scenario(self):
        assert all(not c.is_delayed for c in stress_test_service.compute_stress_test(projet(), 0).cashflows)
        assert all(c.is_delayed for c in stress_test_service.compute_stress_test(projet(), 6).cashflows)

    def test_le_total_de_chaque_echeance_est_la_somme_capital_interets(self):
        for flux in stress_test_service.compute_stress_test(projet(), 0).cashflows:
            assert flux.total == round(flux.capital + flux.interest, 2)

    def test_les_interets_affiches_sont_nets_d_impot(self):
        """Le taux d'imposition du projet est appliqué avant affichage.

        Un projet à 0 % — enveloppe défiscalisée — perçoit donc plus qu'un
        projet à 30 %, à conditions contractuelles identiques. C'est un piège
        connu du module : tester `if project.tax_rate` traiterait le 0 % comme
        une absence et le taxerait à 30 %.
        """
        taxe = stress_test_service.compute_stress_test(projet(tax_rate=Decimal("30")), 0)
        exonere = stress_test_service.compute_stress_test(projet(tax_rate=Decimal("0")), 0)

        interets_taxes = sum(c.interest for c in taxe.cashflows)
        interets_exoneres = sum(c.interest for c in exonere.cashflows)

        assert interets_exoneres > interets_taxes
        assert interets_taxes == pytest.approx(interets_exoneres * 0.7, rel=1e-3)


class TestAmortissable:
    def test_un_projet_amortissable_produit_plusieurs_echeances(self):
        res = stress_test_service.compute_stress_test(projet(repayment_type=RepaymentType.AMORTIZABLE), 0)

        assert len(res.cashflows) > 1
        assert res.base_irr is not None

    def test_l_amortissable_se_degrade_aussi_avec_le_retard(self):
        amortissable = projet(repayment_type=RepaymentType.AMORTIZABLE)
        base = stress_test_service.compute_stress_test(amortissable, 0).base_irr
        stresse = stress_test_service.compute_stress_test(amortissable, 12).stressed_irr

        assert stresse < base


class TestEcheancesNulles:
    """Un in fine à intérêts périodiques produit des échéances vides.

    Le capital ne tombe qu'à la fin et les intérêts ne sont versés qu'à
    l'échéance : les 11 lignes intermédiaires portent 0 en capital comme en
    intérêts.
    """

    def mensuel(self, **surcharges):
        return projet(
            interest_frequency="monthly",
            duration_months=Decimal("12"),
            estimated_end_date=date(2027, 1, 1),
            **surcharges,
        )

    def test_les_echeances_vides_sont_affichees_a_l_utilisateur(self):
        res = stress_test_service.compute_stress_test(self.mensuel(annual_rate=Decimal("0")), 0)

        vides = [c for c in res.cashflows if c.total == 0]

        assert len(res.cashflows) == 12
        assert len(vides) == 11

    def test_le_calcul_du_tri_les_ecarte_sans_changer_le_resultat(self):
        """`payment <= 0: continue` retire ces échéances des flux du TRI.

        Le garde-fou est **sans effet sur la valeur** : un flux nul ne pèse
        pas dans une VAN, et le TRI est identique qu'on lui passe 13 flux ou 2.
        C'est une économie de calcul, pas une correction — et le filtre ne vaut
        que pour le TRI, l'affichage gardant ses lignes vides.

        Le test ne peut donc pas tenir le garde-fou lui-même : il tient l'écart
        entre ce que l'utilisateur voit et ce qui est calculé.
        """
        res = stress_test_service.compute_stress_test(self.mensuel(annual_rate=Decimal("0")), 0)

        assert res.base_irr == pytest.approx(0.0, abs=1e-9)
        assert any(c.total == 0 for c in res.cashflows)


class TestCasLimites:
    def test_un_echeancier_vide_leve_une_erreur_explicite(self):
        # In fine sans date de fin estimée : `_generate_in_fine` rend une liste
        # vide, et le message oriente vers la date et la durée.
        with pytest.raises(ValueError, match="échéancier vide"):
            stress_test_service.compute_stress_test(projet(estimated_end_date=None), 0)

    def test_l_absence_de_date_de_debut_est_signalee_apres_l_echeancier(self):
        """L'ordre des contrôles décide du message.

        L'échéancier est généré **avant** que la date de début soit vérifiée.
        Un projet sans date de début mais avec une date de fin obtient donc le
        message « pas de date de début » ; s'il manque les deux, c'est
        « échéancier vide » qui l'emporte — exact, mais moins parlant.
        """
        with pytest.raises(ValueError, match="date de début"):
            stress_test_service.compute_stress_test(projet(start_date=None), 0)

        with pytest.raises(ValueError, match="échéancier vide"):
            stress_test_service.compute_stress_test(projet(start_date=None, estimated_end_date=None), 0)

    def test_le_service_accepte_un_retard_hors_de_la_liste_autorisee(self):
        """`ALLOWED_DELAY_MONTHS` n'est pas appliqué ici mais à l'endpoint.

        Appelé directement, le service calcule sans broncher un retard de trois
        mois. La validation vit dans `crowdfunding.py` : tout autre appelant
        contourne la liste.
        """
        assert ALLOWED_DELAY_MONTHS == {0, 6, 12, 24}

        res = stress_test_service.compute_stress_test(projet(), 3)

        assert res.delay_months == 3
        assert res.stressed_irr is not None

    def test_un_retard_negatif_avance_les_echeances(self):
        # `delay_months > 0` gouverne le décalage : une valeur négative laisse
        # les dates inchangées, et le TRI stressé se recalcule à l'identique.
        res = stress_test_service.compute_stress_test(projet(), -6)

        assert [c.date for c in res.cashflows] == [
            c.date for c in stress_test_service.compute_stress_test(projet(), 0).cashflows
        ]
        assert all(not c.is_delayed for c in res.cashflows)
