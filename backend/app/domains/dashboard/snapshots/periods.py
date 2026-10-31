"""Échelle de la série de valeur selon la longueur de la période."""

from datetime import datetime

from app.domains.planning.goals.months import SHORT_MONTHS

_DAY_NAMES = ("Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim")


def format_date_for_period(moment: datetime, days: int) -> str:
    """Étiquette d'un point : jour de semaine, jour et mois abrégé, ou jour/mois."""
    if days <= 7:
        return f"{_DAY_NAMES[moment.weekday()]} {moment.day}"
    if days <= 30:
        return f"{moment.day:02d} {SHORT_MONTHS[moment.month - 1]}"
    return moment.strftime("%d/%m")


def data_point_interval(days: int) -> int:
    """Nombre de jours entre deux points de la série."""
    if days <= 30:
        return 1
    if days <= 90:
        return 3
    if days <= 365:
        return 7
    return 14
