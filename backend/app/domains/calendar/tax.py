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
    """Échéances fiscales françaises indicatives de l'année ``year``, qui portent sur les revenus de l'année
    précédente : ouverture et clôture de la déclaration, solde de l'impôt.
    """
    income_year = year - 1
    return [
        TaxDeadline(
            f"Ouverture de la déclaration {year} des revenus {income_year}",
            datetime(year, 4, 1, 9, 0, tzinfo=UTC),
            f"Ouverture du service de déclaration en ligne (généralement début avril). {NOTE}",
        ),
        TaxDeadline(
            f"Date limite de la déclaration en ligne {year} des revenus {income_year} (départements 50 et +)",
            datetime(year, 6, 8, 9, 0, tzinfo=UTC),
            f"Date limite de la déclaration en ligne pour les départements 50 à 976. {NOTE}",
        ),
        TaxDeadline(
            f"Solde de l'impôt sur les revenus {income_year}",
            datetime(year, 9, 15, 9, 0, tzinfo=UTC),
            f"Prélèvement du solde de l'impôt sur le revenu (généralement mi-septembre). {NOTE}",
        ),
    ]


async def seed_tax_events(db: AsyncSession, user_id: uuid.UUID) -> SeedTaxEventsResponse:
    """Ajoute les échéances fiscales de l'année et de la suivante qui manquent, sans les échéances passées.

    Une échéance existe déjà quand une échéance fiscale de l'utilisateur tombe au même moment.
    """
    now = datetime.now(UTC)
    existing = await db.execute(
        select(CalendarEvent.event_date).where(
            CalendarEvent.user_id == user_id, CalendarEvent.event_type == EventType.TAX_DEADLINE
        )
    )
    taken = set(existing.scalars().all())
    created = skipped = 0
    for year in (now.year, now.year + 1):
        for deadline in french_tax_deadlines(year):
            if deadline.date in taken or deadline.date < now:
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
            taken.add(deadline.date)
            created += 1
    if not created:
        return SeedTaxEventsResponse(
            created=0, skipped=skipped, message="Aucune échéance à ajouter : elles existent déjà ou sont passées."
        )
    await db.commit()
    message = f"{created} échéance(s) fiscale(s) ajoutée(s). Dates indicatives — vérifiez sur impots.gouv.fr."
    return SeedTaxEventsResponse(created=created, skipped=skipped, message=message)
