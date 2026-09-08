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

import pathlib
import re
import sys

RACINE = pathlib.Path(__file__).resolve().parent.parent
CLIENT = RACINE / "frontend" / "src" / "services" / "api.ts"
PREFIXE = "/api/v1"  # baseURL du client


def routes_declarees() -> set[tuple[str, str]]:
    """Routes reconstituées par lecture du code, sans importer l'application.

    Importer `app.main` demanderait un environnement complet : `Settings`
    refuse les variables supplémentaires, et le `.env` de développement en
    porte trois destinées à docker-compose (`BACKEND_HOST`, `BACKEND_PORT`,
    `VITE_API_URL`). Le contrôle ne doit pas dépendre de cela — il lit les
    décorateurs et les préfixes.
    """
    endpoints = RACINE / "backend" / "app" / "api" / "v1"
    montages = re.findall(
        r"include_router\(\s*(\w+)\.router\s*,\s*prefix=\"([^\"]*)\"",
        (endpoints / "router.py").read_text(),
    )

    routes: set[tuple[str, str]] = set()
    for module, prefixe in montages:
        fichier = endpoints / "endpoints" / f"{module}.py"
        if not fichier.exists():
            continue
        for methode, chemin in re.findall(
            r"@router\.(get|post|put|patch|delete)\(\s*[\"']([^\"']*)[\"']",
            fichier.read_text(),
        ):
            complet = (PREFIXE + prefixe + chemin).rstrip("/") or PREFIXE + prefixe
            routes.add((methode.upper(), complet))
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
