"""Modèles de stratégie paramétrés : échéancier et description de la règle.

Tout ce qui est calculé ici découle **uniquement** des paramètres saisis par l'utilisateur (actifs, budget,
fréquence, seuils, valeurs). Aucune lecture de ses positions, de sa liquidité, des signaux ou des scores du
moteur de prévision : l'outil applique la règle choisie, il ne choisit rien à la place de l'utilisateur.
"""

import calendar
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from pydantic import TypeAdapter, ValidationError

from app.domains.strategies.schemas import (
    DcaParams,
    ProfitTakingParams,
    RebalanceParams,
    ScheduleLine,
    TemplateParams,
    VcaParams,
)

TemplateParamsModel = DcaParams | VcaParams | ProfitTakingParams | RebalanceParams

TEMPLATE_LABELS: dict[str, str] = {
    "dca": "Achat périodique (DCA)",
    "vca": "Value averaging (VCA)",
    "profit_taking": "Prise de profits par paliers",
    "rebalance": "Rééquilibrage vers une allocation cible",
}

_FREQUENCY_LABELS: dict[str, str] = {
    "weekly": "chaque semaine",
    "biweekly": "toutes les deux semaines",
    "monthly": "chaque mois",
    "quarterly": "chaque trimestre",
}

_PARAMS_ADAPTER: TypeAdapter[TemplateParamsModel] = TypeAdapter(TemplateParams)


def parse_template_params(params: dict[str, Any] | None) -> TemplateParamsModel | None:
    """Paramètres d'un modèle si ``params`` en décrit un valide ; ``None`` pour une stratégie libre ou héritée."""
    if not params or "template" not in params:
        return None
    try:
        return _PARAMS_ADAPTER.validate_python(params)
    except ValidationError:
        return None


def eur(amount: float) -> str:
    """Montant au format français : ``1 234,56 €``."""
    text = f"{amount:,.2f}".replace(",", " ").replace(".", ",")
    return f"{text} €"


def _qty(quantity: float) -> str:
    text = f"{quantity:.8f}".rstrip("0").rstrip(".")
    return text.replace(".", ",")


def _pct(value: float) -> str:
    return f"{value:g}".replace(".", ",") + " %"


def _day(d: date) -> str:
    return d.strftime("%d/%m/%Y")


def _add_months(d: date, months: int) -> date:
    index = d.month - 1 + months
    year, month = d.year + index // 12, index % 12 + 1
    return date(year, month, min(d.day, calendar.monthrange(year, month)[1]))


def schedule_dates(start: date, frequency: str, periods: int) -> list[date]:
    """Dates des ``periods`` échéances à partir de ``start`` ; les mois courts ramènent au dernier jour du mois."""
    if frequency == "weekly":
        return [start + timedelta(weeks=k) for k in range(periods)]
    if frequency == "biweekly":
        return [start + timedelta(weeks=2 * k) for k in range(periods)]
    step = 3 if frequency == "quarterly" else 1
    return [_add_months(start, step * k) for k in range(periods)]


def _cadence(frequency: str, periods: int, start: date) -> str:
    plural = "échéance" if periods == 1 else "échéances"
    return f"{_FREQUENCY_LABELS[frequency]}, {periods} {plural} à partir du {_day(start)}"


