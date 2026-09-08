"""Advanced analysis service: fees, tax-loss harvesting, passive income, DCA backtest."""

import logging
from datetime import datetime, timezone
from typing import Dict, Optional

from sqlalchemy import extract, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.asset import Asset, AssetType
from app.models.portfolio import Portfolio
from app.models.transaction import Transaction, TransactionType
from app.services.price_service import price_service

logger = logging.getLogger(__name__)


# Devises dont le montant est déjà exploitable tel quel, ou converti par le
# taux capté à l'exécution. Les autres sont des jetons : il leur faut un cours.
DEVISES_FIAT = frozenset({"EUR", "USD", "GBP", "CAD", "JPY", "CHF", "AUD"})


def convertir_frais_en_devise_portefeuille(
    montant: float,
    devise_frais: str,
    symbole_actif: str,
    prix_transaction: float,
    devise_transaction: str,
    taux_conversion: Optional[float],
    cours_par_jeton: Optional[Dict[str, float]] = None,
) -> tuple[float, bool]:
    """Ramène des frais dans la devise du portefeuille. Rend (montant, converti).

    Additionner des frais sans les convertir revenait à faire « 1 EUR + 1 USDC
    + 0,001 BTC = 2,001 » : `fee_currency` était reporté ligne par ligne, mais
    le total et toutes les ventilations sommaient des montants bruts. Sur un
    frais en BTC, l'écart est de trois ordres de grandeur.

    Quatre situations, dans l'ordre où elles se présentent :

    - **frais déjà dans la devise du portefeuille** — rien à faire ;
    - **frais dans la devise de la transaction** (des frais en USD sur un trade
      libellé en USD) — le `conversion_rate` capté à l'exécution s'applique,
      et c'est le taux du jour de l'opération, pas celui d'aujourd'hui ;
    - **frais dans le jeton échangé** (des frais en BTC sur un achat de BTC) —
      le prix unitaire de la transaction fait l'affaire, converti lui aussi ;
    - **frais dans un autre jeton** (des frais en BNB sur un achat de PEPE) —
      il faut le cours de ce jeton, que l'appelant fournit.

    Faute de cours, le montant est rendu **tel quel** avec `converti=False` :
    l'appelant sait alors qu'une part du total n'est pas homogène, plutôt que
    de recevoir un zéro qui minorerait silencieusement les frais.
    """
    if montant <= 0:
        return 0.0, True

    devise = (devise_frais or "EUR").upper()
    if devise == "EUR":
        return montant, True

    fx = float(taux_conversion) if taux_conversion else 1.0

    if devise in DEVISES_FIAT:
        if devise == (devise_transaction or "EUR").upper():
            return montant * fx, True
        return montant, False

    if devise == (symbole_actif or "").upper():
        return (montant * prix_transaction * fx, True) if prix_transaction > 0 else (montant, False)

    cours = (cours_par_jeton or {}).get(devise, 0.0)
    if cours > 0:
        return montant * cours, True

    return montant, False


