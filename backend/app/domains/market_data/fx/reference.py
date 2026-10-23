import bisect
from collections.abc import Sequence
from datetime import date
from decimal import Decimal


def resolve_rate(target: date, sorted_rates: Sequence[tuple[date, Decimal]]) -> Decimal | None:
    """Taux en vigueur à ``target`` (dernier publié à cette date ou avant), None avant l'historique."""
    if not sorted_rates:
        return None
    index = bisect.bisect_right([d for d, _ in sorted_rates], target) - 1
    return sorted_rates[index][1] if index >= 0 else None
