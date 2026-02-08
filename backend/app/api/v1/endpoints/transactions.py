"""Transaction endpoints."""

import csv
import io
from decimal import Decimal, InvalidOperation
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.asset import Asset
from app.models.portfolio import Portfolio
from app.models.transaction import Transaction, TransactionType
from app.models.user import User
from app.schemas.transaction import TransactionCreate, TransactionResponse, TransactionUpdate, TransactionWithAsset

router = APIRouter()


class CSVImportResult(BaseModel):
    """Result of CSV import operation."""

    success_count: int
    error_count: int
    errors: List[str]
    created_transactions: List[UUID]


class CSVRowError(BaseModel):
    """Error details for a CSV row."""

    row: int
    message: str


@router.get("/", response_model=List[TransactionWithAsset])
async def list_transactions(
    asset_id: Optional[UUID] = None,
    portfolio_id: Optional[UUID] = None,
    skip: int = 0,
    limit: int = 10000,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> List[TransactionWithAsset]:
    """List transactions for the current user with asset details."""
    # Get user's portfolio IDs
    portfolio_result = await db.execute(
        select(Portfolio.id).where(
            Portfolio.user_id == current_user.id
        )
    )
    portfolio_ids = [p for p in portfolio_result.scalars().all()]

    if not portfolio_ids:
        return []

    # Get user's assets (full objects for later mapping)
    asset_query = select(Asset).where(
        Asset.portfolio_id.in_(portfolio_ids)
    )

    if portfolio_id:
        if portfolio_id not in portfolio_ids:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Portfolio not found",
            )
        asset_query = asset_query.where(Asset.portfolio_id == portfolio_id)

    asset_result = await db.execute(asset_query)
    assets = asset_result.scalars().all()
    asset_map = {a.id: a for a in assets}
    asset_ids = list(asset_map.keys())

    if not asset_ids:
        return []

    # Build transaction query
    query = select(Transaction).where(
        Transaction.asset_id.in_(asset_ids),
    )

    if asset_id:
        if asset_id not in asset_ids:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Asset not found",
            )
        query = query.where(Transaction.asset_id == asset_id)

    result = await db.execute(
        query.order_by(Transaction.executed_at.desc()).offset(skip).limit(limit)
    )
    transactions = result.scalars().all()

    # Enrich transactions with asset info
    enriched_transactions = []
    for trans in transactions:
        asset = asset_map.get(trans.asset_id)
        enriched_transactions.append(
            TransactionWithAsset(
                id=trans.id,
                asset_id=trans.asset_id,
                transaction_type=trans.transaction_type,
                quantity=trans.quantity,
                price=trans.price,
                fee=trans.fee,
                currency=trans.currency,
                executed_at=trans.executed_at,
                notes=trans.notes,
                exchange=trans.exchange,
                external_id=trans.external_id,
                created_at=trans.created_at,
                asset_symbol=asset.symbol if asset else "N/A",
                asset_name=asset.name if asset else None,
                asset_type=asset.asset_type.value if asset else "unknown",
            )
        )

    return enriched_transactions


