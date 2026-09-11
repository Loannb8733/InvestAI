"""L'échec d'envoi d'une alerte Telegram doit se voir en production.

Il était journalisé en DEBUG, niveau invisible en production. L'alerte restait
marquée déclenchée et notifiée dans l'application — un autre chemin — mais le
canal Telegram se perdait sans trace : un utilisateur qui compte sur Telegram
ne l'aurait jamais su.

Même famille que l'instantané quotidien du tableau de bord et que le
rattrapage des hashs : un échec qui existe sans que personne puisse le voir.

Test de forme, faute d'un chemin léger vers `check_all_alerts` : il vérifie
dans le code même que le gestionnaire d'erreur qui entoure l'envoi Telegram
n'est pas silencieux.
"""

import ast
import inspect

from app.services import alert_service as module


def _gestionnaires_autour_de(appel: str) -> list[ast.ExceptHandler]:
    """Les `except` dont le `try` contient un appel à `appel`."""
    arbre = ast.parse(inspect.getsource(module))
    trouves = []
    for noeud in ast.walk(arbre):
        if not isinstance(noeud, ast.Try):
            continue
        corps_appelle = any(
            isinstance(n, ast.Attribute) and n.attr == appel for instr in noeud.body for n in ast.walk(instr)
        )
        if corps_appelle:
            trouves.extend(noeud.handlers)
    return trouves


def _niveaux_journalises(gestionnaire: ast.ExceptHandler) -> set[str]:
    return {
        n.func.attr
        for instr in gestionnaire.body
        for n in ast.walk(instr)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr in {"debug", "info", "warning", "error", "exception", "critical"}
    }


def test_l_envoi_telegram_est_bien_entoure_d_une_garde():
    # Sans garde, un Telegram en panne ferait échouer tout le contrôle des
    # alertes : la garde doit exister, c'est son niveau qui compte.
    assert _gestionnaires_autour_de("send_smart_alert")


def test_son_echec_n_est_pas_journalise_en_debug():
    for gestionnaire in _gestionnaires_autour_de("send_smart_alert"):
        niveaux = _niveaux_journalises(gestionnaire)
        assert "debug" not in niveaux, "DEBUG est invisible en production : l'alerte perdue ne se verrait pas"
        assert niveaux & {"warning", "error", "exception"}, "l'échec doit laisser une trace visible"
