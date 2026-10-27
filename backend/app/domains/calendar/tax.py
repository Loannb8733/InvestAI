import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.calendar.models import CalendarEvent, EventType
from app.domains.calendar.schemas import SeedTaxEventsResponse

NOTE = (
    "Date indicative — vérifiez le calendrier officiel sur impots.gouv.fr. "
    "Concerne notamment les formulaires 2042 (déclaration des revenus) "
    "et 2086 (plus-values sur actifs numériques)."
)


@dataclass(frozen=True)
class TaxDeadline:
    title: str
    date: datetime
    description: str


def french_tax_deadlines(year: int) -> list[TaxDeadline]:
    """Échéances fiscales françaises indicatives : ouverture et clôture de la déclaration, solde de l'impôt."""
    return [
        TaxDeadline(
            f"Ouverture de la déclaration des revenus {year}",
            datetime(year, 4, 1, 9, 0, tzinfo=UTC),
            f"Ouverture du service de déclaration en ligne (généralement début avril). {NOTE}",
        ),
        TaxDeadline(
            f"Date limite de déclaration en ligne {year} (départements 50 et +)",
            datetime(year, 6, 8, 9, 0, tzinfo=UTC),
            f"Date limite de la déclaration en ligne pour les départements 50 à 976. {NOTE}",
        ),
        TaxDeadline(
            f"Solde de l'impôt sur le revenu {year}",
            datetime(year, 9, 15, 9, 0, tzinfo=UTC),
            f"Prélèvement du solde de l'impôt sur le revenu (généralement mi-septembre). {NOTE}",
        ),
    ]


async def seed_tax_events(db: AsyncSession, user_id: uuid.UUID) -> SeedTaxEventsResponse:
    """Ajoute les échéances fiscales de l'année et de la suivante qui manquent, sans les échéances passées.

    Une échéance existe déjà quand une échéance fiscale de l'utilisateur porte le même titre, qui contient l'année.
    """
    now = datetime.now(UTC)
    existing = await db.execute(
        select(CalendarEvent.title).where(
            CalendarEvent.user_id == user_id, CalendarEvent.event_type == EventType.TAX_DEADLINE
        )
    )
    titles = set(existing.scalars().all())
    created = skipped = 0
    for year in (now.year, now.year + 1):
        for deadline in french_tax_deadlines(year):
            if deadline.title in titles or deadline.date < now:
                skipped += 1
                continue
            db.add(
                CalendarEvent(
                    user_id=user_id,
                    title=deadline.title,
                    description=deadline.description,
                    event_type=EventType.TAX_DEADLINE,
                    event_date=deadline.date,
                    is_recurring=False,
                    currency="EUR",
                    is_completed=False,
                )
            )
            titles.add(deadline.title)
            created += 1
    if not created:
        return SeedTaxEventsResponse(
            created=0, skipped=skipped, message="Aucune échéance à ajouter : elles existent déjà ou sont passées."
        )
    await db.commit()
    message = f"{created} échéance(s) fiscale(s) ajoutée(s). Dates indicatives — vérifiez sur impots.gouv.fr."
    return SeedTaxEventsResponse(created=created, skipped=skipped, message=message)
