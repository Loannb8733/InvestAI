"""Un contrôle de révocation contourné doit être visible, et un statut de tâche privé.

Pourquoi ces deux règles
------------------------
**Le niveau de log n'est pas cosmétique.** Quand Redis est injoignable, quatre
chemins laissent passer : la vérification de blocklist sur l'access token et sur
le refresh token, et la mise en blocklist des deux au logout. Le choix du
fail-open est assumé — un token expire de lui-même — mais l'événement doit
remonter : l'intégration logging de Sentry transforme les ERROR en événements,
là où un WARNING ne laisse qu'un fil d'Ariane que personne ne consulte. Ces
quatre sites étaient en WARNING : le fail-open était décidé, mais muet.

Le cas du logout est le plus trompeur : l'utilisateur voit « déconnecté » alors
qu'un token déjà exfiltré reste accepté — jusqu'à 7 jours pour un refresh token.

**L'entropie n'est pas un contrôle d'accès.** `import-status` ne vérifiait pas le
propriétaire du `task_id`. Un `uuid4` n'est pas énumérable, mais il peut fuiter
par un journal, un référent ou un partage d'écran ; l'identifiant secret n'est
pas une autorisation.

Tests statiques : ces chemins ne s'atteignent qu'avec un Redis en panne et une
session authentifiée. La propriété vérifiée est structurelle.
"""

import ast
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
_DEPS = (_BACKEND / "app" / "api" / "deps.py").read_text(encoding="utf-8")
_AUTH = (_BACKEND / "app" / "api" / "v1" / "endpoints" / "auth.py").read_text(encoding="utf-8")
_KEYS = (_BACKEND / "app" / "api" / "v1" / "endpoints" / "api_keys.py").read_text(encoding="utf-8")


def _appels_logger(source: str) -> list:
    """[(niveau, message)] pour chaque logger.<niveau>("...") du fichier."""
    appels = []
    for noeud in ast.walk(ast.parse(source)):
        if not isinstance(noeud, ast.Call):
            continue
        f = noeud.func
        if not (isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) and f.value.id == "logger"):
            continue
        msg = noeud.args[0].value if noeud.args and isinstance(noeud.args[0], ast.Constant) else ""
        appels.append((f.attr, msg if isinstance(msg, str) else ""))
    return appels


def test_les_quatre_fail_open_de_revocation_sont_en_error():
    """Un WARNING ici ne déclenche aucune alerte : le fail-open passerait inaperçu."""
    trouves = []
    for source in (_DEPS, _AUTH):
        for niveau, msg in _appels_logger(source):
            bas = msg.lower()
            concerne = ("blocklist" in bas or "revocation" in bas or "revoked" in bas) and "redis" in bas
            if concerne:
                trouves.append((niveau, msg))
                assert niveau == "error", f"fail-open de révocation loggué en {niveau} au lieu de error : {msg!r}"

    assert len(trouves) == 4, (
        f"4 sites attendus (vérif access + refresh, révocation des deux au logout), {len(trouves)} trouvé(s) : "
        f"{[m for _, m in trouves]}"
    )


def test_les_messages_de_fail_open_sont_identifiables():
    """Un préfixe stable rend la règle d'alerte possible côté supervision."""
    for source in (_DEPS, _AUTH):
        for niveau, msg in _appels_logger(source):
            bas = msg.lower()
            if ("blocklist" in bas or "revocation" in bas or "revoked" in bas) and "redis" in bas:
                assert msg.startswith("SECURITY:"), f"message de fail-open sans préfixe SECURITY: {msg!r}"


def _fonction(source: str, nom: str):
    for noeud in ast.walk(ast.parse(source)):
        if isinstance(noeud, (ast.FunctionDef, ast.AsyncFunctionDef)) and noeud.name == nom:
            return noeud
    raise AssertionError(f"fonction {nom} introuvable")


def test_import_status_verifie_le_proprietaire():
    src = ast.unparse(_fonction(_KEYS, "get_import_status"))
    assert "user_id" in src, "get_import_status ne consulte pas le propriétaire de la tâche"
    assert "current_user.id" in src, "le propriétaire n'est pas comparé à l'utilisateur courant"


def test_import_status_ne_distingue_pas_absente_et_interdite():
    """Un 403 distinct confirmerait l'existence du task_id à un tiers."""
    fn = _fonction(_KEYS, "get_import_status")
    codes = [
        kw.value.attr
        for n in ast.walk(fn)
        if isinstance(n, ast.Raise) and isinstance(n.exc, ast.Call)
        for kw in n.exc.keywords
        if kw.arg == "status_code" and isinstance(kw.value, ast.Attribute)
    ]
    assert codes, "get_import_status ne lève plus d'erreur : le contrôle a disparu"
    assert all("404" in c for c in codes), f"réponse distincte pour une tâche d'autrui : {codes}"


def test_le_proprietaire_est_enregistre_a_la_creation():
    assert '"user_id": str(current_user.id)' in _KEYS, (
        "aucune tâche d'import ne mémorise son propriétaire : la vérification "
        "d'ownership rejetterait alors tout le monde"
    )


def test_l_identifiant_du_proprietaire_ne_fuit_pas_dans_la_reponse():
    src = ast.unparse(_fonction(_KEYS, "get_import_status"))
    assert "!= 'user_id'" in src or '!= "user_id"' in src, (
        "le user_id stocké doit être retiré de la réponse, sinon la route "
        "expose l'identifiant interne du propriétaire"
    )
