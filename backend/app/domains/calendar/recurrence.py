import calendar
from datetime import UTC, datetime, timedelta

MAX_OCCURRENCES = 400


def next_occurrence(current: datetime, rule: str) -> datetime | None:
    """Occurrence suivante selon la règle (DAILY, WEEKLY, MONTHLY, YEARLY), None pour une règle inconnue.

    Un mois plus court garde le dernier jour du mois.
    """
    rule = rule.upper()
    if "DAILY" in rule:
        return current + timedelta(days=1)
    if "WEEKLY" in rule:
        return current + timedelta(weeks=1)
    if "MONTHLY" in rule:
        year, month = (current.year + 1, 1) if current.month == 12 else (current.year, current.month + 1)
        return current.replace(year=year, month=month, day=min(current.day, calendar.monthrange(year, month)[1]))
    if "YEARLY" in rule:
        return current.replace(year=current.year + 1)
    return None


def _as_utc(moment: datetime) -> datetime:
    return moment.replace(tzinfo=UTC) if moment.tzinfo is None else moment


def _fast_forward(start: datetime, rule: str, now: datetime) -> datetime:
    if start >= now:
        return start
    behind_days = (now - start).days
    if "DAILY" in rule:
        return start + timedelta(days=behind_days)
    if "WEEKLY" in rule:
        return start + timedelta(weeks=behind_days // 7)
    return start


def occurrences(start: datetime, rule: str | None, now: datetime, cutoff: datetime) -> list[datetime]:
    """Occurrences entre maintenant et ``cutoff`` ; sans règle, la date elle-même si elle est à venir.

    Au plus 400 occurrences dépliées.
    """
    occurrence = _as_utc(start)
    if not rule:
        return [occurrence] if occurrence >= now else []
    occurrence = _fast_forward(occurrence, rule.upper(), now)
    found: list[datetime] = []
    for _ in range(MAX_OCCURRENCES):
        if occurrence > cutoff:
            break
        if occurrence >= now:
            found.append(occurrence)
        following = next_occurrence(occurrence, rule)
        if not following or following <= occurrence:
            break
        occurrence = _as_utc(following)
    return found