@router.post(
    "/", response_model=TransactionResponse, status_code=status.HTTP_201_CREATED
)
async def create_transaction(
    transaction_in: TransactionCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TransactionResponse:
    """Create a new transaction."""
    # Verify asset belongs to user
    portfolio_result = await db.execute(
        select(Portfolio.id).where(
            Portfolio.user_id == current_user.id
        )
    )
    portfolio_ids = [p for p in portfolio_result.scalars().all()]

    asset_result = await db.execute(
        select(Asset).where(
            Asset.id == transaction_in.asset_id,
            Asset.portfolio_id.in_(portfolio_ids),
        )
    )
    asset = asset_result.scalar_one_or_none()

    if not asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Asset not found",
        )

    # Sanitize values to prevent numeric overflow
    # NUMERIC(18, 8) max value is 10^10 - 1 = 9,999,999,999.99999999
    MAX_NUMERIC_VALUE = 9_999_999_999.0

    quantity = float(transaction_in.quantity)
    price = float(transaction_in.price)
    fee = float(transaction_in.fee) if transaction_in.fee else 0

    # Clamp values to valid ranges
    quantity = max(0, min(quantity, MAX_NUMERIC_VALUE))
    price = max(0, min(price, MAX_NUMERIC_VALUE))
    fee = max(0, min(fee, MAX_NUMERIC_VALUE))

    transaction = Transaction(
        asset_id=transaction_in.asset_id,
        transaction_type=transaction_in.transaction_type,
        quantity=quantity,
        price=price,
        fee=fee,
        currency=transaction_in.currency,
        executed_at=transaction_in.executed_at,
        exchange=transaction_in.exchange,
        external_id=transaction_in.external_id,
        notes=transaction_in.notes,
    )

    db.add(transaction)

    # Update asset quantity and average price for buy/sell
    if transaction_in.transaction_type.value in ["buy", "transfer_in", "airdrop"]:
        new_total = float(asset.quantity) + quantity
        if new_total > 0 and price > 0:
            new_avg_price = (
                float(asset.quantity) * float(asset.avg_buy_price)
                + quantity * price
            ) / new_total
            # Clamp avg_buy_price to valid range
            new_avg_price = max(0, min(new_avg_price, MAX_NUMERIC_VALUE))
            asset.avg_buy_price = new_avg_price
        asset.quantity = min(new_total, MAX_NUMERIC_VALUE)
    elif transaction_in.transaction_type.value in ["sell", "transfer_out"]:
        new_total = float(asset.quantity) - quantity
        if new_total < 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Insufficient quantity",
            )
        asset.quantity = new_total

    await db.commit()
    await db.refresh(transaction)

    return transaction


@router.get("/csv-platforms")
async def get_csv_platforms():
    """Get list of supported CSV platforms for import."""
    from app.services.csv_parsers import get_available_platforms
    return {"platforms": get_available_platforms()}


@router.get("/{transaction_id}", response_model=TransactionResponse)
async def get_transaction(
    transaction_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TransactionResponse:
    """Get a specific transaction."""
    # Get user's asset IDs
    portfolio_result = await db.execute(
        select(Portfolio.id).where(
            Portfolio.user_id == current_user.id
        )
    )
    portfolio_ids = [p for p in portfolio_result.scalars().all()]

    asset_result = await db.execute(
        select(Asset.id).where(
            Asset.portfolio_id.in_(portfolio_ids)
        )
    )
    asset_ids = [a for a in asset_result.scalars().all()]

    result = await db.execute(
        select(Transaction).where(
            Transaction.id == transaction_id,
            Transaction.asset_id.in_(asset_ids),
        )
    )
    transaction = result.scalar_one_or_none()

    if not transaction:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transaction not found",
        )

    return transaction


@router.patch("/{transaction_id}", response_model=TransactionResponse)
async def update_transaction(
    transaction_id: UUID,
    transaction_update: TransactionUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TransactionResponse:
    """Update a transaction (quantity, price, fee, notes, executed_at)."""
    # Get user's asset IDs
    portfolio_result = await db.execute(
        select(Portfolio.id).where(
            Portfolio.user_id == current_user.id
        )
    )
    portfolio_ids = [p for p in portfolio_result.scalars().all()]

    asset_result = await db.execute(
        select(Asset.id).where(
            Asset.portfolio_id.in_(portfolio_ids)
        )
    )
    asset_ids = [a for a in asset_result.scalars().all()]

    result = await db.execute(
        select(Transaction).where(
            Transaction.id == transaction_id,
            Transaction.asset_id.in_(asset_ids),
        )
    )
    transaction = result.scalar_one_or_none()

    if not transaction:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transaction not found",
        )

    # Update fields if provided
    update_data = transaction_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(transaction, field, value)

    await db.commit()
    await db.refresh(transaction)

    return transaction


