"""Transaction endpoints."""

import csv
import io
import logging
from typing import List, Optional
from uuid import UUID

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.rate_limit import limiter
from app.models.asset import Asset
from app.models.portfolio import Portfolio
from app.models.transaction import Transaction, TransactionType
from app.models.user import User
from app.schemas.transaction import TransactionCreate, TransactionResponse, TransactionUpdate, TransactionWithAsset
from app.services.metrics_service import invalidate_dashboard_cache

router = APIRouter()


async def _recalculate_avg_buy_price(db: AsyncSession, asset: Asset):
    """Recalculate avg_buy_price from BUY and CONVERSION_IN transactions for an asset."""
    from sqlalchemy import func as sqlfunc

    result = await db.execute(
        select(
            sqlfunc.sum(Transaction.quantity * Transaction.price),
            sqlfunc.sum(Transaction.quantity),
        ).where(
            Transaction.asset_id == asset.id,
            Transaction.transaction_type.in_([TransactionType.BUY, TransactionType.CONVERSION_IN]),
            Transaction.price > 0,
        )
    )
    row = result.one()
    if row[1] and float(row[1]) > 0:
        asset.avg_buy_price = float(row[0]) / float(row[1])
    else:
        asset.avg_buy_price = 0


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


@router.get("", response_model=List[TransactionWithAsset])
async def list_transactions(
    asset_id: Optional[UUID] = None,
    portfolio_id: Optional[UUID] = None,
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> List[TransactionWithAsset]:
    """List transactions for the current user with asset details."""
    # Get user's portfolio IDs
    portfolio_result = await db.execute(select(Portfolio.id).where(Portfolio.user_id == current_user.id))
    portfolio_ids = [p for p in portfolio_result.scalars().all()]

    if not portfolio_ids:
        return []

    # Get user's assets (full objects for later mapping)
    asset_query = select(Asset).where(Asset.portfolio_id.in_(portfolio_ids))

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

    result = await db.execute(query.order_by(Transaction.executed_at.desc()).offset(skip).limit(limit))
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
                exchange=trans.exchange or (asset.exchange if asset else None),
                external_id=trans.external_id,
                created_at=trans.created_at,
                asset_symbol=asset.symbol if asset else "N/A",
                asset_name=asset.name if asset else None,
                asset_type=asset.asset_type.value if asset else "unknown",
            )
        )

    return enriched_transactions


@router.post("", response_model=TransactionResponse, status_code=status.HTTP_201_CREATED)
async def create_transaction(
    transaction_in: TransactionCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TransactionResponse:
    """Create a new transaction."""
    # Verify asset belongs to user
    portfolio_result = await db.execute(select(Portfolio.id).where(Portfolio.user_id == current_user.id))
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
    transaction.compute_hash()

    db.add(transaction)

    # Update asset quantity for buy/sell
    add_types = ["buy", "conversion_in", "transfer_in", "airdrop", "staking_reward", "dividend", "interest"]
    subtract_types = ["sell", "transfer_out", "conversion_out", "fee"]

    if transaction_in.transaction_type.value in add_types:
        new_total = float(asset.quantity) + quantity
        asset.quantity = min(new_total, MAX_NUMERIC_VALUE)
    elif transaction_in.transaction_type.value in subtract_types:
        new_total = float(asset.quantity) - quantity
        # Allow historical sells even when quantity was already synced to 0
        # (e.g. exchange sync updated balance before the transaction was recorded).
        # Clamp to 0 to avoid negative quantities.
        asset.quantity = max(0, new_total)

    # Recalculate avg_buy_price from all BUY + CONVERSION_IN transactions
    # (avoids the incremental formula bug that dilutes PRU with airdrop quantities)
    await db.flush()
    await _recalculate_avg_buy_price(db, asset)

    await db.commit()
    await db.refresh(transaction)

    invalidate_dashboard_cache(str(current_user.id))

    return transaction


@router.get("/csv-platforms")
async def get_csv_platforms():
    """Get list of supported CSV platforms for import."""
    from app.services.csv_parsers import get_available_platforms

    return {"platforms": get_available_platforms()}


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
    portfolio_query = select(Portfolio).where(Portfolio.user_id == current_user.id)
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
    asset_result = await db.execute(select(Asset).where(Asset.portfolio_id.in_(portfolio_ids)))
    assets = asset_result.scalars().all()
    asset_map = {a.id: a for a in assets}
    asset_ids = [a.id for a in assets]

    # Get transactions
    result = await db.execute(
        select(Transaction).where(Transaction.asset_id.in_(asset_ids)).order_by(Transaction.executed_at.desc())
    )
    transactions = result.scalars().all()

    # Generate CSV
    output = io.StringIO()
    writer = csv.writer(output, delimiter=";")
    writer.writerow(["symbol", "type", "quantity", "price", "fee", "date", "exchange", "notes"])

    for trans in transactions:
        asset = asset_map.get(trans.asset_id)
        symbol = asset.symbol if asset else "UNKNOWN"
        exchange = trans.exchange or (asset.exchange if asset else "") or ""
        writer.writerow(
            [
                symbol,
                trans.transaction_type.value,
                str(trans.quantity),
                str(trans.price),
                str(trans.fee),
                trans.executed_at.strftime("%Y-%m-%d %H:%M:%S"),
                exchange,
                trans.notes or "",
            ]
        )

    output.seek(0)

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=transactions_export.csv"},
    )


