"""Resynchronise les échéanciers et calendriers crowdfunding enregistrés avec le calcul actuel.

Problème
--------
L'échéancier contractuel et les événements du calendrier sont calculés à la
création d'un projet, puis enregistrés. Les corrections du 2026-10-26 (intérêts
d'un amortissable sur le capital restant dû, dernière période incomplète d'un in
fine, calendrier dérivé de l'échéancier) ne changent donc rien aux projets déjà
saisis tant qu'ils ne sont pas resynchronisés.

Ce que fait le script
---------------------
Pour chaque projet : les échéances soldées restent telles quelles, les échéances
ouvertes sont recalculées ; les événements à venir non faits sont remplacés par
ceux de l'échéancier (projets actifs ou en retard) ou retirés (autres statuts).
Les événements passés ou faits ne bougent pas.

Un projet est laissé de côté, et signalé, quand son capital serait attendu deux
fois (une échéance soldée de l'ancien calcul portait déjà le capital) ou quand
son propriétaire est introuvable : seule une personne peut trancher.

Ce qu'il ne rattrape pas : le taux d'imposition et le retard saisis à la création
avant la correction n'ont jamais été enregistrés ; ils se corrigent dans l'écran.

Idempotence
-----------
Après écriture, un second passage ne propose plus rien. Dry-run par défaut.

Usage
-----
    python scripts/resync_crowdfunding.py            # dry-run
    python scripts/resync_crowdfunding.py --commit   # applique
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select  # noqa: E402

from app.core.db.session import session_factory  # noqa: E402
from app.domains.crowdfunding.models import CrowdfundingProject  # noqa: E402
from app.domains.crowdfunding.resync import ResyncPlan, apply_resync, plan_resync  # noqa: E402


def _total(installments) -> Decimal:
    return sum((capital + interest for _, capital, interest in installments), Decimal("0"))


def describe(plan: ResyncPlan) -> str:
    """Ligne de rapport d'un projet. Fonction pure."""
    project = plan.project
    name = f"{project.project_name or '-'} ({project.platform}, {project.status.value})"
    schedule = (
        f"échéances ouvertes {len(plan.open_before)} = {_total(plan.open_before)} € "
        f"-> {len(plan.open_after)} = {_total(plan.open_after)} €"
    )
    events = f"calendrier {len(plan.events_before)} -> {len(plan.events_after)} événement(s)"
    verdict = f"IGNORÉ : {plan.blocker}" if plan.blocker else ("à resynchroniser" if plan.changed else "déjà à jour")
    return f"  {name}\n    {schedule} ; {events} — {verdict}"


async def resync(commit: bool) -> int:
    async with session_factory() as db:
        projects = (
            (await db.execute(select(CrowdfundingProject).order_by(CrowdfundingProject.created_at))).scalars().all()
        )
        plans = [await plan_resync(db, project) for project in projects]
        for plan in plans:
            print(describe(plan))
        todo = [plan for plan in plans if plan.changed and not plan.blocker]
        blocked = [plan for plan in plans if plan.changed and plan.blocker]
        print(f"\n--- {len(todo)} projet(s) à resynchroniser, {len(blocked)} ignoré(s), {len(plans)} au total ---")
        if not commit:
            await db.rollback()
            print("DRY-RUN : rien écrit. Relancer avec --commit pour appliquer.")
            return len(todo)
        for plan in todo:
            await apply_resync(db, plan)
        print(f"COMMITTED : {len(todo)} projet(s) resynchronisé(s).")
        return len(todo)


def main() -> None:
    parser = argparse.ArgumentParser(description="Resynchronise échéanciers et calendriers crowdfunding.")
    parser.add_argument("--commit", action="store_true", help="Applique (défaut : dry-run).")
    args = parser.parse_args()
    asyncio.run(resync(args.commit))


if __name__ == "__main__":
    main()
