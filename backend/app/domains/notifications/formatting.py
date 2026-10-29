NBSP = "\u00a0"


def amount(value: float, currency: str, signed: bool = False) -> str:
    """Montant à la française, « 12 345,68 EUR », avec espaces insécables ; « + » devant un gain si ``signed``."""
    sign = "+" if signed and value >= 0 else ""
    grouped = f"{value:,.2f}".replace(",", NBSP).replace(".", ",")
    return f"{sign}{grouped}{NBSP}{currency}"


def percent(value: float, decimals: int = 1, signed: bool = False) -> str:
    """Pourcentage à la française, « 1,9 % » ; « + » devant une hausse si ``signed``."""
    sign = "+" if signed and value >= 0 else ""
    return f"{sign}{value:.{decimals}f}".replace(".", ",") + f"{NBSP}%"