class DeleteAllResult(BaseModel):
    """Result of delete all operation."""
    deleted_count: int


@router.delete("/all", response_model=DeleteAllResult)
async def delete_all_transactions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DeleteAllResult:
    """Delete all transactions for the current user and reset asset quantities."""
    # Get user's portfolio IDs
    portfolio_result = await db.execute(
        select(Portfolio.id).where(
            Portfolio.user_id == current_user.id
        )
    )
    portfolio_ids = [p for p in portfolio_result.scalars().all()]

    if not portfolio_ids:
        return DeleteAllResult(deleted_count=0)

    # Get user's assets
    asset_result = await db.execute(
        select(Asset).where(
            Asset.portfolio_id.in_(portfolio_ids)
        )
    )
    assets = asset_result.scalars().all()
    asset_ids = [a.id for a in assets]

    if not asset_ids:
        return DeleteAllResult(deleted_count=0)

    # Count and delete all transactions
    count_result = await db.execute(
        select(Transaction).where(
            Transaction.asset_id.in_(asset_ids),
        )
    )
    transactions = count_result.scalars().all()
    deleted_count = len(transactions)

    # Hard delete all transactions
    for transaction in transactions:
        await db.delete(transaction)

    # Reset all asset quantities and avg prices
    for asset in assets:
        asset.quantity = 0
        asset.avg_buy_price = 0

    await db.commit()

    return DeleteAllResult(deleted_count=deleted_count)