class InsightsService:
    """Service for advanced portfolio insights."""

    # ------------------------------------------------------------------
    # Fee Analysis
    # ------------------------------------------------------------------

    @staticmethod
    def _mois_couverts(mois_observes: list[str]) -> int:
        """Nombre de mois entre le premier et le dernier mois observé, inclus.

        Diviser par le nombre de mois **ayant porté un mouvement** répond à
        « combien un mois actif coûte-t-il », pas à « combien cela me coûte par
        mois » — ce que le libellé laisse entendre. Douze euros payés en
        janvier et rien les onze mois suivants donnaient une « moyenne
        mensuelle » de 12 EUR ; ils en donnent désormais 1.

        Les mois sans mouvement comptent donc au dénominateur, y compris ceux
        du milieu. Les clés hors format (`"?"`, pour une transaction sans date)
        sont ignorées : elles ne situent rien sur l'axe du temps.
        """
        valides = sorted(m for m in mois_observes if len(m) == 7 and m[4] == "-")
        if not valides:
            return 1
        debut, fin = valides[0], valides[-1]
        ecart = (int(fin[:4]) - int(debut[:4])) * 12 + (int(fin[5:]) - int(debut[5:]))
        return max(ecart + 1, 1)

    async def get_fee_analysis(self, db: AsyncSession, user_id: str) -> dict:
        """Analyse complète des frais payés : par exchange, par actif, par mois."""
        portfolios = await self._get_user_portfolios(db, user_id)
        if not portfolios:
            return self._empty_fees()

        pids = [p.id for p in portfolios]
        asset_ids, asset_map = await self._get_assets_map(db, pids)
        if not asset_ids:
            return self._empty_fees()

        # All transactions with fees
        result = await db.execute(
            select(Transaction)
            .where(
                Transaction.asset_id.in_(asset_ids),
                Transaction.fee > 0,
            )
            .order_by(Transaction.executed_at.desc())
        )
        txns = result.scalars().all()

        total_fees = 0.0
        by_exchange: Dict[str, float] = {}
        by_asset: Dict[str, float] = {}
        by_type: Dict[str, float] = {}
        by_month: Dict[str, float] = {}
        fee_list = []

        # Cours des jetons dans lesquels des frais ont été prélevés sans que la
        # transaction porte de quoi les convertir. Un appel par jeton, pas un
        # par transaction.
        jetons_a_coter = {
            (tx.fee_currency or "").upper()
            for tx in txns
            if (tx.fee_currency or "EUR").upper() not in DEVISES_FIAT
            and (tx.fee_currency or "").upper()
            != (asset_map.get(str(tx.asset_id)).symbol.upper() if asset_map.get(str(tx.asset_id)) else "")
        }
        cours_par_jeton: Dict[str, float] = {}
        for jeton in jetons_a_coter:
            if not jeton:
                continue
            try:
                donnees = await price_service.get_price(jeton, "crypto")
                if donnees and donnees.get("price"):
                    cours_par_jeton[jeton] = float(donnees["price"])
            except Exception:
                logger.warning("Cours indisponible pour %s — frais laissés dans leur devise", jeton)

        frais_non_convertis = 0

        for tx in txns:
            asset_courant = asset_map.get(str(tx.asset_id))
            fee, converti = convertir_frais_en_devise_portefeuille(
                float(tx.fee or 0),
                tx.fee_currency or "EUR",
                asset_courant.symbol if asset_courant else "",
                float(tx.price or 0),
                tx.currency or "EUR",
                tx.conversion_rate,
                cours_par_jeton,
            )
            if not converti:
                frais_non_convertis += 1
            total_fees += fee

            exchange = tx.exchange or "Inconnu"
            by_exchange[exchange] = by_exchange.get(exchange, 0) + fee

            asset = asset_map.get(str(tx.asset_id))
            symbol = asset.symbol if asset else "?"
            by_asset[symbol] = by_asset.get(symbol, 0) + fee

            tx_type = tx.transaction_type.value if hasattr(tx.transaction_type, "value") else str(tx.transaction_type)
            by_type[tx_type] = by_type.get(tx_type, 0) + fee

            month = tx.executed_at.strftime("%Y-%m") if tx.executed_at else "?"
            by_month[month] = by_month.get(month, 0) + fee

            fee_list.append(
                {
                    "date": tx.executed_at.isoformat() if tx.executed_at else None,
                    "symbol": symbol,
                    "exchange": exchange,
                    "type": tx_type,
                    "fee": round(fee, 2),
                    "fee_currency": tx.fee_currency or "EUR",
                    "fee_convertie": converti,
                }
            )

        # Sort by_month chronologically
        by_month_sorted = dict(sorted(by_month.items()))

        # Average monthly fee
        avg_monthly = total_fees / self._mois_couverts(list(by_month))

        return {
            "total_fees": round(total_fees, 2),
            "nb_transactions_with_fees": len(txns),
            # Nombre de frais dont la devise n'a pas pu être ramenée en euros :
            # tant qu'il est non nul, le total mélange des unités.
            "nb_frais_non_convertis": frais_non_convertis,
            "avg_monthly_fee": round(avg_monthly, 2),
            "by_exchange": {k: round(v, 2) for k, v in sorted(by_exchange.items(), key=lambda x: -x[1])},
            "by_asset": {k: round(v, 2) for k, v in sorted(by_asset.items(), key=lambda x: -x[1])[:10]},
            "by_type": {k: round(v, 2) for k, v in sorted(by_type.items(), key=lambda x: -x[1])},
            "by_month": {k: round(v, 2) for k, v in by_month_sorted.items()},
            "recent_fees": fee_list[:20],
        }

    # ------------------------------------------------------------------
    # Tax-Loss Harvesting
    # ------------------------------------------------------------------

    async def get_tax_loss_harvesting(self, db: AsyncSession, user_id: str) -> dict:
        """Identify positions with unrealized losses that could be sold for tax optimization."""
        portfolios = await self._get_user_portfolios(db, user_id)
        if not portfolios:
            return {
                "opportunities": [],
                "total_harvestable": 0,
                "estimated_tax_saving": 0,
            }

        pids = [p.id for p in portfolios]
        result = await db.execute(
            select(Asset).where(
                Asset.portfolio_id.in_(pids),
                Asset.quantity > 0,
            )
        )
        assets = result.scalars().all()

        opportunities = []
        total_harvestable = 0.0

        for asset in assets:
            qty = float(asset.quantity)
            avg_price = float(asset.avg_buy_price)
            if qty <= 0 or avg_price <= 0:
                continue

            # Get current price
            at = asset.asset_type.value if isinstance(asset.asset_type, AssetType) else str(asset.asset_type)
            price_data = await price_service.get_price(asset.symbol, at)
            current_price = float(price_data["price"]) if price_data and price_data.get("price") else avg_price

            cost_basis = qty * avg_price
            current_value = qty * current_price
            unrealized_pnl = current_value - cost_basis
            unrealized_pnl_pct = (unrealized_pnl / cost_basis * 100) if cost_basis > 0 else 0

            if unrealized_pnl < 0:
                # This is a harvesting candidate
                tax_saving = abs(unrealized_pnl) * 0.30  # Flat tax 30%
                total_harvestable += unrealized_pnl

                opportunities.append(
                    {
                        "symbol": asset.symbol,
                        "name": asset.name,
                        "asset_type": at,
                        "quantity": round(qty, 8),
                        "avg_buy_price": round(avg_price, 2),
                        "current_price": round(current_price, 2),
                        "cost_basis": round(cost_basis, 2),
                        "current_value": round(current_value, 2),
                        "unrealized_loss": round(unrealized_pnl, 2),
                        "unrealized_loss_pct": round(unrealized_pnl_pct, 2),
                        "potential_tax_saving": round(tax_saving, 2),
                    }
                )

        # Sort by biggest loss first
        opportunities.sort(key=lambda x: x["unrealized_loss"])
        estimated_tax_saving = abs(total_harvestable) * 0.30 if total_harvestable < 0 else 0

        return {
            "opportunities": opportunities,
            "total_harvestable": round(total_harvestable, 2),
            "estimated_tax_saving": round(estimated_tax_saving, 2),
            "nb_candidates": len(opportunities),
            "note": "Vendre ces positions cristallise les moins-values, réduisant l'impôt sur les plus-values. "
            "Attention au wash sale — ne rachetez pas immédiatement le même actif.",
        }

    # ------------------------------------------------------------------
    # Passive Income Tracker
    # ------------------------------------------------------------------

    async def get_passive_income(self, db: AsyncSession, user_id: str, year: Optional[int] = None) -> dict:
        """Track dividends, staking rewards, interest — by month and by asset."""
        portfolios = await self._get_user_portfolios(db, user_id)
        if not portfolios:
            return self._empty_passive_income()

        pids = [p.id for p in portfolios]
        asset_ids, asset_map = await self._get_assets_map(db, pids)
        if not asset_ids:
            return self._empty_passive_income()

        passive_types = [
            TransactionType.STAKING_REWARD,
            TransactionType.AIRDROP,
        ]

        query = select(Transaction).where(
            Transaction.asset_id.in_(asset_ids),
            Transaction.transaction_type.in_(passive_types),
        )
        if year:
            query = query.where(extract("year", Transaction.executed_at) == year)

        result = await db.execute(query.order_by(Transaction.executed_at.desc()))
        txns = result.scalars().all()

        total = 0.0
        by_type: Dict[str, float] = {}
        by_asset: Dict[str, float] = {}
        by_month: Dict[str, float] = {}
        history = []

        for tx in txns:
            value = float(tx.quantity * tx.price) if tx.price else 0
            total += value

            tx_type = tx.transaction_type.value if hasattr(tx.transaction_type, "value") else str(tx.transaction_type)
            by_type[tx_type] = by_type.get(tx_type, 0) + value

            asset = asset_map.get(str(tx.asset_id))
            symbol = asset.symbol if asset else "?"
            by_asset[symbol] = by_asset.get(symbol, 0) + value

            month = tx.executed_at.strftime("%Y-%m") if tx.executed_at else "?"
            by_month[month] = by_month.get(month, 0) + value

            history.append(
                {
                    "date": tx.executed_at.isoformat() if tx.executed_at else None,
                    "symbol": symbol,
                    "type": tx_type,
                    "quantity": round(float(tx.quantity), 8),
                    "price": round(float(tx.price), 4) if tx.price else 0,
                    "value": round(value, 2),
                }
            )

        by_month_sorted = dict(sorted(by_month.items()))
        avg_monthly = total / self._mois_couverts(list(by_month))

        # Project annual income
        if by_month_sorted:
            recent_months = list(by_month_sorted.values())[-3:]
            projected_monthly = sum(recent_months) / len(recent_months)
        else:
            projected_monthly = 0

        return {
            "total_income": round(total, 2),
            "avg_monthly": round(avg_monthly, 2),
            "projected_annual": round(projected_monthly * 12, 2),
            "by_type": {k: round(v, 2) for k, v in sorted(by_type.items(), key=lambda x: -x[1])},
            "by_asset": {k: round(v, 2) for k, v in sorted(by_asset.items(), key=lambda x: -x[1])[:10]},
            "by_month": {k: round(v, 2) for k, v in by_month_sorted.items()},
            "nb_events": len(txns),
            "history": history[:30],
        }

    # ------------------------------------------------------------------
    # DCA Backtester
    # ------------------------------------------------------------------

    async def backtest_dca(
        self,
        symbol: str,
        asset_type: str,
        monthly_amount: float,
        start_year: int,
        start_month: int = 1,
    ) -> dict:
        """Backtest DCA strategy: invest fixed amount monthly since a given date.

        Returns what the portfolio would be worth today.
        """
        from app.core.config import settings
        from app.ml.historical_data import HistoricalDataFetcher

        fetcher = HistoricalDataFetcher(coingecko_api_key=getattr(settings, "COINGECKO_API_KEY", None))

        now = datetime.now(timezone.utc)
        start_date = datetime(start_year, start_month, 1)
        total_months = (now.year - start_date.year) * 12 + (now.month - start_date.month)

        if total_months <= 0:
            return {"error": "La date de début doit être dans le passé"}

        # Fetch max historical data
        days = min(total_months * 31 + 30, 365 * 5)  # up to 5 years
        dates, prices = await fetcher.get_history(symbol, asset_type, days=days)
        await fetcher.close()

        if not prices or len(prices) < 30:
            return {"error": f"Pas assez d'historique pour {symbol}"}

        # Build date->price lookup (use closest available date)
        date_price = {}
        for d, p in zip(dates, prices):
            key = d.strftime("%Y-%m")
            date_price[key] = p

        total_invested = 0.0
        total_units = 0.0
        monthly_buys = []

        current = start_date
        while current <= now:
            key = current.strftime("%Y-%m")
            price = date_price.get(key)

            if price and price > 0:
                units_bought = monthly_amount / price
                total_invested += monthly_amount
                total_units += units_bought
                monthly_buys.append(
                    {
                        "month": key,
                        "price": round(price, 4),
                        "units": round(units_bought, 8),
                        "invested": round(total_invested, 2),
                        "value": round(total_units * price, 2),
                    }
                )

            # Next month
            if current.month == 12:
                current = datetime(current.year + 1, 1, 1)
            else:
                current = datetime(current.year, current.month + 1, 1)

        if not monthly_buys:
            return {"error": "Aucune donnée de prix disponible pour cette période"}

        current_price = prices[-1] if prices else 0
        current_value = total_units * current_price
        gain_loss = current_value - total_invested
        gain_loss_pct = (gain_loss / total_invested * 100) if total_invested > 0 else 0
        avg_buy_price = total_invested / total_units if total_units > 0 else 0

        return {
            "symbol": symbol,
            "monthly_amount": monthly_amount,
            "start_date": start_date.strftime("%Y-%m"),
            "nb_months": len(monthly_buys),
            "total_invested": round(total_invested, 2),
            "total_units": round(total_units, 8),
            "avg_buy_price": round(avg_buy_price, 4),
            "current_price": round(current_price, 4),
            "current_value": round(current_value, 2),
            "gain_loss": round(gain_loss, 2),
            "gain_loss_pct": round(gain_loss_pct, 2),
            "monthly_history": monthly_buys,
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _get_user_portfolios(self, db: AsyncSession, user_id: str):
        result = await db.execute(
            select(Portfolio).where(
                Portfolio.user_id == user_id,
            )
        )
        return result.scalars().all()

    async def _get_assets_map(self, db: AsyncSession, portfolio_ids: list):
        result = await db.execute(
            select(Asset).where(
                Asset.portfolio_id.in_(portfolio_ids),
            )
        )
        assets = result.scalars().all()
        asset_map = {str(a.id): a for a in assets}
        asset_ids = list(asset_map.keys())
        return asset_ids, asset_map

    @staticmethod
    def _empty_fees():
        return {
            "total_fees": 0,
            "nb_transactions_with_fees": 0,
            "avg_monthly_fee": 0,
            "by_exchange": {},
            "by_asset": {},
            "by_type": {},
            "by_month": {},
            "recent_fees": [],
        }

    @staticmethod
    def _empty_passive_income():
        return {
            "total_income": 0,
            "avg_monthly": 0,
            "projected_annual": 0,
            "by_type": {},
            "by_asset": {},
            "by_month": {},
            "nb_events": 0,
            "history": [],
        }


insights_service = InsightsService()
