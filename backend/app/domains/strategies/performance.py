from bisect import bisect_right
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.market_data.history.models import AssetPriceHistory
from app.domains.strategies.models import ActionStatus, StrategyAction

_BUY_KEYWORDS = ("BUY", "ACHAT", "DCA", "RENFORCER", "ACCUMULER")
_SELL_KEYWORDS = ("SELL", "VENDRE", "ALLÉGER", "ALLEGER", "PROFITS")
_EXEC_PRICE_TOLERANCE_DAYS = 7
_SELL_NOTE = (
    "Pour les ventes, l'impact mesure le gain/perte évité depuis la vente "
    "(pas un P&L réalisé). La baseline « ne rien faire » suppose la position conservée."
)


@dataclass(frozen=True)
class _Candidate:
    action: StrategyAction
    direction: str
    amount: float
    symbol: str
    executed_at: datetime


def classify_action_direction(action: str | None) -> str | None:
    """Classe un libellé libre (« ACHAT FORT », « DCA », « PRENDRE PROFITS »…) en ``"buy"`` ou ``"sell"`` ;
    ``None`` pour HOLD, OBSERVER, SWAP et tout libellé inconnu, sans sens de flux univoque."""
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
) -> dict[str, float]:
    """Impact d'une action exécutée. Achat : ``montant * (courant/exécution - 1)``, un P&L latent. Vente :
    ``montant * (1 - courant/exécution)``, le gain ou la perte évités, pas un P&L réalisé. ``baseline_eur`` est le
    résultat sans agir : 0 pour un achat, la position conservée pour une vente. Lève ``ValueError`` sur un sens
    inconnu ou une valeur non strictement positive."""
    if direction not in ("buy", "sell"):
        raise ValueError(f"Unknown direction: {direction!r}")
    if amount_eur <= 0 or price_at_execution <= 0 or current_price <= 0:
        raise ValueError("amount_eur, price_at_execution and current_price must be > 0")

    ratio = current_price / price_at_execution
    if direction == "buy":
        pnl_eur = amount_eur * (ratio - 1)
        pnl_pct = (ratio - 1) * 100
        baseline_eur = 0.0
    else:
        pnl_eur = amount_eur * (1 - ratio)
        pnl_pct = (1 - ratio) * 100
        baseline_eur = amount_eur * (ratio - 1)

    return {
        "pnl_eur": round(pnl_eur, 2),
        "pnl_pct": round(pnl_pct, 2),
        "baseline_eur": round(baseline_eur, 2),
    }


def aggregate_strategy_performance(
    evaluated: Sequence[dict[str, Any]],
    executed_count: int,
    skipped_count: int,
    pending_count: int,
    non_evaluable_count: int,
) -> dict[str, Any]:
    """Totaux d'une stratégie ; ``vs_baseline_eur`` compare l'exécution au « ne rien faire » et ``follow_rate_pct``
    (exécutées / décidées) vaut ``None`` tant qu'aucune action n'est décidée, plutôt qu'un 0 % trompeur."""
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


def _non_evaluable(action: StrategyAction, reason: str) -> dict[str, Any]:
    return {
        "action_id": str(action.id),
        "symbol": action.symbol,
        "action": action.action,
        "reason": reason,
    }


def _candidate_or_reason(a: StrategyAction) -> _Candidate | str:
    direction = classify_action_direction(a.action)
    amount = float(a.amount) if a.amount is not None else 0.0
    if not a.symbol:
        return "Pas de symbole associé"
    if direction is None:
        return f"Direction non déterminable ({a.action})"
    if amount <= 0:
        return "Montant manquant ou nul"
    if (a.currency or "EUR").upper() != "EUR":
        return f"Devise non supportée ({a.currency})"
    if a.executed_at is None:
        return "Date d'exécution inconnue"
    return _Candidate(a, direction, amount, a.symbol, a.executed_at)


def _split_executed(executed: Sequence[StrategyAction]) -> tuple[list[_Candidate], list[dict[str, Any]]]:
    candidates: list[_Candidate] = []
    non_evaluable: list[dict[str, Any]] = []
    for a in executed:
        outcome = _candidate_or_reason(a)
        if isinstance(outcome, str):
            non_evaluable.append(_non_evaluable(a, outcome))
        else:
            candidates.append(outcome)
    return candidates, non_evaluable


async def _load_closes(db: AsyncSession, candidates: list[_Candidate]) -> dict[str, list[tuple[date, float]]]:
    prices_by_symbol: dict[str, list[tuple[date, float]]] = {}
    if not candidates:
        return prices_by_symbol
    symbols = {c.symbol.upper() for c in candidates}
    min_exec = min(c.executed_at.date() for c in candidates)
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
    return prices_by_symbol


def _price_at(series: list[tuple[date, float]], target: date) -> tuple[float, date] | None:
    if not series:
        return None
    dates = [d for d, _ in series]
    idx = bisect_right(dates, target) - 1
    if idx < 0:
        return None
    pdate, price = series[idx]
    if (target - pdate).days > _EXEC_PRICE_TOLERANCE_DAYS or price <= 0:
        return None
    return price, pdate


def _evaluate(c: _Candidate, series: list[tuple[date, float]]) -> dict[str, Any] | str:
    sym = c.symbol.upper()
    found = _price_at(series, c.executed_at.date())
    if found is None:
        return "Prix introuvable au jour d'exécution"
    exec_price, exec_price_date = found
    current_date, current_price = series[-1]
    if current_price <= 0:
        return "Prix actuel indisponible"

    perf = compute_action_performance(c.direction, c.amount, exec_price, current_price)
    return {
        "action_id": str(c.action.id),
        "symbol": sym,
        "action": c.action.action,
        "direction": c.direction,
        "amount_eur": round(c.amount, 2),
        "executed_at": c.executed_at.isoformat(),
        "price_at_execution": exec_price,
        "price_at_execution_date": exec_price_date.isoformat(),
        "current_price": current_price,
        "current_price_date": current_date.isoformat(),
        **perf,
    }


async def compute_strategy_performance(db: AsyncSession, actions: Sequence[StrategyAction]) -> dict[str, Any]:
    """Rendement des actions EXECUTED d'après les clôtures journalières persistées, sans appel externe : prix
    d'exécution = dernière clôture au plus tard le jour d'exécution, à 7 jours près ; prix courant = dernière clôture
    connue. Les actions sans symbole, montant, devise EUR, sens décidable ou prix résolu sont exclues des totaux et
    listées dans ``non_evaluable``."""
    executed = [a for a in actions if a.status == ActionStatus.EXECUTED]
    skipped_count = sum(1 for a in actions if a.status == ActionStatus.SKIPPED)
    pending_count = sum(1 for a in actions if a.status == ActionStatus.PENDING)

    candidates, non_evaluable = _split_executed(executed)
    prices_by_symbol = await _load_closes(db, candidates)

    evaluated: list[dict[str, Any]] = []
    for c in candidates:
        outcome = _evaluate(c, prices_by_symbol.get(c.symbol.upper(), []))
        if isinstance(outcome, str):
            non_evaluable.append(_non_evaluable(c.action, outcome))
        else:
            evaluated.append(outcome)

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
        "sell_note": _SELL_NOTE,
    }
