"""Exécution de coroutines depuis une tâche Celery synchrone.

Pourquoi un seul endroit
------------------------
Huit modules de ``app/tasks`` définissaient leur propre ``run_async``, en trois
variantes subtilement différentes, et un neuvième appelait ``new_event_loop``
directement. Six d'entre elles omettaient ``set_event_loop`` — or asyncpg et
SQLAlchemy résolvent la boucle courante via ``get_event_loop()`` au moment de créer
leurs ressources. Sans ce réglage, une coroutine pouvait rattacher une connexion à
une boucle qui n'est plus celle qui l'exécute : c'est l'origine des
« Future attached to a different loop » et des connexions jamais rendues au pool.

Le défaut se propageait par imitation : chaque nouvelle tâche recopiait le helper du
voisin. Le 2026-09-01, une neuvième copie a été ajoutée de cette façon.

Ce module est l'unique implémentation. Toute tâche Celery doit l'importer plutôt que
d'en écrire une.
"""

from __future__ import annotations

import asyncio
from typing import Any, Coroutine, TypeVar

T = TypeVar("T")


def run_async(coro: Coroutine[Any, Any, T]) -> T:
    """Exécute ``coro`` dans une boucle neuve, dédiée à cet appel.

    La boucle est installée comme boucle courante (``set_event_loop``) avant
    exécution : asyncpg et SQLAlchemy résolvent la boucle via ``get_event_loop()``
    en créant leurs ressources, et sans cela ils les rattachent à une autre boucle
    que celle qui exécute la coroutine.

    On ne touche pas à l'état du thread APRÈS coup. Poser ``set_event_loop(None)``
    dans le ``finally`` paraissait plus propre — aucune boucle fermée ne restant
    courante — mais cela retire sa boucle à un appelant qui en avait une : 103 tests
    sont tombés sur « There is no current event loop » avant que ce comportement ne
    soit abandonné. C'est celui qu'avait ``history_cache``, éprouvé en production.
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()
