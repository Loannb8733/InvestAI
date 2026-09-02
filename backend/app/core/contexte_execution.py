"""Sait-on qu'on sert une requête HTTP, ou qu'on travaille en tâche de fond ?

Pourquoi cette distinction existe
---------------------------------
Face à un 429, la bonne conduite dépend entièrement de qui attend :

- une **tâche Celery** n'a personne en face. Respecter le `Retry-After` d'une
  API — quinze secondes, parfois plus — est exactement ce qu'il faut faire ;
- une **requête HTTP** a un utilisateur devant un écran. La même attente le fait
  patienter pour une donnée qu'un cache ou PostgreSQL sait déjà fournir.

Sans cette distinction, il faut choisir un compromis unique : soit on brusque
l'API tierce, soit on fige l'interface. Le dashboard passait 10 secondes à
attendre un `Retry-After` en plein rendu.

Une `ContextVar` suit la tâche asyncio courante, sans qu'il faille faire
descendre un drapeau à travers toutes les signatures de la pile d'appels.
"""

from contextvars import ContextVar

# Vrai pendant le traitement d'une requête HTTP. Faux par défaut : les workers
# Celery, les scripts et les tests n'ont personne qui attend devant un écran.
sert_une_requete_http: ContextVar[bool] = ContextVar("sert_une_requete_http", default=False)


def un_humain_attend() -> bool:
    """Vrai quand une réponse rapide prime sur une donnée complète."""
    return sert_une_requete_http.get()
