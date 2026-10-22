import logging

logger = logging.getLogger(__name__)


INTERNAL_ADJUSTMENT_NOTE_PREFIXES = (
    "Ajustement balance",
    "Phantom holding zeroed",
    "Solde zéro sur",
    "Dust sweep",
    "Manual adjustment",
    "Réconciliation :",
    "Cale ",
)

INTERNAL_NOTE_PATTERNS = [f"{prefix}%" for prefix in INTERNAL_ADJUSTMENT_NOTE_PREFIXES]


def create_missing_transfer_mirrors() -> None:
    try:
        import uuid as uuid_mod

        from sqlalchemy import create_engine, text

        from app.core.config import settings
        from app.domains.transactions.transfers import COLD_WALLET_DESTINATION as DEFAULT_DESTINATION

        sync_engine = create_engine(settings.DATABASE_URL_SYNC)
        with sync_engine.begin() as conn:
            col_check = conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns"
                    " WHERE table_name = 'transactions'"
                    " AND column_name = 'related_transaction_id'"
                )
            ).fetchone()
            if not col_check:
                logger.info("Adding missing related_transaction_id column to transactions")
                conn.execute(
                    text(
                        "ALTER TABLE transactions ADD COLUMN related_transaction_id UUID"
                        " REFERENCES transactions(id) ON DELETE SET NULL"
                    )
                )
                conn.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS ix_transactions_related_tx_id ON transactions(related_transaction_id)"
                    )
                )

            rows = conn.execute(
                text(
                    "SELECT t.id, t.asset_id, t.quantity, t.price, t.fee, t.fee_currency,"
                    " t.currency, t.executed_at, t.exchange AS tx_exchange,"
                    " a.portfolio_id, a.symbol, a.name, a.asset_type, a.exchange AS asset_exchange,"
                    " a.currency AS asset_currency"
                    " FROM transactions t JOIN assets a ON t.asset_id = a.id"
                    " LEFT JOIN transactions m ON t.related_transaction_id = m.id"
                    " WHERE t.transaction_type::text = 'TRANSFER_OUT'"
                    " AND (t.related_transaction_id IS NULL OR m.id IS NULL)"
                    " AND NOT (COALESCE(t.notes, '') LIKE ANY(:internal_note_patterns))"
                ),
                {"internal_note_patterns": INTERNAL_NOTE_PATTERNS},
            ).fetchall()

            if not rows:
                logger.info("No unmirrored transfer_out transactions found")
                sync_engine.dispose()
                return

            mirrored_qty_by_asset: dict[str, float] = {}

            for r in rows:
                conn.execute(
                    text("UPDATE transactions SET related_transaction_id = NULL WHERE id = :tid"),
                    {"tid": r.id},
                )

            logger.info("Found %d transfer_out without mirrors", len(rows))

            asset_cache = {}
            for r in rows:
                key = (str(r.portfolio_id), r.symbol, DEFAULT_DESTINATION)
                if key not in asset_cache:
                    existing = conn.execute(
                        text("SELECT id FROM assets WHERE portfolio_id = :pid AND symbol = :sym AND exchange = :exc"),
                        {
                            "pid": r.portfolio_id,
                            "sym": r.symbol,
                            "exc": DEFAULT_DESTINATION,
                        },
                    ).fetchone()

                    if existing:
                        asset_cache[key] = str(existing.id)
                    else:
                        new_id = str(uuid_mod.uuid4())
                        conn.execute(
                            text(
                                "INSERT INTO assets (id, portfolio_id, symbol, name, asset_type,"
                                " quantity, avg_buy_price, exchange, currency)"
                                " VALUES (:id, :pid, :sym, :name, :atype, 0, 0, :exc, :cur)"
                            ),
                            {
                                "id": new_id,
                                "pid": r.portfolio_id,
                                "sym": r.symbol,
                                "name": r.name,
                                "atype": r.asset_type,
                                "exc": DEFAULT_DESTINATION,
                                "cur": r.asset_currency,
                            },
                        )
                        asset_cache[key] = new_id
                        logger.info(
                            "Created asset %s/%s (id=%s)",
                            r.symbol,
                            DEFAULT_DESTINATION,
                            new_id,
                        )

                qty = float(r.quantity)
                fee = float(r.fee) if r.fee else 0
                fee_currency = (r.fee_currency or "").upper()
                if fee > 0 and (not fee_currency or fee_currency == r.symbol.upper()):
                    mirror_qty = qty - fee
                else:
                    mirror_qty = qty
                if mirror_qty <= 0:
                    continue

                dest_asset_id = asset_cache[key]

                from datetime import timedelta as _td

                existing_mirror = conn.execute(
                    text(
                        "SELECT id, quantity FROM transactions"
                        " WHERE asset_id = :aid AND transaction_type = 'TRANSFER_IN'"
                        " AND executed_at >= :d1 AND executed_at <= :d2"
                    ),
                    {
                        "aid": dest_asset_id,
                        "d1": r.executed_at - _td(days=1),
                        "d2": r.executed_at + _td(days=1),
                    },
                ).fetchall()
                skip = False
                for em in existing_mirror:
                    eq = float(em.quantity)
                    if eq > 0 and abs(eq - mirror_qty) / eq < 0.01:
                        logger.info(
                            "Skip auto-mirror for %s: transfer_in exists (id=%s)",
                            r.symbol,
                            em.id,
                        )
                        conn.execute(
                            text("UPDATE transactions SET related_transaction_id = :mid WHERE id = :tid"),
                            {"mid": str(em.id), "tid": r.id},
                        )
                        skip = True
                        break
                if skip:
                    continue

                mirror_id = str(uuid_mod.uuid4())

                conn.execute(
                    text(
                        "INSERT INTO transactions (id, asset_id, transaction_type, quantity, price,"
                        " fee, currency, executed_at, exchange, notes, related_transaction_id)"
                        " VALUES (:id, :aid, 'TRANSFER_IN', :qty, :price, 0, :cur,"
                        " :exec_at, :exc, :notes, :related_id)"
                    ),
                    {
                        "id": mirror_id,
                        "aid": dest_asset_id,
                        "qty": mirror_qty,
                        "price": float(r.price),
                        "cur": r.currency,
                        "exec_at": r.executed_at,
                        "exc": DEFAULT_DESTINATION,
                        "notes": f"Auto-mirror from {r.tx_exchange or r.asset_exchange or 'unknown'}",
                        "related_id": r.id,
                    },
                )
                conn.execute(
                    text("UPDATE transactions SET related_transaction_id = :mid WHERE id = :tid"),
                    {"mid": mirror_id, "tid": r.id},
                )
                mirrored_qty_by_asset[dest_asset_id] = mirrored_qty_by_asset.get(dest_asset_id, 0.0) + float(mirror_qty)

            for aid, added in mirrored_qty_by_asset.items():
                if added <= 0:
                    continue
                conn.execute(
                    text("UPDATE assets SET quantity = COALESCE(quantity, 0) + :add WHERE id = :aid"),
                    {"add": added, "aid": aid},
                )
                logger.info("Dest asset %s: +%s (miroirs créés)", aid, added)

            logger.info("Transfer mirror fix complete")
        sync_engine.dispose()
    except Exception as e:
        import traceback

        logger.error("Transfer mirror fix failed: %s\n%s", e, traceback.format_exc())
