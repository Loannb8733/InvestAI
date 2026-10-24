import io
from datetime import datetime
from typing import Annotated, Any, NoReturn

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import distinct, extract, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.session import get_session
from app.core.rate_limit import limiter
from app.domains.identity.dependencies import CurrentUser
from app.domains.identity.models import User
from app.domains.portfolio.models import Asset, Portfolio
from app.domains.reports.performance_excel import render_performance_excel
from app.domains.reports.performance_pdf import render_performance_pdf
from app.domains.reports.rebalancing import RebalancingReport
from app.domains.reports.rebalancing_pdf import render_rebalancing_pdf
from app.domains.reports.schemas import RebalancingRequest
from app.domains.reports.service import report_service
from app.domains.reports.tax_excel import render_tax_excel
from app.domains.reports.tax_pdf import render_tax_pdf
from app.domains.reports.transactions_export import (
    render_transactions_csv,
    render_transactions_excel,
    render_transactions_pdf,
)
from app.domains.transactions.models import Transaction

router = APIRouter()

Session = Annotated[AsyncSession, Depends(get_session)]

PDF = "application/pdf"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
SECURITIES_UNAVAILABLE = "Rapport Valeurs Mobilières non disponible - fonctionnalité en cours de développement"


def _currency(user: User) -> str:
    currency: str = getattr(user, "preferred_currency", "EUR") or "EUR"
    return currency


def _today() -> str:
    return datetime.now().strftime("%Y%m%d")


def _tax_file_year(year: int) -> int:
    if year < 2015 or year > datetime.now().year:
        return datetime.now().year - 1
    return year


