"""Strategy service — deployment capacity, munitions intelligence and execution P&L.

Compares available liquidity (Cash + Stablecoins) with the next Alpha
signal to determine whether the user can execute the recommended trade.

Also measures what EXECUTED strategy actions actually returned, closing the
decision loop: AI proposes → user executes → we verify.
"""

import logging
from bisect import bisect_right
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Dict, List, Optional, Sequence, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


# Strategy profile presets: what % of incoming DCA goes to risk vs reserve
PROFILE_ALLOCATION = {
    "aggressive": {"risk_pct": 90, "reserve_pct": 10},
    "moderate": {"risk_pct": 70, "reserve_pct": 30},
    "conservative": {"risk_pct": 40, "reserve_pct": 60},
}


@dataclass
class DeploymentCapacity:
    """Result of deployment capacity check."""

    available_liquidity: float
    total_value: float
    liquidity_pct: float  # % of portfolio that is liquid
    invested_pct: float  # % of portfolio that is invested (risky)

    # Next alpha signal
    next_signal_symbol: Optional[str] = None
    next_signal_action: Optional[str] = None
    next_signal_amount: float = 0.0
    can_execute: bool = True
    shortfall: float = 0.0
    message: Optional[str] = None

    # Deployment suggestion based on profile
    profile: str = "moderate"
    deploy_to_risk: float = 0.0
    keep_in_reserve: float = 0.0


# ── Execution performance (pure functions — unit tested) ────────────────────

# Action labels are free-form French/English strings ("ACHAT FORT", "DCA",
# "PRENDRE PROFITS", …) — classify them into a buy/sell direction.
_BUY_KEYWORDS = ("BUY", "ACHAT", "DCA", "RENFORCER", "ACCUMULER")
_SELL_KEYWORDS = ("SELL", "VENDRE", "ALLÉGER", "ALLEGER", "PROFITS")


def classify_action_direction(action: Optional[str]) -> Optional[str]:
    """Map a free-form action label to "buy" / "sell", or None if undecidable.

    HOLD / OBSERVER / SWAP and unknown labels return None (not evaluable):
    they have no unambiguous cash-flow direction.
    """
    if not action:
        return None
    label = action.upper()
    if any(k in label for k in _SELL_KEYWORDS):
        return "sell"
    if any(k in label for k in _BUY_KEYWORDS):
        return "buy"
    return None


def compute_action_performance(
    direction: str,
    amount_eur: float,
    price_at_execution: float,
    current_price: float,
) -> Dict[str, float]:
    """Compute the realized impact of one executed action (pure function).

    For a BUY: pnl = amount × (current/exec − 1) — a true unrealized P&L on
    the amount deployed.

    For a SELL the result is an *impact* (avoided gain/loss), NOT a P&L in the
    strict sense: pnl = amount × (1 − current/exec). Selling before a drop is
    a positive impact (loss avoided); selling before a rally is a negative
    impact (missed gain). The frontend labels sells as "impact".

    baseline_eur is what the position would have done with NO action:
    - buy  → 0 (no purchase, no exposure);
    - sell → amount × (current/exec − 1) (we would have kept the position).
    Comparing pnl_eur to baseline_eur answers "did acting beat doing nothing?".

    Raises ValueError on non-positive inputs or unknown direction — callers
    must filter those actions out as "non evaluable" beforehand.
    """
    if direction not in ("buy", "sell"):
        raise ValueError(f"Unknown direction: {direction!r}")
    if amount_eur <= 0 or price_at_execution <= 0 or current_price <= 0:
        raise ValueError("amount_eur, price_at_execution and current_price must be > 0")

    ratio = current_price / price_at_execution
    if direction == "buy":
        pnl_eur = amount_eur * (ratio - 1)
        pnl_pct = (ratio - 1) * 100
        baseline_eur = 0.0
    else:  # sell
        pnl_eur = amount_eur * (1 - ratio)
        pnl_pct = (1 - ratio) * 100
        baseline_eur = amount_eur * (ratio - 1)

    return {
        "pnl_eur": round(pnl_eur, 2),
        "pnl_pct": round(pnl_pct, 2),
        "baseline_eur": round(baseline_eur, 2),
    }


