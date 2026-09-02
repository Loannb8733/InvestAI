"""L'espacement des appels CoinGecko doit être réel, et l'attente bornée.

Pourquoi c'est une règle et pas un détail
-----------------------------------------
`/predictions/market-cycle` mettait **65 secondes** à répondre, cache vide, et
le bandeau de régime restait en squelette pendant tout ce temps.

La cause n'était ni le nombre d'actifs (7, pas 56) ni l'absence de
parallélisme (`asyncio.gather` était déjà là) : c'était le verrou. Un
`Semaphore(5)` laissait cinq coroutines entrer ensemble dans la section
critique ; elles lisaient le même `_last_coingecko_call`, dormaient la même
durée et repartaient à la même milliseconde. Le délai de 1,2 s retardait donc
une rafale de cinq sans jamais l'espacer. CoinGecko répondait 429, et chaque
symbole payait 10 s + 20 s + 30 s de backoff pour finir sans donnée.

Sérialiser suffit : mesuré à 8,5 s au lieu de 65 s, avec les mêmes résultats.

Ces tests sont statiques : reproduire un quota épuisé demanderait de taper une
API tierce, et c'est la *structure* du verrou qui portait le défaut.
"""

import ast
import inspect
from pathlib import Path

import app.ml.historical_data as hd

_SOURCE = Path(hd.__file__).read_text(encoding="utf-8")


def _sans_commentaires(source: str) -> str:
    """Les commentaires citent ce qu'ils expliquent — les garder fausserait les tests."""
    lignes = [ligne.split("#")[0] if not ligne.strip().startswith("#") else "" for ligne in source.split("\n")]
    return "\n".join(lignes)


class TestVerrou:
    def test_les_appels_sont_serialises(self):
        """Un sémaphore > 1 rend le délai minimum inopérant."""
        assert isinstance(hd._coingecko_lock, __import__("asyncio").Lock), (
            "le verrou doit être un Lock : avec un Semaphore(n>1), les coroutines "
            "lisent le même horodatage et repartent ensemble, la rafale n'est pas espacée"
        )

    def test_aucun_semaphore_multiple_ne_reapparait(self):
        code = _sans_commentaires(_SOURCE)
        assert "Semaphore(" not in code, "un Semaphore réintroduit dans ce module rendrait l'espacement illusoire"

    def test_le_delai_minimum_couvre_le_palier_gratuit(self):
        # 50 requêtes/minute = 1,2 s entre deux appels.
        assert (
            hd._COINGECKO_MIN_DELAY >= 1.2
        ), f"délai de {hd._COINGECKO_MIN_DELAY}s : au-delà de 50 req/min, CoinGecko répond 429"

    def test_le_throttle_prend_le_verrou(self):
        src = inspect.getsource(hd._coingecko_throttle)
        assert "_coingecko_lock" in src, "le throttle n'utilise plus le verrou"
        assert "_COINGECKO_MIN_DELAY" in src, "le throttle n'applique plus de délai"


class TestAttenteBornee:
    """Une requête HTTP ne doit pas être immobilisée par le backoff d'une API tierce."""

    def _affectation_de_wait(self) -> str:
        """L'expression qui calcule l'attente dans le bloc traitant le 429."""
        arbre = ast.parse(_SOURCE)
        for noeud in ast.walk(arbre):
            if not isinstance(noeud, ast.If):
                continue
            bloc = ast.unparse(noeud)
            if "429" not in bloc or "sleep" not in bloc:
                continue
            for n in ast.walk(noeud):
                if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "wait" for t in n.targets):
                    return ast.unparse(n.value)
        raise AssertionError("calcul de l'attente introuvable dans le bloc 429")

    def test_l_attente_est_plafonnee(self):
        """Le plafond, pas la valeur littérale : `(attempt + 1) * 10` cumulait 60 s
        par symbole sans qu'aucune constante ne dépasse 10.

        Vérifié par canari : sans ce test, restaurer le backoff 10/20/30 laissait
        la suite au vert.

        Le plafond porte désormais sur les **tâches de fond** seules — une requête
        HTTP renonce sans attendre (voir `test_contexte_execution.py`). Il reste
        nécessaire : hors requête, une API qui répondrait `Retry-After: 3600`
        immobiliserait un worker une heure.
        """
        expression = self._affectation_de_wait()
        assert expression.startswith("min("), (
            f"l'attente n'est pas plafonnée : {expression!r} — une progression "
            "multipliée par le numéro de tentative dépasse la minute sans qu'aucune "
            "constante ne le laisse voir"
        )
        plafond = ast.literal_eval(expression.rsplit(",", 1)[1].rstrip(")").strip())
        assert plafond <= 60, f"plafond de {plafond}s : un worker resterait immobilisé trop longtemps"

    def test_retry_after_est_respecte(self):
        assert "Retry-After" in _SOURCE, (
            "quand l'API indique combien de temps patienter, deviner à sa place est " "à la fois impoli et moins juste"
        )


class TestBudgetGlobal:
    """Filet de sécurité indépendant du quota : le temps total est borné."""

    def test_le_cycle_de_marche_borne_ses_appels_externes(self):
        import app.services.prediction_cycles as pc

        source = Path(pc.__file__).read_text(encoding="utf-8")
        assert "_BUDGET_APPELS_EXTERNES" in source, "aucun budget de temps sur les données externes"
        assert "wait_for" in source, "le budget n'est pas appliqué : il faut un wait_for"
        assert (
            0 < pc._BUDGET_APPELS_EXTERNES <= 20
        ), f"budget de {pc._BUDGET_APPELS_EXTERNES}s : au-delà, l'écran reste figé trop longtemps"