def _attachment(content: bytes, media_type: str, filename: str) -> StreamingResponse:
    return StreamingResponse(
        io.BytesIO(content),
        media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


async def _transaction_years(session: AsyncSession, user: User) -> list[int]:
    years_result = await session.execute(
        select(distinct(extract("year", Transaction.executed_at)))
        .join(Asset, Transaction.asset_id == Asset.id)
        .join(Portfolio, Asset.portfolio_id == Portfolio.id)
        .where(Portfolio.user_id == user.id)
        .order_by(extract("year", Transaction.executed_at).desc())
    )
    return [int(y) for y in years_result.scalars().all() if y]


def _rebalancing_payload(report: RebalancingReport) -> dict[str, Any]:
    return {
        "total_value": report.total_value,
        "categories": report.categories,
        "orders": [
            {
                "category": o.category,
                "action": o.action,
                "amount_eur": o.amount_eur,
                "current_pct": o.current_pct,
                "target_pct": o.target_pct,
                "drift_pct": o.drift_pct,
                "estimated_gain": o.estimated_gain,
                "estimated_tax": o.estimated_tax,
            }
            for o in report.orders
        ],
        "total_sell_amount": report.total_sell_amount,
        "total_buy_amount": report.total_buy_amount,
        "total_estimated_gain": report.total_estimated_gain,
        "total_estimated_tax": report.total_estimated_tax,
        "hhi_before": report.hhi_before,
        "hhi_after": report.hhi_after,
    }


@router.get("/performance/pdf")
@limiter.limit("10/minute")
async def get_performance_report_pdf(request: Request, user: CurrentUser, session: Session) -> StreamingResponse:
    data = await report_service.get_report_data(session, str(user.id), currency=_currency(user))
    return _attachment(render_performance_pdf(data), PDF, f"rapport_performance_{_today()}.pdf")


@router.get("/performance/excel")
@limiter.limit("10/minute")
async def get_performance_report_excel(request: Request, user: CurrentUser, session: Session) -> StreamingResponse:
    data = await report_service.get_report_data(session, str(user.id), currency=_currency(user))
    return _attachment(render_performance_excel(data), XLSX, f"rapport_performance_{_today()}.xlsx")


@router.get("/tax/{year}/summary", response_model=None)
@limiter.limit("20/minute")
async def get_tax_summary(request: Request, year: int, user: CurrentUser, session: Session) -> dict[str, Any]:
    """Synthèse 2086 en JSON : vraie base imposable (acquisition globale, cessions crypto→fiat de l'année).

    Le détail des cessions est réservé au PDF.
    """
    if year < 2015 or year > datetime.now().year:
        year = datetime.now().year

    tax = await report_service.compute_tax_2086(session, str(user.id), year)
    return {
        "year": tax.year,
        "nb_cessions": tax.nb_cessions,
        "total_cessions": round(tax.total_cessions, 2),
        "total_plus_values": round(tax.total_plus_values, 2),
        "total_moins_values": round(tax.total_moins_values, 2),
        "net_plus_value": round(tax.net_plus_value, 2),
        "flat_tax_30": round(tax.flat_tax_30, 2),
        "ir_12_8": round(tax.ir_12_8, 2),
        "ps_17_2": round(tax.ps_17_2, 2),
    }


@router.get("/tax/{year}/pdf")
@limiter.limit("10/minute")
async def get_tax_report_pdf(request: Request, year: int, user: CurrentUser, session: Session) -> StreamingResponse:
    year = _tax_file_year(year)
    tax = await report_service.compute_tax_2086(session, str(user.id), year)
    return _attachment(render_tax_pdf(tax, year), PDF, f"declaration_fiscale_crypto_{year}.pdf")


@router.get("/tax/{year}/excel")
@limiter.limit("10/minute")
async def get_tax_report_excel(request: Request, year: int, user: CurrentUser, session: Session) -> StreamingResponse:
    year = _tax_file_year(year)
    tax = await report_service.compute_tax_2086(session, str(user.id), year)
    return _attachment(render_tax_excel(tax, year), XLSX, f"declaration_fiscale_crypto_{year}.xlsx")


@router.get("/tax/securities/{year}/pdf", response_model=None)
@limiter.limit("10/minute")
async def get_securities_tax_report_pdf(request: Request, year: int, user: CurrentUser) -> NoReturn:
    raise HTTPException(status_code=501, detail=SECURITIES_UNAVAILABLE)


@router.get("/tax/securities/{year}/excel", response_model=None)
@limiter.limit("10/minute")
async def get_securities_tax_report_excel(request: Request, year: int, user: CurrentUser) -> NoReturn:
    raise HTTPException(status_code=501, detail=SECURITIES_UNAVAILABLE)


@router.get("/transactions/pdf")
@limiter.limit("10/minute")
async def get_transactions_report_pdf(
    request: Request, user: CurrentUser, session: Session, year: int | None = None
) -> StreamingResponse:
    data = await report_service.get_report_data(session, str(user.id), year, currency=_currency(user))
    year_str = str(year) if year else "all"
    return _attachment(render_transactions_pdf(data), PDF, f"rapport_transactions_{year_str}_{_today()}.pdf")


@router.get("/transactions/excel")
@limiter.limit("10/minute")
async def get_transactions_report_excel(
    request: Request, user: CurrentUser, session: Session, year: int | None = None
) -> StreamingResponse:
    data = await report_service.get_report_data(session, str(user.id), year, currency=_currency(user))
    year_str = str(year) if year else "all"
    return _attachment(render_transactions_excel(data), XLSX, f"transactions_{year_str}_{_today()}.xlsx")


@router.get("/transactions/csv")
@limiter.limit("10/minute")
async def get_transactions_report_csv(
    request: Request, user: CurrentUser, session: Session, year: int | None = None
) -> StreamingResponse:
    data = await report_service.get_report_data(session, str(user.id), year, currency=_currency(user))
    year_str = str(year) if year else "all"
    return _attachment(render_transactions_csv(data), "text/csv", f"transactions_{year_str}_{_today()}.csv")


@router.get("/available-years", response_model=None)
@limiter.limit("10/minute")
async def get_available_years(request: Request, user: CurrentUser, session: Session) -> dict[str, Any]:
    years = await _transaction_years(session, user)
    if not years:
        years = [datetime.now().year]
    return {"years": years}


@router.post("/rebalancing", response_model=None)
@limiter.limit("10/minute")
async def get_rebalancing_report(
    request: Request, body: RebalancingRequest, user: CurrentUser, session: Session
) -> dict[str, Any]:
    report = await report_service.get_rebalancing_report(
        session, str(user.id), body.target_allocations, currency=_currency(user)
    )
    return _rebalancing_payload(report)


@router.get("/rebalancing/targets", response_model=None)
@limiter.limit("30/minute")
async def get_rebalancing_targets(request: Request, user: CurrentUser) -> dict[str, Any]:
    """Allocation cible enregistrée de l'utilisateur (null si jamais définie)."""
    return {"targets": user.target_allocations}


@router.put("/rebalancing/targets", response_model=None)
@limiter.limit("10/minute")
async def save_rebalancing_targets(
    request: Request, body: RebalancingRequest, user: CurrentUser, session: Session
) -> dict[str, Any]:
    """Persiste l'allocation cible, validée comme pour le rapport (somme = 1.0)."""
    user.target_allocations = body.target_allocations
    await session.commit()
    return {"targets": user.target_allocations}


@router.get("/rebalancing/drift", response_model=None)
@limiter.limit("30/minute")
async def get_rebalancing_drift(request: Request, user: CurrentUser, session: Session) -> dict[str, Any]:
    """Écart à l'allocation cible pour le dashboard, sans estimation fiscale (pas de replay FIFO)."""
    targets = user.target_allocations
    if not targets:
        return {"targets": None, "categories": [], "max_drift_pct": 0.0, "total_crypto_value": 0.0}

    report = await report_service.get_rebalancing_report(
        session, str(user.id), targets, currency=_currency(user), estimate_tax=False
    )
    max_drift = max((abs(c["drift_pct"]) for c in report.categories), default=0.0)
    return {
        "targets": targets,
        "categories": report.categories,
        "max_drift_pct": round(max_drift, 2),
        "total_crypto_value": report.total_value,
    }


@router.post("/rebalancing/pdf")
@limiter.limit("10/minute")
async def get_rebalancing_report_pdf(
    request: Request, body: RebalancingRequest, user: CurrentUser, session: Session
) -> StreamingResponse:
    report = await report_service.get_rebalancing_report(
        session, str(user.id), body.target_allocations, currency=_currency(user)
    )
    return _attachment(render_rebalancing_pdf(report), PDF, f"rapport_reequilibrage_{_today()}.pdf")