def describe_rule(params: TemplateParamsModel) -> str:
    """Texte descriptif de la règle telle que l'utilisateur l'a paramétrée."""
    if isinstance(params, DcaParams):
        split = " · ".join(f"{a.symbol} {_pct(a.weight_pct)}" for a in params.assets)
        return (
            f"Achat périodique : {eur(params.amount_per_period)} "
            f"{_cadence(params.frequency, params.periods, params.start_date)}, répartis {split}."
        )
    if isinstance(params, VcaParams):
        cap = f", plafonné à {eur(params.max_per_period)} par échéance" if params.max_per_period else ""
        excess = "l'excédent est revendu" if params.allow_sell else "aucune vente si la ligne dépasse la cible"
        return (
            f"Value averaging sur {params.symbol} : la valeur visée de la ligne augmente de "
            f"{eur(params.target_increment)} {_cadence(params.frequency, params.periods, params.start_date)} ; "
            f"à chaque échéance on investit l'écart entre la cible et la valeur de la ligne{cap} ; {excess}."
        )
    if isinstance(params, ProfitTakingParams):
        tiers = ", ".join(f"{_pct(t.sell_pct)} à {eur(t.price)}" for t in params.tiers)
        total = sum(t.sell_pct for t in params.tiers)
        return (
            f"Prise de profits par paliers sur {_qty(params.quantity)} {params.symbol} : {tiers} "
            f"({_pct(round(total, 2))} de la quantité au total)."
        )
    split = " · ".join(f"{line.symbol} {_pct(line.target_pct)}" for line in params.lines)
    contribution = f", apport de {eur(params.contribution)} à répartir" if params.contribution > 0 else ""
    return (
        f"Rééquilibrage vers {split}, revue {_cadence(params.frequency, params.periods, params.start_date)}, "
        f"seuil d'écart {_pct(params.threshold_pct).replace(' %', ' point(s)')}{contribution}."
    )


def _dca_schedule(params: DcaParams) -> list[ScheduleLine]:
    dates = schedule_dates(params.start_date, params.frequency, params.periods)
    lines: list[ScheduleLine] = []
    for k, d in enumerate(dates, start=1):
        for asset in params.assets:
            amount = round(params.amount_per_period * asset.weight_pct / 100, 2)
            lines.append(
                ScheduleLine(
                    date=d,
                    action="BUY",
                    symbol=asset.symbol,
                    amount=amount,
                    note=(
                        f"Échéance {k}/{len(dates)} : {eur(amount)} sur {asset.symbol} "
                        f"({_pct(asset.weight_pct)} de {eur(params.amount_per_period)})"
                    ),
                )
            )
    return lines


def vca_first_amount(params: VcaParams) -> float:
    """La ligne part de zéro : la première échéance investit l'incrément, dans la limite du plafond."""
    first = params.target_increment
    if params.max_per_period is not None:
        first = min(first, params.max_per_period)
    return round(first, 2)


def _vca_schedule(params: VcaParams) -> list[ScheduleLine]:
    dates = schedule_dates(params.start_date, params.frequency, params.periods)
    cap = f", plafonné à {eur(params.max_per_period)}" if params.max_per_period else ""
    excess = "l'excédent est vendu" if params.allow_sell else "rien n'est acheté"
    lines: list[ScheduleLine] = []
    for k, d in enumerate(dates, start=1):
        target = round(params.target_increment * k, 2)
        amount: float | None
        if k == 1:
            first = vca_first_amount(params)
            amount = first
            note = (
                f"Échéance 1/{len(dates)} : valeur visée {eur(target)} ; la ligne part de zéro, achat de {eur(first)}"
            )
        else:
            amount = None
            note = (
                f"Échéance {k}/{len(dates)} : valeur visée {eur(target)} ; montant = valeur visée moins valeur de la "
                f"ligne ce jour-là{cap} ; si la ligne dépasse déjà la cible, {excess}"
            )
        lines.append(
            ScheduleLine(date=d, action="BUY", symbol=params.symbol, amount=amount, target_value=target, note=note)
        )
    return lines


def _profit_schedule(params: ProfitTakingParams) -> list[ScheduleLine]:
    lines: list[ScheduleLine] = []
    for i, tier in enumerate(params.tiers, start=1):
        quantity = params.quantity * tier.sell_pct / 100
        proceeds = round(quantity * tier.price, 2)
        lines.append(
            ScheduleLine(
                action="SELL",
                symbol=params.symbol,
                amount=proceeds,
                quantity=round(quantity, 8),
                trigger_price=tier.price,
                note=(
                    f"Palier {i} : si le cours atteint {eur(tier.price)}, vendre {_pct(tier.sell_pct)} de la "
                    f"quantité indiquée, soit {_qty(quantity)} {params.symbol} (≈ {eur(proceeds)})"
                ),
            )
        )
    return lines


