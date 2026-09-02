"""Un remboursement se rapproche de l'échéance qu'il solde, pas de la plus proche en date.

Pourquoi c'est une règle et pas un détail
-----------------------------------------
L'appariement se faisait sur la seule distance de date. Deux échéances proches
dans le calendrier — un paiement décalé, un mois à cheval sur deux versements —
se départageaient alors sur quelques jours, alors que leurs **montants** les
distinguent franchement.

Le mauvais rapprochement ne se voit pas : l'échéance est marquée soldée, le
tableau de bord affiche un remboursement de plus, et l'écart n'apparaît qu'à la
fin du prêt, quand une échéance reste ouverte sans raison.

Aucune exposition mesurée sur les données actuelles — 59 échéances, aucune paire
à moins de quinze jours — mais c'est un piège qui s'arme dès qu'un projet a des
versements rapprochés.
"""

import uuid
from datetime import date
from decimal import Decimal

import pytest

from app.services.reconciliation_service import ReconciliationService


class EcheanceFactice:
    """Le strict nécessaire : ce que la fonction de rapprochement consulte."""

    def __init__(self, jour: str, capital: str, interets: str = "0"):
        self.id = uuid.uuid4()
        self.due_date = date.fromisoformat(jour)
        self.expected_capital = Decimal(capital)
        self.expected_interest = Decimal(interets)
        self.is_completed = False
        self.completed_at = None
        self.repayment_id = None


def rapprocher(echeances, jour_paiement: str, montant=None):
    """Applique le vrai classement du service, sans base de données.

    Le score est une méthode publique justement pour que ce test éprouve
    l'implémentation utilisée en production, et non une copie qui resterait
    verte si le service changeait.
    """
    service = ReconciliationService()
    paiement = date.fromisoformat(jour_paiement)
    montant_dec = Decimal(montant) if montant is not None else None
    return min(echeances, key=lambda e: service.score_rapprochement(e, paiement, montant_dec))


class TestLeMontantDepartage:
    def test_deux_echeances_proches_sont_departagees_par_le_montant(self):
        """Le cas que la date seule tranchait mal."""
        petite = EcheanceFactice("2026-03-05", "100.00")
        grosse = EcheanceFactice("2026-03-12", "850.00")

        # Paiement de 850 € le 7 mars : plus proche de la petite en date,
        # mais c'est manifestement la grosse qu'il solde.
        assert rapprocher([petite, grosse], "2026-03-07", "850.00") is grosse

    def test_sans_le_montant_la_date_decide_comme_avant(self):
        """Rétrocompatibilité : les appelants qui ne passent rien ne changent pas."""
        petite = EcheanceFactice("2026-03-05", "100.00")
        grosse = EcheanceFactice("2026-03-12", "850.00")
        assert rapprocher([petite, grosse], "2026-03-07") is petite

    def test_a_montant_egal_la_date_tranche(self):
        proche = EcheanceFactice("2026-03-05", "500.00")
        lointaine = EcheanceFactice("2026-06-05", "500.00")
        assert rapprocher([proche, lointaine], "2026-03-06", "500.00") is proche


class TestToleranceSurLesArrondis:
    def test_un_ecart_de_quelques_centimes_reste_une_correspondance(self):
        """La dernière échéance porte l'arrondi de toutes les précédentes."""
        cible = EcheanceFactice("2026-12-05", "412.37")
        autre = EcheanceFactice("2026-12-02", "100.00")
        assert rapprocher([cible, autre], "2026-12-04", "412.35") is cible

    def test_un_ecart_franc_n_est_pas_une_correspondance(self):
        """1 % sépare un arrondi d'une échéance différente."""
        cible = EcheanceFactice("2026-12-05", "412.37")
        autre = EcheanceFactice("2026-12-02", "100.00")
        # 380 € s'écarte de 8 % : aucune ne correspond, la date reprend la main.
        assert rapprocher([cible, autre], "2026-12-03", "380.00") is autre

    def test_le_capital_et_les_interets_comptent_ensemble(self):
        """Une échéance vaut capital + intérêts, pas le seul capital."""
        cible = EcheanceFactice("2026-05-05", "400.00", interets="50.00")
        autre = EcheanceFactice("2026-05-03", "400.00")
        assert rapprocher([cible, autre], "2026-05-04", "450.00") is cible


class TestCasLimites:
    def test_une_echeance_a_zero_ne_capte_pas_les_paiements(self):
        """Diviser par zéro n'a pas de sens : elle passe en second rang."""
        vide = EcheanceFactice("2026-04-05", "0")
        reelle = EcheanceFactice("2026-04-20", "300.00")
        assert rapprocher([vide, reelle], "2026-04-06", "300.00") is reelle

    @pytest.mark.parametrize("montant", ["0.00", "999999.00"])
    def test_un_montant_aberrant_ne_fait_pas_echouer_le_rapprochement(self, montant):
        a = EcheanceFactice("2026-04-05", "300.00")
        b = EcheanceFactice("2026-04-20", "300.00")
        assert rapprocher([a, b], "2026-04-06", montant) in (a, b)


class TestSignature:
    def test_le_montant_est_facultatif(self):
        import inspect

        params = inspect.signature(ReconciliationService.reconcile_repayment).parameters
        assert "amount" in params, "le montant n'est plus transmissible"
        assert params["amount"].default is None, "un montant obligatoire casserait les appelants qui ne l'ont pas"

    def test_l_endpoint_transmet_le_montant(self):
        from pathlib import Path

        import app.api.v1.endpoints.crowdfunding as module

        source = Path(module.__file__).read_text(encoding="utf-8")
        appel = source[source.index("reconcile_repayment(") :][:400]
        assert "amount=" in appel, "le montant n'est pas transmis : la pondération reste lettre morte"
