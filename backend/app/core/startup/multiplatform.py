import logging

logger = logging.getLogger(__name__)


def fix_multiplatform_assets() -> None:
    try:
        import uuid

        from sqlalchemy import create_engine, text

        from app.core.config import settings

        sync_engine = create_engine(settings.DATABASE_URL_SYNC)
        with sync_engine.begin() as conn:
            rows = conn.execute(
                text(
                    "SELECT t.id AS tx_id, t.exchange AS tx_exchange, t.quantity, t.price,"
                    " t.transaction_type, a.id AS asset_id, a.portfolio_id, a.symbol,"
                    " a.name, a.asset_type, a.exchange AS asset_exchange, a.currency AS asset_currency"
                    " FROM transactions t JOIN assets a ON t.asset_id = a.id"
                    " WHERE t.exchange IS NOT NULL AND t.exchange != ''"
                    " AND LOWER(TRIM(t.exchange)) != LOWER(TRIM(a.exchange))"
                )
            ).fetchall()

            if not rows:
                logger.info("No multiplatform mismatches found")
                sync_engine.dispose()
                return

            logger.info("Found %d mismatched transactions to fix", len(rows))

            asset_cache = {}
            for r in rows:
                key = (str(r.portfolio_id), r.symbol, r.tx_exchange.strip())
                if key not in asset_cache:
                    existing = conn.execute(
                        text("SELECT id FROM assets WHERE portfolio_id = :pid AND symbol = :sym AND exchange = :exc"),
                        {
                            "pid": r.portfolio_id,
                            "sym": r.symbol,
                            "exc": r.tx_exchange.strip(),
                        },
                    ).fetchone()

                    if existing:
                        asset_cache[key] = str(existing.id)
                    else:
                        new_id = str(uuid.uuid4())
                        conn.execute(
                            text(
                                "INSERT INTO assets (id, portfolio_id, symbol, name, asset_type, quantity,"
                                " avg_buy_price, exchange, currency)"
                                " VALUES (:id, :pid, :sym, :name, :atype, 0, 0, :exc, :cur)"
                            ),
                            {
                                "id": new_id,
                                "pid": r.portfolio_id,
                                "sym": r.symbol,
                                "name": r.name,
                                "atype": r.asset_type,
                                "exc": r.tx_exchange.strip(),
                                "cur": r.asset_currency,
                            },
                        )
                        asset_cache[key] = new_id
                        logger.info(
                            "Created asset %s/%s (id=%s)",
                            r.symbol,
                            r.tx_exchange.strip(),
                            new_id,
                        )

            for r in rows:
                key = (str(r.portfolio_id), r.symbol, r.tx_exchange.strip())
                target_id = asset_cache[key]
                conn.execute(
                    text("UPDATE transactions SET asset_id = :new_aid WHERE id = :tid"),
                    {"new_aid": target_id, "tid": r.tx_id},
                )

            affected = set()
            for r in rows:
                affected.add(str(r.asset_id))
                key = (str(r.portfolio_id), r.symbol, r.tx_exchange.strip())
                affected.add(asset_cache[key])

            for aid in affected:
                net = conn.execute(
                    text(
                        "SELECT COALESCE(SUM(CASE"
                        " WHEN transaction_type::text IN ('BUY','CONVERSION_IN','TRANSFER_IN','AIRDROP','STAKING_REWARD','DIVIDEND','INTEREST')"
                        " THEN quantity ELSE 0 END), 0)"
                        " - COALESCE(SUM(CASE"
                        " WHEN transaction_type::text IN ('SELL','TRANSFER_OUT','CONVERSION_OUT','FEE')"
                        " THEN quantity ELSE 0 END), 0) AS net_qty"
                        " FROM transactions WHERE asset_id = :aid"
                    ),
                    {"aid": aid},
                ).fetchone()
                qty = max(0, float(net.net_qty)) if net else 0

                buy = conn.execute(
                    text(
                        "SELECT COALESCE(SUM(quantity), 0) AS tq, COALESCE(SUM(quantity * price), 0) AS tc"
                        " FROM transactions WHERE asset_id = :aid"
                        " AND transaction_type::text IN ('BUY','CONVERSION_IN')"
                    ),
                    {"aid": aid},
                ).fetchone()
                avg = float(buy.tc) / float(buy.tq) if buy and float(buy.tq) > 0 else 0

                conn.execute(
                    text("UPDATE assets SET quantity = :qty, avg_buy_price = :avg WHERE id = :aid"),
                    {"qty": qty, "avg": avg, "aid": aid},
                )
                logger.info("Recalculated asset %s: qty=%s, avg=%s", aid, qty, avg)

            logger.info("Multiplatform fix complete")
        sync_engine.dispose()
    except Exception as e:
        logger.warning("Multiplatform fix failed: %s", e)
