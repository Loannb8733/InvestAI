"""Seuil de matérialité de l'invariant « holdings ».

Un contrôle qui reste rouge en permanence cesse d'être lu, et masque alors les
vraies violations. Deux familles d'écarts ne peuvent pourtant pas influencer le
patrimoine affiché :

- **position soldée** : sa valeur est négligeable, la valorisation ne porte plus
  sur rien. Constaté : 0,00000098 USDC, 0,00000202 ETH — moins d'un centime, sur
  des actifs que le dashboard n'affiche même pas ;
- **bruit d'arrondi** : un écart de 1,22e-8 SOL, soit un millionième d'euro, sur
  une position pourtant bien ouverte.

Elles restent listées en WARN — visibles, jamais bloquantes. Le code de sortie ne
dépend que des violations matérielles.

Fonction pure : ni base, ni réseau.
"""

from decimal import Decimal as D

import pytest

from scripts.check_invariants import MATERIALITY_DIFF_VALUE, MATERIALITY_VALUE, classify_holdings_gap


class TestPositionSoldee:
    @pytest.mark.parametrize(
        "stored,computed,pru",
        [
            (D("0.00000098"), D("-26.54599355"), D("0.93")),  # USDC Binance
            (D("0.00000202"), D("-0.00003188"), D("1946.41")),  # ETH Binance
            (D("0.00011088"), D("-0.00087508"), D("84.28")),  # SOL Binance
            (D("0"), D("109529"), D("0.0000001")),  # actif entièrement vidé
        ],
    )
    def test_ecart_sur_position_videe_est_non_materiel(self, stored, computed, pru):
        immaterial, raison = classify_holdings_gap(stored, computed, pru)
        assert immaterial is True
        assert "soldée" in raison


class TestBruitArrondi:
    def test_ecart_infime_sur_position_ouverte(self):
        # SOL Kraken : position à ~89 €, écart de 1,22e-8 unité.
        immaterial, raison = classify_holdings_gap(D("1.05798199"), D("1.057982002200"), D("84.28"))
        assert immaterial is True
        assert "arrondi" in raison


class TestViolationsReelles:
    def test_ecart_significatif_sur_position_ouverte(self):
        # 0,0033 BTC manquants sur une position de ~440 € : matériel.
        immaterial, _ = classify_holdings_gap(D("0.00780432"), D("0.00447511"), D("56134.35"))
        assert immaterial is False

    def test_position_juste_au_dessus_du_seuil(self):
        # Valeur de position = 2 €, écart valant 1 € : au-dessus des deux seuils.
        immaterial, _ = classify_holdings_gap(D("2"), D("1"), D("1"))
        assert immaterial is False

    def test_le_seuil_de_position_est_bien_applique(self):
        # Position à 0,99 € : sous le seuil de 1 €.
        immaterial, raison = classify_holdings_gap(D("0.99"), D("0.50"), D("1"))
        assert immaterial is True and "soldée" in raison


class TestRobustesse:
    def test_pru_nul_ne_leve_pas(self):
        # Sans prix de revient, tout vaut 0 : classé non matériel, jamais d'erreur.
        immaterial, _ = classify_holdings_gap(D("1000"), D("0"), D("0"))
        assert immaterial is True

    def test_ecart_nul(self):
        immaterial, _ = classify_holdings_gap(D("5"), D("5"), D("100"))
        assert immaterial is True  # écart nul => bruit

    def test_les_seuils_restent_conservateurs(self):
        # Garde-fou : un seuil trop large masquerait de vraies violations.
        assert MATERIALITY_VALUE <= D("5")
        assert MATERIALITY_DIFF_VALUE <= D("1")
