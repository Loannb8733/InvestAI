"""Briques pures du 2086 : taux du PFU par année de revenus et registre du prix total d'acquisition."""

from decimal import Decimal as D

import pytest

from app.domains.reports.tax_ledger import PortfolioLedger
from app.domains.reports.tax_rates import EXEMPTION_THRESHOLD, percent, pfu_rates


class TestTauxDuPfu:
    @pytest.mark.parametrize("annee", [2019, 2023, 2024])
    def test_jusqu_aux_revenus_2024_le_pfu_est_de_30_pour_cent(self, annee):
        taux = pfu_rates(annee)

        assert (taux.ir, taux.ps, taux.total) == (D("0.128"), D("0.172"), D("0.300"))
        assert taux.label == "30,0 % (12,8 % + 17,2 %)"

    @pytest.mark.parametrize("annee", [2025, 2026])
    def test_des_les_revenus_2025_le_pfu_est_de_31_4_pour_cent(self, annee):
        """LFSS 2026 art. 12 : CSG de 9,2 % à 10,6 % sur les revenus du patrimoine, dès l'imposition des revenus 2025."""
        taux = pfu_rates(annee)

        assert (taux.ir, taux.ps, taux.total) == (D("0.128"), D("0.186"), D("0.314"))
        assert taux.label == "31,4 % (12,8 % + 18,6 %)"

    def test_le_seuil_d_exoneration(self):
        assert EXEMPTION_THRESHOLD == D("305")
        assert percent(D("0.186")) == "18,6 %"


class TestRegistre:
    def test_exemple_officiel_bofip_110(self):
        registre = PortfolioLedger()
        registre.acquire(D("1000"))

        c1 = registre.cede(D("450"), D("0"), D("1200"))
        c2 = registre.cede(D("1300"), D("0"), D("1300"))

        assert (c1.fraction, c1.gain) == (D("375"), D("75"))
        assert (c2.net_acquisition_cost, c2.fraction, c2.gain) == (D("625"), D("625"), D("675"))

    def test_exemple_a_trois_cessions_avec_frais_et_achat_intercale(self):
        registre = PortfolioLedger()
        registre.acquire(D("4000"))
        registre.acquire(D("2000"))
        c1 = registre.cede(D("1500"), D("15"), D("7500"))
        registre.acquire(D("1000"))
        c2 = registre.cede(D("2000"), D("20"), D("5000"))
        c3 = registre.cede(D("3000"), D("30"), D("6000"))

        assert [c.fraction for c in (c1, c2, c3)] == [D("1200"), D("2320"), D("1740")]
        assert [c.gain for c in (c1, c2, c3)] == [D("285"), D("-340"), D("1230")]
        assert [(c.acquisition_cost_gross, c.prior_fractions) for c in (c1, c2, c3)] == [
            (D("6000"), D("0")),
            (D("7000"), D("1200")),
            (D("7000"), D("3520")),
        ]
        assert sum(c.net_price for c in (c1, c2, c3)) == D("6435")

    def test_une_valeur_de_portefeuille_incomplete_est_relevee_au_prix_cede(self):
        """V comprend l'actif cédé, donc V ≥ C : sinon la fraction dépasserait le PTA net."""
        registre = PortfolioLedger()
        registre.acquire(D("1000"))

        cession = registre.cede(D("500"), D("0"), D("0"))

        assert cession.portfolio_value == D("500")
        assert cession.fraction == D("1000")
        assert registre.cede(D("100"), D("0"), D("100")).fraction == D("0")