def aggregate_strategy_performance(
    evaluated: Sequence[Dict],
    executed_count: int,
    skipped_count: int,
    pending_count: int,
    non_evaluable_count: int,
) -> Dict:
    """Aggregate per-action results into strategy-level totals (pure function).

    - total_impact_eur: sum of per-action pnl/impact.
    - baseline_no_action_eur: total outcome had NO action been executed.
    - vs_baseline_eur: how much executing beat (or trailed) doing nothing.
    - follow_rate_pct: executed / (executed + skipped); None when no action
      has been decided on yet (avoids a misleading 0%).
    """
    total_impact = sum(line["pnl_eur"] for line in evaluated)
    baseline_total = sum(line["baseline_eur"] for line in evaluated)
    decided = executed_count + skipped_count
    follow_rate = round(executed_count / decided * 100, 1) if decided > 0 else None

    return {
        "total_impact_eur": round(total_impact, 2),
        "baseline_no_action_eur": round(baseline_total, 2),
        "vs_baseline_eur": round(total_impact - baseline_total, 2),
        "executed_count": executed_count,
        "skipped_count": skipped_count,
        "pending_count": pending_count,
        "non_evaluable_count": non_evaluable_count,
        "follow_rate_pct": follow_rate,
        "evaluated_count": len(evaluated),
    }


# Max staleness tolerated when looking up the price at execution date
# (weekends / missed cache runs leave gaps in daily closes).
_EXEC_PRICE_TOLERANCE_DAYS = 7


