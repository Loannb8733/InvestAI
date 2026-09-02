"""Une entrée de cache écrite par un schéma antérieur ne doit pas casser l'écran.

Pourquoi c'est une règle et pas un détail
-----------------------------------------
`GET /api/v1/dashboard?days=0` — l'option « Tout » du sélecteur de période —
répondait **500**. Les autres valeurs passaient.

La cause n'est pas dans le calcul : c'est le cache. L'entrée `days=0` avait
survécu à une évolution de `EnhancedDashboardResponse`, qui a gagné des champs
(`active_alerts`, `upcoming_events`, `advanced_metrics`, `last_updated`…). Le
dict relu ne pouvait plus construire le modèle, et l'exception Pydantic
remontait en 500 — jusqu'à expiration du TTL.

C'est un piège qui se réarme à **chaque** ajout de champ au schéma : les
utilisateurs dont le cache est chaud voient un 500 pendant que les autres non.
Un cache qu'on ne sait plus relire est un cache absent, pas une erreur.
"""

import ast
import inspect

import pytest
from pydantic import ValidationError

from app.api.v1.endpoints import dashboard as module_dashboard


class TestFiletSurLeCache:
    def test_la_lecture_du_cache_est_protegee(self):
        source = inspect.getsource(module_dashboard.get_dashboard)
        arbre = ast.parse(source.lstrip())

        # Le `EnhancedDashboardResponse(**cached)` doit vivre dans un try/except.
        protege = False
        for noeud in ast.walk(arbre):
            if not isinstance(noeud, ast.Try):
                continue
            corps = ast.unparse(noeud.body)
            if "cached" in corps and "EnhancedDashboardResponse" in corps:
                gerees = " ".join(ast.unparse(h.type) for h in noeud.handlers if h.type)
                if "ValidationError" in gerees or "Exception" in gerees:
                    protege = True
        assert protege, (
            "la reconstruction depuis le cache n'est pas protégée : un champ ajouté "
            "au schéma renverra 500 à tous ceux dont le cache est chaud"
        )

    def test_le_schema_refuse_bien_un_dict_incomplet(self):
        """Le filet n'a de sens que si Pydantic rejette réellement l'ancien format."""
        from app.api.v1.endpoints.dashboard import EnhancedDashboardResponse

        with pytest.raises(ValidationError):
            EnhancedDashboardResponse(**{"total_value": 2849.06, "forex_stale": False})

    def test_l_incident_est_journalise(self):
        source = inspect.getsource(module_dashboard.get_dashboard)
        assert "logger.warning" in source or "logger.error" in source, (
            "un cache illisible doit laisser une trace : sans elle, le recalcul "
            "silencieux masque une incompatibilité de schéma"
        )


class TestDaysZeroEstUnCasPrevu:
    def test_days_zero_est_accepte_par_la_signature(self):
        """« Tout » n'est pas une valeur limite exotique : elle est documentée."""
        query = inspect.signature(module_dashboard.get_dashboard).parameters["days"].default
        # FastAPI range les contraintes dans `metadata` (annotated-types), pas en
        # attributs directs : `query.ge` n'existe pas.
        bornes = {type(c).__name__: getattr(c, type(c).__name__.lower(), None) for c in query.metadata}
        assert (
            bornes.get("Ge") == 0
        ), f"days=0 doit rester accepté — c'est l'option « Tout » du sélecteur de période ; bornes : {bornes}"

    def test_la_semantique_de_days_zero_est_documentee(self):
        doc = inspect.getdoc(module_dashboard.get_dashboard) or ""
        assert "days=0" in doc, "la signification de days=0 doit rester écrite noir sur blanc"
