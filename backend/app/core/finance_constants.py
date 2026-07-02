"""Finance constants shared across services.

Kept in the low-level ``core`` layer so services (price, snapshot, metrics) can
import it without creating cycles.
"""

from decimal import Decimal

# Last-resort USD->EUR rate, used ONLY when the live forex API, its Redis cache,
# and the last-known value are all unavailable (cold start). Every real code path
# prefers a live or last-known rate; this constant merely prevents a hard failure
# and is always surfaced to the UI as a stale/guessed rate — never as a quote.
COLD_START_USD_EUR: Decimal = Decimal("0.92")
