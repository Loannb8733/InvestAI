"""Matérialité des écarts d'invariants financiers.

Partagé par ``scripts/check_invariants.py`` (contrôle manuel) et par
``/api/v1/cron/invariants-check`` (watchdog hebdomadaire) : les deux doivent
juger un écart de la même façon, sinon l'alerte automatique et le rapport local
divergent.
"""

from decimal import Decimal

# En dessous de cette valeur (quantité × prix de revient, en devise du portefeuille),
# une position est considérée comme SOLDÉE : un écart entre son historique et son
# solde ne peut plus influencer le patrimoine affiché, puisque la valorisation se
# fait sur une quantité négligeable.
#
# Ces écarts restent signalés — en WARN, sans faire échouer le contrôle. Un
# invariant qui reste rouge en permanence sur des poussières finit par n'être plus
# lu, et masque les vraies violations. Constaté : 3 écarts résiduels portant sur
# 0,00000098 USDC, 0,00011088 SOL et 0,00000202 ETH — soit moins d'un centime au
# total, sur des actifs que le dashboard n'affiche même pas.
MATERIALITY_VALUE = Decimal("1.00")

# Un écart dont la valeur est inférieure à ce montant est du bruit d'arrondi, pas une
# incohérence — même sur une position bien ouverte. Sans ce second critère, un écart
# de 1,22e-8 SOL (soit un millionième d'euro) était signalé comme violation.
MATERIALITY_DIFF_VALUE = Decimal("0.01")


def classify_holdings_gap(stored: Decimal, computed: Decimal, pru: Decimal):
    """Un écart de holdings est-il matériel ? Renvoie ``(immaterial, raison)``.

    Deux cas ne peuvent pas influencer le patrimoine affiché :
    - la position est soldée (sa valeur est négligeable), donc la valorisation ne
      porte plus sur rien ;
    - l'écart lui-même vaut moins d'un centime : c'est du bruit d'arrondi.

    Les signaler en ERROR rendait ce contrôle rouge en permanence — et un contrôle
    toujours rouge finit par n'être plus lu, ce qui masque les vraies violations.
    Ils restent listés, en WARN, sans faire échouer le script.

    Fonction pure : testable sans base.
    """
    position_value = abs(stored) * pru
    diff_value = abs(stored - computed) * pru
    if position_value < MATERIALITY_VALUE:
        return True, f"position soldée, valeur {position_value:.4f} — sans impact"
    if diff_value < MATERIALITY_DIFF_VALUE:
        return True, f"écart de {diff_value:.6f} — bruit d'arrondi"
    return False, ""
