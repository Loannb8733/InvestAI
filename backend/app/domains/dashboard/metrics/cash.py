"""Liquidités d'un portefeuille : stablecoins au cours de marché, monnaies fiat au taux de change."""

import logging
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from app.domains.dashboard.metrics.quotes import fetch_stablecoin_prices
from app.domains.market_data.fx.spot import spot_rates
from app.domains.portfolio.models import Asset
from app.domains.transactions.cost_basis.layers import ZERO

logger = logging.getLogger(__name__)

_USD_STABLECOINS = {"USDT", "USDC", "BUSD", "DAI", "FDUSD", "TUSD", "PYUSD", "FRAX", "LUSD", "USDG"}
_DEPEG_THRESHOLD = 0.02


@dataclass(frozen=True)
class ReferenceRates:
    """Taux vers la devise cible, servant de parité et de repli."""

    target: str
    usd_to_target: float
    eur_to_target: float

    def peg(self, symbol: str) -> float:
        """Valeur de parité d'un stablecoin dans la devise cible."""
        return self.usd_to_target if symbol in _USD_STABLECOINS else self.eur_to_target


@dataclass
class CashHoldings:
    """Une famille de liquidités : montant total et détail par actif."""

    total: Decimal = ZERO
    entries: list[dict[str, Any]] = field(default_factory=list)


async def value_stablecoins(
    assets: list[Asset], rates: ReferenceRates, currency: str, min_value: float
) -> CashHoldings:
    """Valorise au cours de marché, à la parité sans cours, et signale un écart de plus de 2 %."""
    live_prices = await fetch_stablecoin_prices([asset.symbol for asset in assets], currency)
    holdings = CashHoldings()
    for asset in assets:
        symbol = asset.symbol.upper()
        peg = rates.peg(symbol)
        live = live_prices.get(symbol)
        quoted = bool(live and live > 0)
        unit_price = live if live and quoted else peg
        value = float(asset.quantity) * unit_price
        if value < min_value:
            continue
        depeg = abs(unit_price - peg) / peg if quoted and peg > 0 else 0.0
        holdings.total += Decimal(str(value))
        holdings.entries.append(
            {
                "id": str(asset.id),
                "symbol": asset.symbol,
                "quantity": float(asset.quantity),
                "value": value,
                "unit_price": unit_price,
                "depeg_warning": depeg > _DEPEG_THRESHOLD,
                "depeg_percent": round(depeg * 100, 2) if depeg > _DEPEG_THRESHOLD else 0,
            }
        )
    return holdings


async def _fiat_rates(rates: ReferenceRates) -> dict[str, float]:
    known = {"EUR": rates.eur_to_target, "USD": rates.usd_to_target, "GBP": 1.0, "CHF": 1.0}
    for symbol in {"GBP", "CHF"} - {rates.target}:
        try:
            rate = await spot_rates.get(symbol, rates.target)
        except Exception as exc:  # noqa: BLE001
            logger.debug("Fiat forex rate fetch failed for %s->%s: %s", symbol, rates.target, exc)
            continue
        if rate:
            known[symbol] = float(rate)
    known[rates.target] = 1.0
    return known


async def value_fiat(assets: list[Asset], rates: ReferenceRates) -> CashHoldings:
    """Valorise les monnaies au taux de change ; une devise inconnue prend le taux de l'euro."""
    known = await _fiat_rates(rates)
    holdings = CashHoldings()
    for asset in assets:
        value = float(asset.quantity) * known.get(asset.symbol.upper(), rates.eur_to_target)
        holdings.total += Decimal(str(value))
        holdings.entries.append(
            {"id": str(asset.id), "symbol": asset.symbol, "quantity": float(asset.quantity), "value": value}
        )
    return holdings
