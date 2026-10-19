"""Centralized timeframe utility for consistent period calculations.

All services that need to compute date ranges from a period selector
should use these functions to avoid drift between components.
"""

from datetime import UTC, datetime, timedelta


def get_period_start_date(days: int) -> datetime:
    """Get the UTC start date for a given period.

    Args:
        days: Number of days. 0 means "all time" (returns a far-past date).

    Returns:
        datetime: The start date (UTC, midnight-aligned).
    """
    if days <= 0:
        return datetime(2000, 1, 1)
    start = datetime.now(UTC) - timedelta(days=days)
    return start.replace(hour=0, minute=0, second=0, microsecond=0)


def get_period_label_fr(days: int) -> str:
    """Get a human-readable French label for a period.

    Args:
        days: Number of days. 0 means "all time".

    Returns:
        str: e.g. "24h", "7j", "30j", "90j", "1 an", "Depuis le début".
    """
    if days <= 0:
        return "Depuis le début"
    if days == 1:
        return "24h"
    if days == 365:
        return "1 an"
    return f"{days}j"
