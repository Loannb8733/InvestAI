from decimal import Decimal

USD_EUR = Decimal("0.92")

_RATES: dict[tuple[str, str], Decimal] = {
    ("EUR", "USD"): Decimal("1.09"),
    ("EUR", "CHF"): Decimal("0.94"),
    ("EUR", "GBP"): Decimal("0.86"),
    ("USD", "EUR"): USD_EUR,
    ("USD", "CHF"): Decimal("0.86"),
    ("USD", "GBP"): Decimal("0.79"),
}


def cold_start_rate(from_ccy: str, to_ccy: str) -> Decimal | None:
    """Taux de dernier recours, sans aucune source disponible ; toujours à signaler comme périmé."""
    return _RATES.get((from_ccy.upper(), to_ccy.upper()))