class StrategyService:
    """Munitions intelligence and deployment capacity."""

    async def get_deployment_capacity(
        self,
        db: AsyncSession,
        user_id: str,
        monthly_dca: float = 300.0,
        profile: str = "moderate",
    ) -> DeploymentCapacity:
        """Compare available liquidity with next Alpha signal.

        Returns deployment capacity including whether the user can execute
        the top recommended trade and how to split the monthly DCA.
        """
        from app.services.metrics_service import metrics_service

        # 1. Get dashboard metrics for liquidity + total value
        try:
            dashboard = await metrics_service.get_user_dashboard_metrics(db, user_id)
            # Round euro amounts to cents so float aggregation artifacts never leak
            # into the advisory response (these are guidance figures, not ledger math).
            available_liquidity = round(float(dashboard.get("available_liquidity", 0)), 2)
            total_value = round(float(dashboard.get("total_value", 0)), 2)
        except Exception as e:
            logger.warning("Failed to get dashboard metrics: %s", e)
            available_liquidity = 0.0
            total_value = 0.0

        # 2. Compute allocation split
        liquidity_pct = round(available_liquidity / total_value * 100, 1) if total_value > 0 else 0.0
        invested_pct = round(100 - liquidity_pct, 1)

        # 3. Get top Alpha signal from strategy table
        next_symbol = None
        next_action = None
        next_amount = 0.0
        try:
            from app.services.prediction_service import prediction_service

            strategy_data = await prediction_service.get_strategy_map(db, user_id)
            assets = strategy_data.get("assets", [])
            # Find the first buy/DCA signal
            for asset in assets:
                action = asset.get("action", "")
                if "ACHAT" in action or action == "DCA":
                    next_symbol = asset.get("symbol")
                    next_action = action
                    next_amount = round(float(asset.get("impact_eur", 0)), 2)
                    break
        except Exception as e:
            logger.warning("Failed to get strategy table: %s", e)

        # 4. Can we execute?
        can_execute = available_liquidity >= next_amount if next_amount > 0 else True
        shortfall = round(max(0, next_amount - available_liquidity), 2) if not can_execute else 0.0
        message = None
        if not can_execute and next_symbol:
            message = (
                f"Liquidité insuffisante pour le signal Alpha sur {next_symbol} "
                f"({next_amount:.2f} € requis, {available_liquidity:.2f} € disponible)."
            )

        # 5. DCA deployment suggestion based on profile
        alloc = PROFILE_ALLOCATION.get(profile, PROFILE_ALLOCATION["moderate"])
        deploy_risk = round(monthly_dca * alloc["risk_pct"] / 100, 2)
        keep_reserve = round(monthly_dca * alloc["reserve_pct"] / 100, 2)

        return DeploymentCapacity(
            available_liquidity=available_liquidity,
            total_value=total_value,
            liquidity_pct=liquidity_pct,
            invested_pct=invested_pct,
            next_signal_symbol=next_symbol,
            next_signal_action=next_action,
            next_signal_amount=next_amount,
            can_execute=can_execute,
            shortfall=shortfall,
            message=message,
            profile=profile,
            deploy_to_risk=deploy_risk,
            keep_in_reserve=keep_reserve,
        )

    async def get_strategy_performance(self, db: AsyncSession, actions: Sequence) -> Dict:
        """Measure what EXECUTED actions of a strategy actually returned.

        Prices come from AssetPriceHistory (daily closes persisted by the
        history-cache task) — no external API call, so the endpoint stays fast
        and deterministic:
        - price_at_execution: last close ≤ executed_at date, within
          _EXEC_PRICE_TOLERANCE_DAYS;
        - current_price: latest close available for the symbol.
        Executed actions whose price cannot be resolved (or with no symbol /
        amount / non-EUR currency / undecidable direction) are excluded from
        the totals and reported in non_evaluable.
        """
        from app.models.asset_price_history import AssetPriceHistory
        from app.models.strategy import ActionStatus

        executed = [a for a in actions if a.status == ActionStatus.EXECUTED]
        skipped_count = sum(1 for a in actions if a.status == ActionStatus.SKIPPED)
        pending_count = sum(1 for a in actions if a.status == ActionStatus.PENDING)

        # Split executed actions into candidates vs immediately non-evaluable
        candidates = []
        non_evaluable: List[Dict] = []
        for a in executed:
            direction = classify_action_direction(a.action)
            amount = float(a.amount) if a.amount is not None else 0.0
            if not a.symbol:
                non_evaluable.append(self._ne(a, "Pas de symbole associé"))
            elif direction is None:
                non_evaluable.append(self._ne(a, f"Direction non déterminable ({a.action})"))
            elif amount <= 0:
                non_evaluable.append(self._ne(a, "Montant manquant ou nul"))
            elif (a.currency or "EUR").upper() != "EUR":
                non_evaluable.append(self._ne(a, f"Devise non supportée ({a.currency})"))
            elif a.executed_at is None:
                non_evaluable.append(self._ne(a, "Date d'exécution inconnue"))
            else:
                candidates.append((a, direction, amount))

        # Batch-load daily closes for all involved symbols
        prices_by_symbol: Dict[str, List[Tuple[date, float]]] = {}
        if candidates:
            symbols = {a.symbol.upper() for a, _, _ in candidates}
            min_exec = min(a.executed_at.date() for a, _, _ in candidates)
            cutoff = min_exec - timedelta(days=_EXEC_PRICE_TOLERANCE_DAYS)
            result = await db.execute(
                select(
                    AssetPriceHistory.symbol,
                    AssetPriceHistory.price_date,
                    AssetPriceHistory.price_eur,
                )
                .where(
                    AssetPriceHistory.symbol.in_(symbols),
                    AssetPriceHistory.price_date >= cutoff,
                )
                .order_by(AssetPriceHistory.symbol, AssetPriceHistory.price_date)
            )
            for sym, pdate, price in result.all():
                prices_by_symbol.setdefault(sym.upper(), []).append((pdate, float(price)))

        evaluated: List[Dict] = []
        for a, direction, amount in candidates:
            sym = a.symbol.upper()
            series = prices_by_symbol.get(sym, [])
            exec_date = a.executed_at.date()
            exec_price, exec_price_date = self._price_at(series, exec_date)
            if exec_price is None:
                non_evaluable.append(self._ne(a, "Prix introuvable au jour d'exécution"))
                continue
            current_date, current_price = series[-1]
            if current_price <= 0:
                non_evaluable.append(self._ne(a, "Prix actuel indisponible"))
                continue

            perf = compute_action_performance(direction, amount, exec_price, current_price)
            evaluated.append(
                {
                    "action_id": str(a.id),
                    "symbol": sym,
                    "action": a.action,
                    "direction": direction,
                    "amount_eur": round(amount, 2),
                    "executed_at": a.executed_at.isoformat(),
                    "price_at_execution": exec_price,
                    "price_at_execution_date": exec_price_date.isoformat(),
                    "current_price": current_price,
                    "current_price_date": current_date.isoformat(),
                    **perf,
                }
            )

        summary = aggregate_strategy_performance(
            evaluated,
            executed_count=len(executed),
            skipped_count=skipped_count,
            pending_count=pending_count,
            non_evaluable_count=len(non_evaluable),
        )
        return {
            "lines": evaluated,
            "non_evaluable": non_evaluable,
            **summary,
            "sell_note": (
                "Pour les ventes, l'impact mesure le gain/perte évité depuis la vente "
                "(pas un P&L réalisé). La baseline « ne rien faire » suppose la position conservée."
            ),
        }

    @staticmethod
    def _ne(action, reason: str) -> Dict:
        """Build a non-evaluable entry."""
        return {
            "action_id": str(action.id),
            "symbol": action.symbol,
            "action": action.action,
            "reason": reason,
        }

    @staticmethod
    def _price_at(series: List[Tuple[date, float]], target: date) -> Tuple[Optional[float], Optional[date]]:
        """Last daily close ≤ target within the tolerance window (series sorted by date)."""
        if not series:
            return None, None
        dates = [d for d, _ in series]
        idx = bisect_right(dates, target) - 1
        if idx < 0:
            return None, None
        pdate, price = series[idx]
        if (target - pdate).days > _EXEC_PRICE_TOLERANCE_DAYS or price <= 0:
            return None, None
        return price, pdate


# Singleton
strategy_service = StrategyService()
