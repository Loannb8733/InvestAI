from datetime import UTC, datetime

from scipy import optimize as sp_optimize

from app.domains.transactions.models import Transaction, TransactionType

_INFLOW_TYPES = frozenset(
    {
        TransactionType.SELL,
        TransactionType.DIVIDEND,
        TransactionType.INTEREST,
        TransactionType.STAKING_REWARD,
        TransactionType.AIRDROP,
    }
)


def xirr(cashflows: list[tuple[datetime, float]], guess: float = 0.1) -> float | None:
    """TRI annualisé en décimal (0.12 = 12 %) : montant négatif = sortie, positif = entrée, jours / 365.25.

    Brent sur [-0.99, 10] puis Newton depuis guess ; None sous deux flux ou sans convergence.
    """
    if len(cashflows) < 2:
        return None

    dates = [cf[0] for cf in cashflows]
    amounts = [cf[1] for cf in cashflows]
    d0 = min(dates)

    def npv(rate: float) -> float:
        total: float = sum(
            amt / (1.0 + rate) ** ((d - d0).days / 365.25) for d, amt in zip(dates, amounts, strict=False)
        )
        return total

    try:
        result = sp_optimize.brentq(npv, -0.99, 10.0, maxiter=200)
        return float(result)
    except (ValueError, RuntimeError, TypeError, OverflowError):
        try:
            result = sp_optimize.newton(npv, guess, maxiter=200)
            return float(result)
        except (ValueError, RuntimeError, TypeError, OverflowError):
            return None


def build_xirr_cashflows(
    transactions: list[Transaction],
    eur_to_target: float = 1.0,
) -> tuple[list[tuple[datetime, float]], int]:
    """Flux de cash externes du TRI et nombre de lignes ignorées faute de date d'exécution.

    Achat en sortie (frais compris), vente nette de frais et revenus (dividende, intérêt, staking, airdrop)
    en entrée ; transferts, conversions, frais et staking restent hors du calcul. Chaque ligne passe en euros
    à son propre conversion_rate, puis dans la devise cible par eur_to_target.
    """
    cashflows: list[tuple[datetime, float]] = []
    skipped = 0
    for tx in transactions:
        dt = tx.executed_at
        if dt is None:
            skipped += 1
            continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)

        fx = float(tx.conversion_rate) if tx.conversion_rate else 1.0
        to_target = fx * eur_to_target
        amount = float(tx.quantity) * float(tx.price) * to_target
        fee = float(tx.fee or 0) * to_target

        ttype = tx.transaction_type
        if ttype == TransactionType.BUY:
            cashflows.append((dt, -(amount + fee)))
        elif ttype in _INFLOW_TYPES:
            cashflows.append((dt, amount - fee if ttype == TransactionType.SELL else amount))
    return cashflows, skipped
