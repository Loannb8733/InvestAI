"""Recense les fichiers de `frontend/src` que rien n'importe.

Usage : `python3 scripts/balayage_code_mort_frontend.py` depuis la racine.

Pendant frontal de `balayage_code_mort.py`. Ces fichiers n'alourdissent pas le
bundle — Vite les exclut deja du graphe de dependances — mais ils se
maintiennent : les deux onglets de prediction trouves ici avaient ete portes de
recharts vers Nivo alors que rien ne les montait.

ESLint signale un import inutilise dans un fichier ; il ne dit rien d'un
fichier entier que personne n'importe. C'est ce trou que ce balayage couvre.

Precautions :
  - les pages montees par le routeur le sont souvent en `lazy(() => import(...))`
    avec un chemin : la recherche porte sur le chemin ET sur le nom du fichier ;
  - `main.tsx`, `App.tsx`, les fichiers de configuration et les tests sont des
    points d'entree : jamais importes, jamais morts ;
  - un fichier `index.ts` de barrel export est reference par son dossier.
"""
import pathlib
import re
import sys

RACINE = pathlib.Path('frontend/src')
ENTREES = {'main.tsx', 'App.tsx', 'vite-env.d.ts', 'setupTests.ts'}
JETON = re.compile(r'[A-Za-z_][A-Za-z0-9_]*')

fichiers = {}
for p in RACINE.rglob('*'):
    if p.suffix not in ('.ts', '.tsx') or not p.is_file():
        continue
    try:
        fichiers[p] = p.read_text()
    except (UnicodeDecodeError, OSError):
        pass

# Index : quel fichier mentionne quel jeton / quel chemin
mentions = {}
for p, txt in fichiers.items():
    for j in set(JETON.findall(txt)):
        mentions.setdefault(j, set()).add(p)
chemins_cites = ' '.join(fichiers.values())

orphelins = []
for p, txt in fichiers.items():
    if p.name in ENTREES or '.test.' in p.name or p.name == 'index.ts':
        continue
    tige = p.stem                       # PortfolioPage
    relatif = str(p.relative_to(RACINE)).rsplit('.', 1)[0]   # pages/PortfolioPage
    # Cite par son nom ailleurs ?
    par_nom = mentions.get(tige, set()) - {p}
    # Cite par son chemin (import '@/pages/PortfolioPage', './PortfolioPage') ?
    par_chemin = re.search(rf'''['"][^'"]*{re.escape(relatif)}['"]''', chemins_cites) \
        or re.search(rf'''['"][^'"]*/{re.escape(tige)}['"]''', chemins_cites)
    if not par_nom and not par_chemin:
        orphelins.append((p, len(txt.split('\n'))))

print(f"{len(fichiers)} fichiers examines")
print(f"\n=== Fichiers que rien n'importe ({len(orphelins)}) ===")
for p, n in sorted(orphelins, key=lambda x: -x[1]):
    print(f"  {n:5} l.  {p.relative_to(RACINE)}")
print(f"\nTotal : {sum(n for _, n in orphelins)} lignes")
sys.exit(0)
