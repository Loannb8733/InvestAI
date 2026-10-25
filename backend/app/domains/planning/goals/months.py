from datetime import date

SHORT_MONTHS = ("janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc.")
LONG_MONTHS = (
    "janvier",
    "février",
    "mars",
    "avril",
    "mai",
    "juin",
    "juillet",
    "août",
    "septembre",
    "octobre",
    "novembre",
    "décembre",
)


def short_month(day: date) -> str:
    """Mois abrégé et année en français (« sept. 2029 »), indépendamment de la locale du serveur."""
    return f"{SHORT_MONTHS[day.month - 1]} {day.year}"


def long_month(day: date) -> str:
    """Mois et année en toutes lettres (« juin 2029 »)."""
    return f"{LONG_MONTHS[day.month - 1]} {day.year}"
