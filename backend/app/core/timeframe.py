"""Centralized timeframe utility for consistent period calculations.

All services that need to compute date ranges from a period selector
should use these functions to avoid drift between components.
"""

from datetime import datetime, timedelta


def get_period_start_date(days: int) -> datetime:
    """Get the UTC start date for a given period.

    Args:
        days: Number of days. 0 means "all time" (returns a far-past date).

    Returns:
        datetime: The start date (UTC, midnight-aligned).
    """
    if days <= 0:
        return datetime(2000, 1, 1)
    start = datetime.utcnow() - timedelta(days=days)
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


# CoinGecko pre-computed period mapping.
# Keys that match exactly get a batch API call; others need historical data.
COINGECKO_PERIOD_MAP = {
    1: ("24h", "price_change_percentage_24h_in_currency"),
    7: ("7d", "price_change_percentage_7d_in_currency"),
    14: ("14d", "price_change_percentage_14d_in_currency"),
    30: ("30d", "price_change_percentage_30d_in_currency"),
    200: ("200d", "price_change_percentage_200d_in_currency"),
    365: ("1y", "price_change_percentage_1y_in_currency"),
}


def get_coingecko_period(days: int):
    """Find the best CoinGecko pre-computed period for *days*.

    Returns:
        (cg_period, cg_key) if a close match exists, else (None, None).
    """
    # Exact match
    if days in COINGECKO_PERIOD_MAP:
        return COINGECKO_PERIOD_MAP[days]

    # Allow small tolerance for common selections
    for threshold, (period, key) in sorted(COINGECKO_PERIOD_MAP.items()):
        if days <= threshold:
            # Only accept if within 15% of the CoinGecko period
            if (threshold - days) / threshold <= 0.15:
                return period, key
            return None, None

    # days > 365 → use 1y
    return COINGECKO_PERIOD_MAP[365]
