"""Recense les fonctions de `app/` que rien n'appelle.

Usage : `python3 scripts/balayage_code_mort.py` depuis la racine du dépôt.

Deux sorties : les fonctions qu'aucun code n'appelle, et celles que seuls des
tests appellent — mortes en production, mais dont la suppression emporterait
leurs tests, donc à trancher au cas par cas.

Un index inverse des identifiants est construit en une passe. Sans lui, la
recherche naive (une regex par nom, sur chaque fichier) ne terminait pas — elle
scannait aussi `backend/.venv`, dont le nom commence par un point et echappait
au filtre initial : 11 675 fichiers au lieu de ~250.

Precautions apprises des faux negatifs precedents :
  - endpoints FastAPI, taches Celery, validateurs et proprietes sont DECORES :
    jamais appeles par leur nom, donc exclus ;
  - une methode de mixin est appelee via `self.` depuis une autre classe : la
    recherche porte sur tout le depot, pas sur le fichier ;
  - les tests comptent a part — ce qu'eux seuls appellent est mort en
    production, mais sa suppression se discute autrement ;
  - les noms de moins de 6 caracteres sont ecartes (bruit de recherche).
"""
import ast
import pathlib
import re
import sys

EXCLUS = {'venv', '.venv', 'node_modules', '__pycache__', '.git',
          'site-packages', 'dist', 'build', 'alembic'}
RACINE = pathlib.Path('backend/app')
DECOS = {'router', 'app', 'task', 'shared_task', 'celery', 'property', 'setter',
         'validator', 'field_validator', 'model_validator', 'root_validator', 'listens_for', 'hybrid_property',
         'staticmethod', 'classmethod', 'lru_cache', 'cached_property', 'fixture',
         'websocket', 'on_event', 'exception_handler', 'middleware'}
JETON = re.compile(r'[A-Za-z_][A-Za-z0-9_]*')


def pertinent(p):
    return not (EXCLUS & set(p.parts))


def noms_deco(d):
    """Tous les noms d'un decorateur : `@router.get(...)` donne router ET get.

    Ne retenir que l'attribut laissait passer chaque endpoint FastAPI — 187
    « fonctions mortes » qui etaient en fait des routes. La base du decorateur
    est ce qui les identifie.
    """
    if isinstance(d, ast.Name):
        return {d.id}
    if isinstance(d, ast.Attribute):
        return {d.attr} | noms_deco(d.value)
    if isinstance(d, ast.Call):
        return noms_deco(d.func)
    return set()


definitions = {}
for f in RACINE.rglob('*.py'):
    if not pertinent(f):
        continue
    try:
        arbre = ast.parse(f.read_text())
    except (SyntaxError, UnicodeDecodeError):
        continue
    for n in ast.walk(arbre):
        if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if n.name.startswith('__') or len(n.name) < 6:
            continue
        if any(noms_deco(d) & DECOS for d in n.decorator_list):
            continue
        definitions[n.name] = (str(f), n.lineno, (n.end_lineno or n.lineno) - n.lineno + 1)

index_src, index_test, corps_par_fichier = {}, {}, {}
for base, motifs in (('backend', ('*.py',)), ('scripts', ('*.py',)),
                     ('frontend/src', ('*.ts', '*.tsx'))):
    racine = pathlib.Path(base)
    if not racine.exists():
        continue
    for motif in motifs:
        for p in racine.rglob(motif):
            if not pertinent(p):
                continue
            try:
                txt = p.read_text()
            except (UnicodeDecodeError, OSError):
                continue
            corps_par_fichier[str(p)] = txt
            cible = index_test if ('test' in p.name or 'tests' in p.parts) else index_src
            for j in set(JETON.findall(txt)):
                cible.setdefault(j, set()).add(str(p))

print(f"{len(corps_par_fichier)} fichiers indexes, {len(definitions)} fonctions examinees")

mortes, seulement_tests = [], []
for nom, (fichier, ligne, taille) in definitions.items():
    if index_src.get(nom, set()) - {fichier}:
        continue
    if len(JETON.findall(corps_par_fichier.get(fichier, ''))) and \
       len(re.findall(rf'\b{re.escape(nom)}\b', corps_par_fichier.get(fichier, ''))) > 1:
        continue
    en_test = index_test.get(nom, set())
    (seulement_tests if en_test else mortes).append((nom, fichier, ligne, taille, len(en_test)))


def afficher(titre, lot):
    print(f"\n=== {titre} ({len(lot)}) ===")
    for nom, f, l, t, nb in sorted(lot, key=lambda x: -x[3]):
        suffixe = f"  [{nb} fichier(s) de test]" if nb else ""
        print(f"  {t:4} l.  {nom:46} {f.replace('backend/app/', '')}:{l}{suffixe}")
    return sum(x[3] for x in lot)


a = afficher("Jamais appelees, nulle part", mortes)
b = afficher("Appelees seulement par des tests", seulement_tests)
print(f"\nTotal : {a} + {b} = {a + b} lignes concernees")
sys.exit(0)