def rebalance_trades(
    current: dict[str, float], targets: dict[str, float], contribution: float, threshold_pct: float
) -> dict[str, float] | None:
    """Achats (+) et ventes (-) en EUR qui ramènent ``current`` sur ``targets`` (en %) après l'apport ;
    ``None`` quand aucun écart ne dépasse le seuil et qu'il n'y a pas d'apport à répartir."""
    total_now = sum(current.values())
    total_after = total_now + contribution
    if total_after <= 0:
        return None
    drifts = [abs((current[s] / total_now * 100 if total_now > 0 else 0.0) - targets[s]) for s in targets]
    if contribution <= 0 and max(drifts) <= threshold_pct:
        return None
    return {s: total_after * targets[s] / 100 - current[s] for s in targets}


def _rebalance_schedule(params: RebalanceParams) -> list[ScheduleLine]:
    dates = schedule_dates(params.start_date, params.frequency, params.periods)
    current = {line.symbol: line.current_value for line in params.lines}
    targets = {line.symbol: line.target_pct for line in params.lines}
    total_now = sum(current.values())
    trades = rebalance_trades(current, targets, params.contribution, params.threshold_pct)
    lines: list[ScheduleLine] = []
    if trades is None:
        lines.append(
            ScheduleLine(
                date=dates[0],
                action="REVIEW",
                note=f"Revue 1/{len(dates)} : aucun écart ne dépasse le seuil, rien à faire à cette date",
            )
        )
    else:
        for symbol, delta in trades.items():
            if abs(delta) < 0.01:
                continue
            weight_now = current[symbol] / total_now * 100 if total_now > 0 else 0.0
            verb = "acheter" if delta > 0 else "vendre"
            lines.append(
                ScheduleLine(
                    date=dates[0],
                    action="BUY" if delta > 0 else "SELL",
                    symbol=symbol,
                    amount=round(abs(delta), 2),
                    note=(
                        f"Revue 1/{len(dates)} : ramener {symbol} de {_pct(round(weight_now, 1))} à "
                        f"{_pct(targets[symbol])}, {verb} {eur(abs(delta))}"
                    ),
                )
            )
    for k, d in enumerate(dates[1:], start=2):
        lines.append(
            ScheduleLine(
                date=d,
                action="REVIEW",
                note=(
                    f"Revue {k}/{len(dates)} : comparer l'allocation à la cible et rééquilibrer si un écart "
                    f"dépasse {_pct(params.threshold_pct).replace(' %', ' point(s)')}"
                ),
            )
        )
    return lines


def build_schedule(params: TemplateParamsModel) -> list[ScheduleLine]:
    """Échéancier de la règle ; les montants sont ceux que les paramètres impliquent, rien de plus."""
    if isinstance(params, DcaParams):
        return _dca_schedule(params)
    if isinstance(params, VcaParams):
        return _vca_schedule(params)
    if isinstance(params, ProfitTakingParams):
        return _profit_schedule(params)
    return _rebalance_schedule(params)


def schedule_totals(schedule: list[ScheduleLine]) -> tuple[float, float, bool]:
    """Total des achats, total des ventes, et présence d'échéances dont le montant se calcule à l'échéance."""
    buy = sum(line.amount or 0 for line in schedule if line.action == "BUY")
    sell = sum(line.amount or 0 for line in schedule if line.action == "SELL")
    deferred = any(line.amount is None for line in schedule if line.action in ("BUY", "SELL"))
    return round(buy, 2), round(sell, 2), deferred


def actions_from_schedule(schedule: list[ScheduleLine]) -> list[dict[str, Any]]:
    """Actions PENDING à enregistrer : une par achat ou vente de l'échéancier (les revues restent dans l'aperçu)."""
    return [
        {
            "action": line.action,
            "symbol": line.symbol,
            "amount": line.amount,
            "currency": "EUR",
            "reason": line.note,
            "scheduled_at": datetime.combine(line.date, time(0), tzinfo=UTC) if line.date else None,
        }
        for line in schedule
        if line.action in ("BUY", "SELL")
    ]
