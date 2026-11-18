"""Mentions légales.

``SIMULATION_DISCLAIMER`` accompagne chaque aperçu du simulateur de stratégies, ``BACKTEST_NOTE`` chaque
simulation passée. ``AI_DISCLAIMER`` reste la mention générique « pas un conseil en investissement » que
``predictions/recommendation.py`` ajoute aux constats de prévision ; le simulateur ne l'utilise pas.
"""

SIMULATION_DISCLAIMER = (
    "Simulation calculée uniquement à partir des paramètres que vous avez saisis. "
    "Ce n'est pas un conseil en investissement ni une recommandation personnalisée : "
    "InvestAI ne choisit ni les actifs, ni les montants, ni le moment d'agir. "
    "Les performances passées ne préjugent pas des performances futures."
)

BACKTEST_NOTE = (
    "Simulation passée : ce que la règle aurait donné sur l'historique de prix enregistré, "
    "aux clôtures journalières, sans frais ni fiscalité. Elle n'a aucune valeur prédictive."
)

AI_DISCLAIMER = (
    "⚠️ Information à but éducatif uniquement, ne constitue pas un conseil en "
    "investissement. InvestAI n'est pas un conseiller financier agréé. Les "
    "performances passées ne préjugent pas des performances futures. Faites vos "
    "propres recherches et consultez un professionnel avant toute décision."
)
