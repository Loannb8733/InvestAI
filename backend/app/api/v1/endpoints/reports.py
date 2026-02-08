"""Reports endpoints for PDF and Excel exports."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
import io

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.services.report_service import report_service

router = APIRouter()


@router.get("/performance/pdf")
async def get_performance_report_pdf(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate and download a PDF performance report."""
    data = await report_service.get_portfolio_data(db, str(current_user.id))
    pdf_content = report_service.generate_performance_pdf(data)

    filename = f"rapport_performance_{datetime.now().strftime('%Y%m%d')}.pdf"

    return StreamingResponse(
        io.BytesIO(pdf_content),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/performance/excel")
async def get_performance_report_excel(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate and download an Excel performance report."""
    data = await report_service.get_portfolio_data(db, str(current_user.id))
    excel_content = report_service.generate_performance_excel(data)

    filename = f"rapport_performance_{datetime.now().strftime('%Y%m%d')}.xlsx"

    return StreamingResponse(
        io.BytesIO(excel_content),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/tax/{year}/pdf")
async def get_tax_report_pdf(
    year: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate and download a PDF tax report (2086) for crypto assets."""
    if year < 2015 or year > datetime.now().year:
        year = datetime.now().year - 1

    pdf_content = await report_service.generate_tax_report_2086(
        db, str(current_user.id), year
    )

    filename = f"declaration_fiscale_crypto_{year}.pdf"

    return StreamingResponse(
        io.BytesIO(pdf_content),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/tax/{year}/excel")
async def get_tax_report_excel(
    year: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate and download an Excel tax report for crypto assets."""
    if year < 2015 or year > datetime.now().year:
        year = datetime.now().year - 1

    excel_content = await report_service.generate_tax_excel(
        db, str(current_user.id), year
    )

    filename = f"declaration_fiscale_crypto_{year}.xlsx"

    return StreamingResponse(
        io.BytesIO(excel_content),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/transactions/pdf")
async def get_transactions_report_pdf(
    year: Optional[int] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate and download a PDF transactions report."""
    data = await report_service.get_portfolio_data(db, str(current_user.id), year)
    pdf_content = report_service.generate_performance_pdf(data)

    year_str = str(year) if year else "all"
    filename = f"rapport_transactions_{year_str}_{datetime.now().strftime('%Y%m%d')}.pdf"

    return StreamingResponse(
        io.BytesIO(pdf_content),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/available-years")
async def get_available_years(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get list of years with transactions for reporting."""
    from sqlalchemy import select, extract, distinct
    from app.models.transaction import Transaction
    from app.models.asset import Asset
    from app.models.portfolio import Portfolio

    portfolio_result = await db.execute(
        select(Portfolio.id).where(
            Portfolio.user_id == current_user.id,
        )
    )
    portfolio_ids = list(portfolio_result.scalars().all())

    if not portfolio_ids:
        return {"years": [datetime.now().year]}

    asset_result = await db.execute(
        select(Asset.id).where(
            Asset.portfolio_id.in_(portfolio_ids),
        )
    )
    asset_ids = list(asset_result.scalars().all())

    if not asset_ids:
        return {"years": [datetime.now().year]}

    years_result = await db.execute(
        select(distinct(extract('year', Transaction.executed_at)))
        .where(Transaction.asset_id.in_(asset_ids))
        .order_by(extract('year', Transaction.executed_at).desc())
    )
    years = [int(y) for y in years_result.scalars().all() if y]

    if not years:
        years = [datetime.now().year]

    return {"years": years}
