"""Historical FX resolution for cost-basis conversion (FIN-01).

Exchange trades are priced in a quote currency (USD/USDT/EUR/...). To book a correct
EUR cost basis, each trade needs the FX rate **at its execution date**. The cost-basis
engine (``metrics_service``) consumes ``Transaction.conversion_rate`` as a direct
multiplier: ``eur_unit_cost = price_in_quote * conversion_rate``. So ``conversion_rate``
must be expressed as **EUR per 1 unit of the quote currency** (≈ 0.92 for USD), matching
the existing ``PriceService.get_forex_rate("USD", "EUR")`` convention.

Source of truth: ECB daily reference rates (served free, no key, by Frankfurter). The ECB
only publishes on TARGET business days, while crypto trades 24/7 — so we **forward-fill**:
a weekend/holiday trade uses the most recent published business-day rate at or before its
date. This is the standard accounting convention; the residual error is bounded by the
weekend FX drift and is documented, not hidden.

This module's resolver is a **pure function** (no DB/HTTP) so the date logic is unit
tested deterministically. The DB-backed loader lives in ``FxHistoryService``.
"""

from __future__ import annotations

import bisect
from collections.abc import Sequence
from datetime import date
from decimal import Decimal


def resolve_rate(
    target: date,
    sorted_rates: Sequence[tuple[date, Decimal]],
) -> Decimal | None:
    """Return the rate effective on ``target`` via forward-fill.

    ``sorted_rates`` must be a sequence of ``(date, rate)`` sorted ascending by date.
    Returns the rate of the latest entry whose date is ``<= target`` (so weekends and
    holidays reuse the prior business-day fix). Returns ``None`` when ``target`` precedes
    the earliest known date (we must not fabricate a rate before history begins) or when
    the input is empty.
    """
    if not sorted_rates:
        return None
    # Find the rightmost entry with date <= target.
    dates = [d for d, _ in sorted_rates]
    idx = bisect.bisect_right(dates, target) - 1
    if idx < 0:
        return None
    return sorted_rates[idx][1]
