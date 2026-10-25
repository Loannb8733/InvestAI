import logging
from collections.abc import Sequence
from typing import Any

import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.session import session_factory
from app.domains.predictions.core import PredictionCore, held_assets, user_portfolio_ids
from app.domains.predictions.models import PredictionLog

logger = logging.getLogger(__name__)

RETRAINING_MAPE = 10.0
LOGS_PER_SYMBOL = 20


def _empty_track_record(symbol: str) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "records": [],
        "summary": {
            "total_checked": 0,
            "avg_mape": None,
            "direction_accuracy": None,
            "ci_coverage": None,
        },
    }


def _record(log: PredictionLog) -> dict[str, Any]:
    return {
        "date": log.created_at.isoformat() if log.created_at else None,
        "target_date": log.target_date.isoformat() if log.target_date else None,
        "predicted_price": log.predicted_price,
        "actual_price": log.actual_price,
        "mape": round(log.mape, 1) if log.mape is not None else None,
        "direction_correct": log.direction_correct,
        "ci_covered": log.ci_covered,
        "confidence_low": log.confidence_low,
        "confidence_high": log.confidence_high,
    }


def _rate(hits: int, total: int) -> float | None:
    return round(hits / total * 100, 1) if total > 0 else None


def _track_summary(logs: Sequence[PredictionLog]) -> dict[str, Any]:
    mapes = [log.mape for log in logs if log.mape is not None]
    directions = [log.direction_correct for log in logs if log.direction_correct is not None]
    coverage = [log.ci_covered for log in logs if log.ci_covered is not None]
    return {
        "total_checked": len(logs),
        "avg_mape": round(float(np.mean(mapes)), 1) if mapes else None,
        "direction_accuracy": _rate(sum(1 for d in directions if d), len(directions)),
        "ci_coverage": _rate(sum(1 for c in coverage if c), len(coverage)),
    }


def _empty_backtest(days: int) -> dict[str, Any]:
    return {
        "assets": [],
        "overall_mape": None,
        "overall_direction_accuracy": None,
        "needs_retraining": False,
        "days": days,
    }


def _asset_backtest(sym: str, sym_logs: list[PredictionLog]) -> tuple[dict[str, Any], float | None, list[bool]]:
    mapes = [entry.mape for entry in sym_logs if entry.mape is not None]
    dirs = [entry.direction_correct for entry in sym_logs if entry.direction_correct is not None]
    avg_mape = float(np.mean(mapes)) if mapes else None
    dir_acc = sum(1 for d in dirs if d) / len(dirs) * 100 if dirs else None
    entry = {
        "symbol": sym,
        "samples": len(sym_logs),
        "avg_mape": round(avg_mape, 1) if avg_mape is not None else None,
        "direction_accuracy": round(dir_acc, 1) if dir_acc is not None else None,
    }
    return entry, avg_mape, dirs


def _backtest(symbols: list[str], logs: Sequence[PredictionLog], days: int) -> dict[str, Any]:
    by_symbol: dict[str, list[PredictionLog]] = {}
    for log in logs:
        by_symbol.setdefault(log.symbol, []).append(log)

    asset_results = []
    all_mapes: list[float] = []
    dir_hits = 0
    dir_total = 0
    for sym in symbols:
        entry, avg_mape, dirs = _asset_backtest(sym, by_symbol.get(sym, []))
        if avg_mape is not None:
            all_mapes.append(avg_mape)
        dir_hits += sum(1 for d in dirs if d)
        dir_total += len(dirs)
        asset_results.append(entry)

    overall_mape = float(np.mean(all_mapes)) if all_mapes else None
    overall_dir = dir_hits / dir_total * 100 if dir_total > 0 else None
    return {
        "assets": asset_results,
        "overall_mape": round(overall_mape, 1) if overall_mape is not None else None,
        "overall_direction_accuracy": round(overall_dir, 1) if overall_dir is not None else None,
        "needs_retraining": overall_mape is not None and overall_mape > RETRAINING_MAPE,
        "days": days,
    }


class TrackRecordMixin(PredictionCore):
    async def get_track_record(self, symbol: str, limit: int = 20, user_id: str | None = None) -> dict[str, Any]:
        """Dernières prévisions vérifiées d'un symbole avec leur issue, MAPE moyen, précision de direction et
        couverture de l'intervalle ; vide en cas d'erreur."""
        try:
            async with session_factory() as db:
                filters = [
                    PredictionLog.symbol == symbol.upper(),
                    PredictionLog.accuracy_checked.isnot(None),
                ]
                if user_id:
                    filters.append(PredictionLog.user_id == user_id)
                result = await db.execute(
                    select(PredictionLog).where(*filters).order_by(PredictionLog.created_at.desc()).limit(limit)
                )
                logs = result.scalars().all()
                if not logs:
                    return _empty_track_record(symbol)
                return {
                    "symbol": symbol,
                    "records": [_record(log) for log in logs],
                    "summary": _track_summary(logs),
                }
        except Exception as e:  # noqa: BLE001
            logger.warning("Failed to get track record for %s: %s", symbol, e)
            return _empty_track_record(symbol)

    async def get_portfolio_backtest(self, db: AsyncSession, user_id: str, days: int = 7) -> dict[str, Any]:
        """Prévisions vérifiées à l'horizon `days` des actifs détenus : MAPE et précision de direction par actif
        et globaux, `needs_retraining` au-delà de 10 % de MAPE."""
        portfolio_ids = await user_portfolio_ids(db, user_id)
        if not portfolio_ids:
            return _empty_backtest(days)
        symbols = sorted({a.symbol.upper() for a in await held_assets(db, portfolio_ids)})
        if not symbols:
            return _empty_backtest(days)

        result = await db.execute(
            select(PredictionLog)
            .where(
                PredictionLog.symbol.in_(symbols),
                PredictionLog.accuracy_checked.isnot(None),
                PredictionLog.horizon_days == days,
            )
            .order_by(PredictionLog.created_at.desc())
            .limit(len(symbols) * LOGS_PER_SYMBOL)
        )
        return _backtest(symbols, result.scalars().all(), days)