@router.delete("/{transaction_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_transaction(
    transaction_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a transaction (and revert asset quantity)."""
    # Get user's asset IDs
    portfolio_result = await db.execute(
        select(Portfolio.id).where(
            Portfolio.user_id == current_user.id
        )
    )
    portfolio_ids = [p for p in portfolio_result.scalars().all()]

    asset_result = await db.execute(
        select(Asset.id).where(
            Asset.portfolio_id.in_(portfolio_ids)
        )
    )
    asset_ids = [a for a in asset_result.scalars().all()]

    result = await db.execute(
        select(Transaction).where(
            Transaction.id == transaction_id,
            Transaction.asset_id.in_(asset_ids),
        )
    )
    transaction = result.scalar_one_or_none()

    if not transaction:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transaction not found",
        )

    # Revert asset quantity
    asset_result = await db.execute(select(Asset).where(Asset.id == transaction.asset_id))
    asset = asset_result.scalar_one()

    # Types that ADD to quantity (revert = subtract)
    add_types = ["buy", "transfer_in", "airdrop", "staking_reward", "dividend", "interest", "conversion_in"]
    # Types that SUBTRACT from quantity (revert = add back)
    subtract_types = ["sell", "transfer_out", "conversion_out", "fee"]

    if transaction.transaction_type.value in add_types:
        asset.quantity = float(asset.quantity) - float(transaction.quantity)
    elif transaction.transaction_type.value in subtract_types:
        asset.quantity = float(asset.quantity) + float(transaction.quantity)

    await db.delete(transaction)
    await db.commit()


@router.post("/import-csv", response_model=CSVImportResult)
async def import_transactions_csv(
    file: UploadFile = File(...),
    portfolio_id: Optional[UUID] = Query(None),
    platform: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CSVImportResult:
    """
    Import transactions from a CSV file.

    Supports multiple platforms:
    - Crypto.com: Export from app
    - Binance: Transaction history export
    - Kraken: Ledger export
    - Generic: InvestAI format (symbol, type, quantity, price, fee, date, notes)

    Platform is auto-detected if not specified.
    Assets are created automatically if they don't exist.
    """
    from app.services.csv_parsers import detect_csv_format, get_parser_by_name
    from app.models.asset import AssetType

    print(f"CSV Import: portfolio_id={portfolio_id}, platform={platform}, filename={file.filename}")

    if not file.filename.endswith(".csv"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be a CSV file",
        )

    # Get or create portfolio
    if portfolio_id:
        portfolio_result = await db.execute(
            select(Portfolio).where(
                Portfolio.id == portfolio_id,
                Portfolio.user_id == current_user.id,
            )
        )
        portfolio = portfolio_result.scalar_one_or_none()
        if not portfolio:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Portfolio not found",
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Portfolio ID is required",
        )

    # Get existing assets
    asset_result = await db.execute(
        select(Asset).where(
            Asset.portfolio_id == portfolio.id,
        )
    )
    assets = asset_result.scalars().all()
    asset_map = {a.symbol.upper(): a for a in assets}

    # Read CSV content
    try:
        content = await file.read()
        content_str = content.decode("utf-8-sig")  # Handle BOM
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to read file: {str(e)}",
        )

    # Get or detect parser
    try:
        if platform:
            parser = get_parser_by_name(platform)
            if not parser:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Unknown platform: {platform}",
                )
        else:
            parser = detect_csv_format(content_str)
            if not parser:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Could not detect CSV format. Please specify the platform.",
                )

        print(f"Using parser: {parser.name}")
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error detecting parser: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error detecting CSV format: {str(e)}",
        )

    # Parse CSV
    try:
        parsed_transactions, parse_errors = parser.parse_csv(content_str)
        print(f"Parsed {len(parsed_transactions)} transactions, {len(parse_errors)} parse errors")
    except Exception as e:
        print(f"Error parsing CSV: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error parsing CSV file: {str(e)}",
        )

    success_count = 0
    error_count = len(parse_errors)
    errors = parse_errors.copy()
    created_transactions = []
    assets_created = 0

    # Transaction type mapping
    type_mapping = {
        "buy": TransactionType.BUY,
        "sell": TransactionType.SELL,
        "transfer_in": TransactionType.TRANSFER_IN,
        "transfer_out": TransactionType.TRANSFER_OUT,
        "staking_reward": TransactionType.STAKING_REWARD,
        "airdrop": TransactionType.AIRDROP,
        "conversion_in": TransactionType.CONVERSION_IN,
        "conversion_out": TransactionType.CONVERSION_OUT,
    }

    # Sort transactions by timestamp to ensure correct quantity calculations
    parsed_transactions.sort(key=lambda x: x.timestamp)

    for parsed in parsed_transactions:
        try:
            symbol = parsed.symbol.upper()

            # Skip fiat currencies
            if symbol in ["EUR", "USD", "GBP", "CAD", "JPY", "CHF", "AUD"]:
                continue

            # Get or create asset
            asset = asset_map.get(symbol)
            if not asset:
                # Create new asset
                asset = Asset(
                    portfolio_id=portfolio.id,
                    symbol=symbol,
                    name=symbol,
                    asset_type=AssetType.CRYPTO,
                    quantity=0,
                    avg_buy_price=0,
                    currency=parsed.currency or "EUR",
                )
                db.add(asset)
                await db.flush()
                asset_map[symbol] = asset
                assets_created += 1

            # Get transaction type
            trans_type = type_mapping.get(parsed.transaction_type)
            if not trans_type:
                errors.append(f"Unknown transaction type: {parsed.transaction_type}")
                error_count += 1
                continue

            # Sanitize values to prevent numeric overflow
            # NUMERIC(18, 8) max value is 10^10 - 1 = 9,999,999,999.99999999
            MAX_NUMERIC_VALUE = 9_999_999_999.0
            MIN_QUANTITY = 1e-8  # Minimum meaningful quantity

            quantity = float(parsed.quantity)
            price = float(parsed.price)
            fee = float(parsed.fee)

            # Clamp values to valid ranges
            quantity = max(0, min(quantity, MAX_NUMERIC_VALUE))
            price = max(0, min(price, MAX_NUMERIC_VALUE))
            fee = max(0, min(fee, MAX_NUMERIC_VALUE))

            # Skip transactions with negligible quantities
            if quantity < MIN_QUANTITY:
                continue

            # Create transaction
            transaction = Transaction(
                asset_id=asset.id,
                transaction_type=trans_type,
                quantity=quantity,
                price=price,
                fee=fee,
                currency=parsed.currency or "EUR",
                executed_at=parsed.timestamp,
                notes=parsed.notes,
                exchange=parser.name,
            )
            db.add(transaction)

            # Update asset quantity and avg price
            if trans_type.value in ["buy", "transfer_in", "airdrop", "staking_reward", "conversion_in"]:
                new_total = float(asset.quantity) + quantity
                if new_total > MIN_QUANTITY and price > 0:
                    new_avg_price = (
                        float(asset.quantity) * float(asset.avg_buy_price)
                        + quantity * price
                    ) / new_total
                    # Clamp avg_buy_price to valid range
                    new_avg_price = max(0, min(new_avg_price, MAX_NUMERIC_VALUE))
                    asset.avg_buy_price = new_avg_price
                asset.quantity = min(new_total, MAX_NUMERIC_VALUE)
            elif trans_type.value in ["sell", "transfer_out", "conversion_out"]:
                new_quantity = float(asset.quantity) - quantity
                asset.quantity = max(0, new_quantity)  # Prevent negative quantities

            await db.flush()
            created_transactions.append(transaction.id)
            success_count += 1

        except Exception as e:
            errors.append(f"Error processing {parsed.symbol}: {str(e)}")
            error_count += 1
            print(f"Error processing {parsed.symbol}: {e}")

    try:
        await db.commit()
        print(f"Successfully committed {success_count} transactions")
    except Exception as e:
        print(f"Database commit error: {e}")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error: {str(e)}",
        )

    return CSVImportResult(
        success_count=success_count,
        error_count=error_count,
        errors=errors[:50],
        created_transactions=created_transactions,
    )


@router.get("/export-csv")
async def export_transactions_csv(
    portfolio_id: Optional[UUID] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Export transactions to a CSV file.
    """
    from fastapi.responses import StreamingResponse

    # Get user's portfolio IDs
    portfolio_query = select(Portfolio).where(
        Portfolio.user_id == current_user.id
    )
    if portfolio_id:
        portfolio_query = portfolio_query.where(Portfolio.id == portfolio_id)

    portfolio_result = await db.execute(portfolio_query)
    portfolios = portfolio_result.scalars().all()
    portfolio_ids = [p.id for p in portfolios]

    if not portfolio_ids:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No portfolios found",
        )

    # Get user's assets with symbols
    asset_result = await db.execute(
        select(Asset).where(
            Asset.portfolio_id.in_(portfolio_ids)
        )
    )
    assets = asset_result.scalars().all()
    asset_map = {a.id: a for a in assets}
    asset_ids = [a.id for a in assets]

    # Get transactions
    result = await db.execute(
        select(Transaction)
        .where(Transaction.asset_id.in_(asset_ids))
        .order_by(Transaction.executed_at.desc())
    )
    transactions = result.scalars().all()

    # Generate CSV
    output = io.StringIO()
    writer = csv.writer(output, delimiter=";")
    writer.writerow(["symbol", "type", "quantity", "price", "fee", "date", "notes"])

    for trans in transactions:
        asset = asset_map.get(trans.asset_id)
        symbol = asset.symbol if asset else "UNKNOWN"
        writer.writerow([
            symbol,
            trans.transaction_type.value,
            str(trans.quantity),
            str(trans.price),
            str(trans.fee),
            trans.executed_at.strftime("%Y-%m-%d %H:%M:%S"),
            trans.notes or "",
        ])

    output.seek(0)

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=transactions_export.csv"},
    )
