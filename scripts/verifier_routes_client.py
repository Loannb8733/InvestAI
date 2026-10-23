"""Chaque appel du client HTTP doit viser une route qui existe.

`frontend/src/services/api.ts` construit ses URL à la main. Rien ne les relie
aux routes que FastAPI déclare : une route renommée côté serveur, et l'appel
part en **404** — que le client traite comme une erreur réseau ordinaire.
L'écran affiche « une erreur est survenue », et rien ne dit que le chemin
n'existe plus.

Ce contrôle ne peut pas vivre dans la suite pytest : le conteneur backend ne
monte que `/app`, et n'a donc pas accès au frontend. Il tourne en CI, où le
dépôt entier est présent, et à la main depuis la racine :

    python3 scripts/verifier_routes_client.py

Sortie 0 si tout correspond, 1 sinon, avec la liste des chemins fautifs.
"""

from __future__ import annotations

import ast
import pathlib
import re
import sys

RACINE = pathlib.Path(__file__).resolve().parent.parent
BACKEND = RACINE / "backend"
CLIENT = RACINE / "frontend" / "src" / "services" / "api.ts"
PREFIXE = "/api/v1"  # baseURL du client
METHODES = {"get", "post", "put", "patch", "delete"}


def _fichier(module: str) -> pathlib.Path:
    return BACKEND.joinpath(*module.split(".")).with_suffix(".py")


def _routeurs_importes(arbre: ast.Module) -> dict[str, tuple[str, str]]:
    """Nom local -> (module du fichier, variable du routeur dans ce fichier)."""
    noms: dict[str, tuple[str, str]] = {}
    for noeud in arbre.body:
        if isinstance(noeud, ast.ImportFrom) and noeud.module and noeud.module.startswith("app."):
            for alias in noeud.names:
                local = alias.asname or alias.name
                if _fichier(f"{noeud.module}.{alias.name}").exists():
                    noms[local] = (f"{noeud.module}.{alias.name}", "router")
                else:
                    noms[local] = (noeud.module, alias.name)
    return noms


def _montages(arbre: ast.Module) -> list[tuple[str, str, str]]:
    """(module, variable du routeur, préfixe) de chaque include_router."""
    importes = _routeurs_importes(arbre)
    montages = []
    for noeud in ast.walk(arbre):
        if not (isinstance(noeud, ast.Call) and getattr(noeud.func, "attr", None) == "include_router"):
            continue
        prefixe = next(
            (k.value.value for k in noeud.keywords if k.arg == "prefix" and isinstance(k.value, ast.Constant)), ""
        )
        cible = noeud.args[0]
        if isinstance(cible, ast.Attribute) and isinstance(cible.value, ast.Name):
            module, _ = importes[cible.value.id]
            montages.append((module, cible.attr, prefixe))
        elif isinstance(cible, ast.Name):
            module, variable = importes[cible.id]
            montages.append((module, variable, prefixe))
    return montages


def routes_declarees() -> set[tuple[str, str]]:
    """Routes reconstituées par lecture du code, sans importer l'application.

    Importer `app.main` demanderait un environnement complet : `Settings`
    refuse les variables supplémentaires, et le `.env` de développement en
    porte trois destinées à docker-compose (`BACKEND_HOST`, `BACKEND_PORT`,
    `VITE_API_URL`). Le contrôle ne doit pas dépendre de cela — il lit les
    montages de `router.py` (routeurs des endpoints comme des domaines, alias
    compris) puis les décorateurs de chaque routeur.
    """
    arbre = ast.parse((BACKEND / "app" / "api" / "v1" / "router.py").read_text())
    routes: set[tuple[str, str]] = set()
    for module, variable, prefixe in _montages(arbre):
        for noeud in ast.walk(ast.parse(_fichier(module).read_text())):
            if not isinstance(noeud, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            for deco in noeud.decorator_list:
                if (
                    isinstance(deco, ast.Call)
                    and isinstance(deco.func, ast.Attribute)
                    and deco.func.attr in METHODES
                    and isinstance(deco.func.value, ast.Name)
                    and deco.func.value.id == variable
                    and deco.args
                    and isinstance(deco.args[0], ast.Constant)
                ):
                    complet = (PREFIXE + prefixe + deco.args[0].value).rstrip("/") or PREFIXE + prefixe
                    routes.add((deco.func.attr.upper(), complet))
    return routes


def appels_du_client() -> list[tuple[str, str]]:
    source = CLIENT.read_text()
    # api.get('/x'), api.post<T>(`/y/${id}`), api.delete("/z")
    trouves = re.findall(
        r"api\.(get|post|put|patch|delete)(?:<[^>]*>)?\(\s*([`'\"])([^`'\"]*)\2",
        source,
    )
    return [(verbe.upper(), chemin) for verbe, _, chemin in trouves]


def main() -> int:
    if not CLIENT.exists():
        print(f"Client introuvable : {CLIENT}")
        return 1

    motifs = [
        (methode, chemin, re.compile("^" + re.sub(r"\\\{[^}]+\\\}", "[^/]+", re.escape(chemin)) + "$"))
        for methode, chemin in routes_declarees()
    ]

    fautifs: list[tuple[str, str]] = []
    ignores = 0
    for verbe, chemin in appels_du_client():
        chemin = chemin.split("?")[0]
        if not chemin.startswith("/"):
            ignores += 1  # URL assemblée ailleurs : hors de portée de ce contrôle
            continue
        # Une interpolation `${...}` vaut un segment quelconque.
        concret = PREFIXE + re.sub(r"\$\{[^}]*\}", "x", chemin).rstrip("/")
        if not any(m == verbe and rx.match(concret) for m, _, rx in motifs):
            couple = (verbe, PREFIXE + chemin)
            if couple not in fautifs:
                fautifs.append(couple)

    total = len(appels_du_client())
    if fautifs:
        print(f"{len(fautifs)} appel(s) sans route correspondante, sur {total} :")
        for verbe, chemin in fautifs:
            print(f"  {verbe:7} {chemin}")
        return 1

    print(f"{total} appels vérifiés ({ignores} ignorés, URL construite ailleurs) — tous ont une route.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
