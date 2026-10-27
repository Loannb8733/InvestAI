import calendar
from datetime import UTC, datetime, timedelta

MAX_OCCURRENCES = 400


def _same_day_in(current: datetime, year: int, month: int) -> datetime:
    return current.replace(year=year, month=month, day=min(current.day, calendar.monthrange(year, month)[1]))


def next_occurrence(current: datetime, rule: str) -> datetime | None:
    """Occurrence suivante selon la règle (DAILY, WEEKLY, MONTHLY, YEARLY), None pour une règle inconnue.

    Un mois plus court garde son dernier jour : le 31 janvier passe au 28 février, le 29 février au 28.
    """
    rule = rule.upper()
    if "DAILY" in rule:
        return current + timedelta(days=1)
    if "WEEKLY" in rule:
        return current + timedelta(weeks=1)
    if "MONTHLY" in rule:
        year, month = (current.year + 1, 1) if current.month == 12 else (current.year, current.month + 1)
        return _same_day_in(current, year, month)
    if "YEARLY" in rule:
        return _same_day_in(current, current.year + 1, current.month)
    return None


def _as_utc(moment: datetime) -> datetime:
    return moment.replace(tzinfo=UTC) if moment.tzinfo is None else moment


def _fast_forward(first: datetime, rule: str, start: datetime) -> datetime:
    if first >= start:
        return first
    behind_days = (start - first).days
    if "DAILY" in rule:
        return first + timedelta(days=behind_days)
    if "WEEKLY" in rule:
        return first + timedelta(weeks=behind_days // 7)
    return first


def occurrences(first: datetime, rule: str | None, start: datetime, end: datetime) -> list[datetime]:
    """Occurrences comprises entre ``start`` inclus et ``end`` exclu ; sans règle, la date elle-même.

    Au plus 400 occurrences dépliées.
    """
    occurrence = _as_utc(first)
    if not rule:
        return [occurrence] if start <= occurrence < end else []
    occurrence = _fast_forward(occurrence, rule.upper(), start)
    found: list[datetime] = []
    for _ in range(MAX_OCCURRENCES):
        if occurrence >= end:
            break
        if occurrence >= start:
            found.append(occurrence)
        following = next_occurrence(occurrence, rule)
        if not following or following <= occurrence:
            break
        occurrence = _as_utc(following)
    return found