@router.get("/{transaction_id}", response_model=TransactionResponse)
async def get_transaction(
    transaction_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TransactionResponse:
    """Get a specific transaction."""
    # Get user's asset IDs
    portfolio_result = await db.execute(select(Portfolio.id).where(Portfolio.user_id == current_user.id))
    portfolio_ids = [p for p in portfolio_result.scalars().all()]

    asset_result = await db.execute(select(Asset.id).where(Asset.portfolio_id.in_(portfolio_ids)))
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
    portfolio_result = await db.execute(select(Portfolio.id).where(Portfolio.user_id == current_user.id))
    portfolio_ids = [p for p in portfolio_result.scalars().all()]

    asset_result = await db.execute(select(Asset.id).where(Asset.portfolio_id.in_(portfolio_ids)))
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

    update_data = transaction_update.model_dump(exclude_unset=True)

    # If quantity or transaction_type changed, revert old effect and apply new
    quantity_changed = "quantity" in update_data
    type_changed = "transaction_type" in update_data
    if quantity_changed or type_changed:
        asset_result2 = await db.execute(select(Asset).where(Asset.id == transaction.asset_id))
        asset = asset_result2.scalar_one()

        add_types = ["buy", "transfer_in", "airdrop", "staking_reward", "dividend", "interest", "conversion_in"]
        subtract_types = ["sell", "transfer_out", "conversion_out", "fee"]

        old_type = transaction.transaction_type.value
        old_qty = float(transaction.quantity)

        # Revert old effect
        if old_type in add_types:
            asset.quantity = float(asset.quantity) - old_qty
        elif old_type in subtract_types:
            asset.quantity = float(asset.quantity) + old_qty

        # Apply new effect
        new_type = update_data.get("transaction_type", transaction.transaction_type)
        new_type_val = new_type.value if hasattr(new_type, "value") else new_type
        new_qty = float(update_data.get("quantity", transaction.quantity))

        if new_type_val in add_types:
            asset.quantity = float(asset.quantity) + new_qty
        elif new_type_val in subtract_types:
            asset.quantity = float(asset.quantity) - new_qty

        if asset.quantity < 0:
            logger.warning(f"Asset {asset.symbol} quantity went negative ({asset.quantity}), clamping to 0")
            asset.quantity = 0

    # Update fields
    for field, value in update_data.items():
        setattr(transaction, field, value)

    # Recalculate avg_buy_price if quantity or price changed
    if quantity_changed or type_changed or "price" in update_data:
        await db.flush()  # Persist transaction changes before recalculating
        asset_for_avg = asset if (quantity_changed or type_changed) else None
        if not asset_for_avg:
            asset_res = await db.execute(select(Asset).where(Asset.id == transaction.asset_id))
            asset_for_avg = asset_res.scalar_one()
        await _recalculate_avg_buy_price(db, asset_for_avg)

    await db.commit()
    await db.refresh(transaction)

    invalidate_dashboard_cache(str(current_user.id))

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
    portfolio_result = await db.execute(select(Portfolio.id).where(Portfolio.user_id == current_user.id))
    portfolio_ids = [p for p in portfolio_result.scalars().all()]

    if not portfolio_ids:
        return DeleteAllResult(deleted_count=0)

    # Get user's assets
    asset_result = await db.execute(select(Asset).where(Asset.portfolio_id.in_(portfolio_ids)))
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

    invalidate_dashboard_cache(str(current_user.id))

    return DeleteAllResult(deleted_count=deleted_count)


@router.delete("/{transaction_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_transaction(
    transaction_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a transaction (and revert asset quantity)."""
    # Get user's asset IDs
    portfolio_result = await db.execute(select(Portfolio.id).where(Portfolio.user_id == current_user.id))
    portfolio_ids = [p for p in portfolio_result.scalars().all()]

    asset_result = await db.execute(select(Asset.id).where(Asset.portfolio_id.in_(portfolio_ids)))
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
        asset.quantity = max(0, float(asset.quantity) - float(transaction.quantity))
    elif transaction.transaction_type.value in subtract_types:
        asset.quantity = float(asset.quantity) + float(transaction.quantity)

    await db.delete(transaction)
    await db.flush()

    # Recalculate avg_buy_price from remaining BUY transactions
    await _recalculate_avg_buy_price(db, asset)

    await db.commit()

    invalidate_dashboard_cache(str(current_user.id))


@router.post("/import-csv", response_model=CSVImportResult)
@limiter.limit("10/minute")
async def import_transactions_csv(
    request: Request,
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
    from app.models.asset import AssetType
    from app.services.csv_parsers import detect_csv_format, get_parser_by_name

    logger.info(f"CSV Import: portfolio_id={portfolio_id}, platform={platform}, filename={file.filename}")

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

    # Get existing assets — keyed by (symbol, exchange) for multi-platform support
    asset_result = await db.execute(
        select(Asset).where(
            Asset.portfolio_id == portfolio.id,
        )
    )
    assets = asset_result.scalars().all()
    # Key: (symbol, exchange) for multi-platform, fallback by symbol for backward compat
    asset_map_by_platform = {(a.symbol.upper(), a.exchange or ""): a for a in assets}
    asset_map_by_symbol = {a.symbol.upper(): a for a in assets}

    # Read CSV content
    try:
        content = await file.read()
        content_str = content.decode("utf-8-sig")  # Handle BOM
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to read the uploaded file. Please check the file format.",
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

        logger.info(f"Using parser: {parser.name}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error detecting parser: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Error detecting CSV format. Please specify the platform.",
        )

    # Parse CSV
    try:
        parsed_transactions, parse_errors = parser.parse_csv(content_str)
        logger.info(f"Parsed {len(parsed_transactions)} transactions, {len(parse_errors)} parse errors")
    except Exception as e:
        logger.error(f"Error parsing CSV: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Error parsing CSV file. Please check the file format and content.",
        )

    success_count = 0
    skipped = 0
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
        "fee": TransactionType.FEE,
        "dividend": TransactionType.DIVIDEND,
        "interest": TransactionType.INTEREST,
    }

    # Sort transactions by timestamp to ensure correct quantity calculations
    parsed_transactions.sort(key=lambda x: x.timestamp)

    # Build set of existing transactions for deduplication
    # Match by (symbol, type, quantity, timestamp) to avoid reimporting duplicates
    existing_tx_keys = set()
    all_asset_ids_for_dedup = list(asset_map_by_platform.values()) + list(asset_map_by_symbol.values())
    dedup_asset_ids = list({a.id for a in all_asset_ids_for_dedup})
    if dedup_asset_ids:
        existing_tx_result = await db.execute(
            select(
                Transaction.quantity,
                Transaction.transaction_type,
                Transaction.executed_at,
                Asset.symbol,
                Transaction.price,
            )
            .join(Asset, Transaction.asset_id == Asset.id)
            .where(Transaction.asset_id.in_(dedup_asset_ids))
        )
        for row in existing_tx_result.all():
            qty, tx_type, exec_at, sym, price = row
            if exec_at:
                ts_key = int(exec_at.timestamp())  # Second precision
                existing_tx_keys.add((sym.upper(), tx_type.value, f"{float(qty):.8f}", f"{float(price):.8f}", ts_key))

    for parsed in parsed_transactions:
        try:
            symbol = parsed.symbol.upper()

            # Skip fiat currencies
            if symbol in ["EUR", "USD", "GBP", "CAD", "JPY", "CHF", "AUD"]:
                continue

            # Get or create asset — prefer exact (symbol, exchange) match
            csv_exchange = parser.name
            platform_key = (symbol, csv_exchange)
            asset = asset_map_by_platform.get(platform_key)
            if not asset:
                # Fallback: check if asset exists with no exchange assigned
                empty_key = (symbol, "")
                asset = asset_map_by_platform.get(empty_key)
                if asset:
                    # Assign exchange to the unassigned asset
                    asset.exchange = csv_exchange
                    asset_map_by_platform[platform_key] = asset
                    del asset_map_by_platform[empty_key]
            if not asset:
                # Fallback: check by symbol alone (avoid creating duplicates
                # when the same symbol exists on a different exchange)
                asset = asset_map_by_symbol.get(symbol)
                if asset:
                    # Use existing asset — don't change its exchange
                    asset_map_by_platform[platform_key] = asset
            if not asset:
                # Create new asset for this platform
                asset = Asset(
                    portfolio_id=portfolio.id,
                    symbol=symbol,
                    name=symbol,
                    asset_type=AssetType.CRYPTO,
                    quantity=0,
                    avg_buy_price=0,
                    currency=parsed.currency or "EUR",
                    exchange=csv_exchange,
                )
                db.add(asset)
                await db.flush()
                asset_map_by_platform[platform_key] = asset
                assets_created += 1
            asset_map_by_symbol[symbol] = asset

            # Get transaction type
            trans_type = type_mapping.get(parsed.transaction_type)
            if not trans_type:
                errors.append(f"Unknown transaction type: {parsed.transaction_type}")
                error_count += 1
                continue

            # Deduplication: skip if a matching transaction already exists
            ts_key = int(parsed.timestamp.timestamp())  # Second precision
            dedup_key = (
                symbol,
                trans_type.value,
                f"{float(parsed.quantity):.8f}",
                f"{float(parsed.price):.8f}",
                ts_key,
            )
            if dedup_key in existing_tx_keys:
                continue  # Skip duplicate
            existing_tx_keys.add(dedup_key)  # Prevent duplicates within same import

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
            transaction.compute_hash()
            # Skip if duplicate hash already exists
            from sqlalchemy import select as _sel

            _dup = await db.execute(_sel(Transaction.id).where(Transaction.internal_hash == transaction.internal_hash))
            if _dup.scalar_one_or_none() is not None:
                skipped += 1
                continue
            db.add(transaction)

            # Update asset quantity (avg_buy_price recalculated in batch after commit)
            csv_add_types = ["buy", "transfer_in", "airdrop", "staking_reward", "conversion_in", "dividend", "interest"]
            csv_subtract_types = ["sell", "transfer_out", "conversion_out", "fee"]
            if trans_type.value in csv_add_types:
                new_total = float(asset.quantity) + quantity
                asset.quantity = min(new_total, MAX_NUMERIC_VALUE)
            elif trans_type.value in csv_subtract_types:
                new_quantity = float(asset.quantity) - quantity
                asset.quantity = max(0, new_quantity)  # Prevent negative quantities

            await db.flush()
            created_transactions.append(transaction.id)
            success_count += 1

        except Exception as e:
            errors.append(f"Error processing {parsed.symbol}: {str(e)}")
            error_count += 1
            logger.error(f"Error processing {parsed.symbol}: {e}")

    try:
        await db.commit()
        logger.info(f"Successfully committed {success_count} transactions")
    except Exception as e:
        logger.error(f"Database commit error: {e}")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="A database error occurred. Please try again.",
        )

    # Recalculate asset quantities from transactions (incremental updates lose precision)
    if success_count > 0:
        try:
            from sqlalchemy import case, func

            add_types = [
                TransactionType.BUY,
                TransactionType.TRANSFER_IN,
                TransactionType.AIRDROP,
                TransactionType.STAKING_REWARD,
                TransactionType.CONVERSION_IN,
                TransactionType.DIVIDEND,
                TransactionType.INTEREST,
            ]
            # TRANSFER_OUT is NOT subtracted: you still own the asset (it moved to cold wallet)
            sell_types = [
                TransactionType.SELL,
                TransactionType.CONVERSION_OUT,
            ]

            for (symbol, _exchange), asset in asset_map_by_platform.items():
                # Calculate owned quantity (all in - sells/conversions, NOT transfer_out)
                qty_result = await db.execute(
                    select(
                        func.coalesce(
                            func.sum(
                                case(
                                    (Transaction.transaction_type.in_(add_types), Transaction.quantity),
                                    (Transaction.transaction_type.in_(sell_types), -Transaction.quantity),
                                    else_=0,
                                )
                            ),
                            0,
                        )
                    ).where(Transaction.asset_id == asset.id)
                )
                owned_qty = max(0, float(qty_result.scalar()))

                # Check if asset has been transferred out (to cold wallet)
                transfer_out_result = await db.execute(
                    select(func.coalesce(func.sum(Transaction.quantity), 0)).where(
                        Transaction.asset_id == asset.id,
                        Transaction.transaction_type == TransactionType.TRANSFER_OUT,
                    )
                )
                transferred_qty = float(transfer_out_result.scalar())

                if transferred_qty > 0.0001:
                    # Asset was transferred — deduct withdrawal fees in crypto
                    transfer_fees_result = await db.execute(
                        select(func.coalesce(func.sum(Transaction.fee), 0)).where(
                            Transaction.asset_id == asset.id,
                            Transaction.transaction_type == TransactionType.TRANSFER_OUT,
                            Transaction.fee_currency == symbol,
                        )
                    )
                    transfer_fees = float(transfer_fees_result.scalar())
                    asset.quantity = max(0, owned_qty - transfer_fees)
                else:
                    asset.quantity = owned_qty

                # Recalculate avg_buy_price from buy transactions
                avg_result = await db.execute(
                    select(
                        func.sum(Transaction.quantity * Transaction.price),
                        func.sum(Transaction.quantity),
                    ).where(
                        Transaction.asset_id == asset.id,
                        Transaction.transaction_type.in_([TransactionType.BUY, TransactionType.CONVERSION_IN]),
                        Transaction.price > 0,
                    )
                )
                row = avg_result.one()
                if row[1] and float(row[1]) > 0:
                    asset.avg_buy_price = float(row[0]) / float(row[1])

            await db.commit()
            logger.info("Recalculated asset quantities from transactions")
        except Exception as e:
            logger.warning(f"Failed to recalculate quantities: {e}")

    if success_count > 0:
        invalidate_dashboard_cache(str(current_user.id))

    # Trigger historical price cache for imported assets (background Celery tasks)
    if success_count > 0:
        try:
            from app.tasks.history_cache import cache_single_asset

            for (symbol, _exchange), asset in asset_map_by_platform.items():
                asset_type_value = (
                    asset.asset_type.value if hasattr(asset.asset_type, "value") else str(asset.asset_type)
                )
                cache_single_asset.delay(symbol, asset_type_value)
            logger.info(f"Triggered history cache for {len(asset_map_by_platform)} assets")
        except Exception as e:
            # Non-critical: don't fail import if cache trigger fails
            logger.warning(f"Failed to trigger history cache: {e}")

    return CSVImportResult(
        success_count=success_count,
        error_count=error_count,
        errors=errors[:50],
        created_transactions=created_transactions,
    )
