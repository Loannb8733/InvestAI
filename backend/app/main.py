"""
InvestAI - Backend API
Plateforme multi-utilisateurs de gestion et d'analyse d'investissements
"""

from __future__ import annotations

import os
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Mapping

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy import text
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.gzip import GZipMiddleware

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.contexte_execution import sert_une_requete_http
from app.core.database import engine
from app.core.logging import get_logger, setup_logging
from app.core.rate_limit import limiter
from app.models import Base

# Setup structured logging
setup_logging()
logger = get_logger(__name__)

# Sentry error tracking — never let a bad DSN or transient sentry-sdk init
# error take the whole process down. A 500 with no Sentry beats no app at all.
if settings.sentry_enabled:
    try:
        import sentry_sdk
        from sentry_sdk.integrations.celery import CeleryIntegration
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.redis import RedisIntegration
        from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

        from app.core.sentry_scrub import scrub_event

        sentry_sdk.init(
            dsn=settings.SENTRY_DSN,
            environment=settings.APP_ENV,
            release="investai@1.0.0",
            traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
            profiles_sample_rate=settings.SENTRY_PROFILES_SAMPLE_RATE,
            integrations=[
                FastApiIntegration(transaction_style="endpoint"),
                SqlalchemyIntegration(),
                CeleryIntegration(),
                RedisIntegration(),
            ],
            send_default_pii=False,
            # Scrub Authorization/Cookie headers and any payload field whose
            # name matches password/secret/token/api_key/mfa/totp/… before
            # events leave the process. FastApiIntegration would otherwise
            # capture login bodies, JWT bearer tokens, exchange API keys,
            # and MFA codes.
            before_send=scrub_event,
            before_send_transaction=scrub_event,
        )
        logger.info("Sentry initialized (env=%s)", settings.APP_ENV)
    except Exception as _sentry_err:  # noqa: BLE001 — degrade silently
        logger.warning("Sentry init failed, continuing without it: %s", _sentry_err)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware for logging HTTP requests with timing and trace_id."""

    async def dispatch(self, request: Request, call_next):
        """Log request details and timing."""
        start_time = time.perf_counter()

        # Marque toute la pile d'appels comme « servant une requête HTTP ».
        # Les intégrations tierces s'en servent pour renoncer plutôt que
        # d'attendre un `Retry-After` : un utilisateur est devant l'écran, et le
        # cache sait déjà répondre. Les workers Celery n'ont pas ce marqueur et
        # gardent le droit d'attendre.
        sert_une_requete_http.set(True)

        # Generate or accept trace_id for request correlation
        trace_id = request.headers.get("X-Request-ID", uuid.uuid4().hex[:16])
        request.state.trace_id = trace_id

        # Set Sentry user context from JWT if available
        if settings.sentry_enabled:
            auth_header = request.headers.get("authorization", "")
            if auth_header.startswith("Bearer "):
                try:
                    from app.core.security import decode_access_token

                    payload = decode_access_token(auth_header.split(" ")[1])
                    if payload:
                        import sentry_sdk

                        sentry_sdk.set_user({"id": payload.get("sub"), "ip_address": "{{auto}}"})
                except Exception as exc:  # noqa: BLE001
                    logger.debug("Failed to set Sentry user context from token: %s", exc)

        try:
            # Process the request
            response = await call_next(request)

            # Echo trace_id in response header
            response.headers["X-Request-ID"] = trace_id

            # Calculate duration
            duration_ms = (time.perf_counter() - start_time) * 1000

            # Log based on response status
            log_data = {
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": round(duration_ms, 2),
                "client_ip": request.client.host if request.client else "unknown",
                "trace_id": trace_id,
            }

            # Skip health check logs to reduce noise
            if not request.url.path.startswith("/health"):
                if response.status_code >= 500:
                    logger.error("Request failed", extra=log_data)
                elif response.status_code >= 400:
                    logger.warning("Request error", extra=log_data)
                elif duration_ms > 1000:  # Log slow requests (>1s)
                    logger.warning("Slow request", extra=log_data)
                else:
                    logger.debug("Request completed", extra=log_data)

            return response
        except Exception as e:
            import traceback

            logger.error(f"Middleware error: {type(e).__name__}: {e}")
            logger.error(f"Traceback:\n{traceback.format_exc()}")
            # Return a proper response instead of re-raising: re-raising a
            # BaseHTTPMiddleware exception bypasses CORSMiddleware's send
            # wrapper, resulting in 500 responses without CORS headers.
            return JSONResponse(
                status_code=500,
                content={"detail": "Internal server error"},
                headers={"X-Request-ID": trace_id},
            )


# Libellés de TRANSFER_OUT qui ne sont PAS des retraits vers un wallet : ce sont des
# écritures internes de réconciliation (mise à zéro d'un solde fantôme, balayage de
# poussière, ajustement manuel). Les miroiter fabrique une position sur le cold wallet
# pour des actifs qui n'y ont jamais mis les pieds — constaté en production le
# 2026-06-07 : une opération de NETTOYAGE a créé 5 entrées fantômes sur Tangem
# (109 529 PEPE, 25,21 USDT, 2,52 USDG, 0,0086 DOGE), l'utilisateur n'ayant jamais
# détenu ces actifs là-bas.
INTERNAL_ADJUSTMENT_NOTE_PREFIXES = (
    "Ajustement balance",
    "Phantom holding zeroed",
    "Solde zéro sur",
    "Dust sweep",
    "Manual adjustment",
    "Réconciliation :",
    # Cale posée à la main pour annuler un miroir fantôme déjà écrit : la miroiter
    # recréerait précisément ce qu'elle vient d'annuler.
    "Cale ",
)


# Valeur du paramètre lié `:internal_note_patterns` des requêtes de mirroring : un
# motif de préfixe par libellé. Les libellés ne sont jamais concaténés dans le SQL.
INTERNAL_NOTE_PATTERNS = [f"{prefix}%" for prefix in INTERNAL_ADJUSTMENT_NOTE_PREFIXES]


def _fix_multiplatform_assets():
    """One-shot: move transactions whose exchange differs from their asset to a per-exchange asset."""
    try:
        import uuid

        from sqlalchemy import create_engine, text

        from app.core.config import settings

        sync_engine = create_engine(settings.DATABASE_URL_SYNC)
        with sync_engine.begin() as conn:
            # Find mismatched transactions
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

            # Group by (portfolio_id, symbol, tx_exchange) -> create or find assets
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

            # Move transactions
            for r in rows:
                key = (str(r.portfolio_id), r.symbol, r.tx_exchange.strip())
                target_id = asset_cache[key]
                conn.execute(
                    text("UPDATE transactions SET asset_id = :new_aid WHERE id = :tid"),
                    {"new_aid": target_id, "tid": r.tx_id},
                )

            # Recalculate quantities for all affected assets
            affected = set()
            for r in rows:
                affected.add(str(r.asset_id))
                key = (str(r.portfolio_id), r.symbol, r.tx_exchange.strip())
                affected.add(asset_cache[key])

            for aid in affected:
                # Net quantity
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

                # Avg buy price
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


def _create_missing_transfer_mirrors():
    """One-shot: create mirror transfer_in for transfer_out transactions that have no related_transaction_id.

    This handles existing transfer_out transactions (e.g. exchange → cold wallet)
    that were imported before the mirror feature was added.
    Default destination: 'Tangem' (user's cold wallet).
    """
    try:
        import uuid as uuid_mod

        from sqlalchemy import create_engine, text

        from app.core.config import settings
        from app.services.transfer_service import COLD_WALLET_DESTINATION as DEFAULT_DESTINATION

        sync_engine = create_engine(settings.DATABASE_URL_SYNC)
        with sync_engine.begin() as conn:
            # Ensure related_transaction_id column exists (may be missing if
            # the DB was created by create_all before the column was added)
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

            # Find transfer_out without VALID mirrors (broken refs or NULL)
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
                    # Écarte les écritures d'ajustement interne (cf. INTERNAL_NOTE_PATTERNS) :
                    # les libellés voyagent en paramètre lié, la requête reste littérale.
                    " AND NOT (COALESCE(t.notes, '') LIKE ANY(:internal_note_patterns))"
                ),
                {"internal_note_patterns": INTERNAL_NOTE_PATTERNS},
            ).fetchall()

            if not rows:
                logger.info("No unmirrored transfer_out transactions found")
                sync_engine.dispose()
                return

            # Quantité réellement miroitée par actif destination : c'est ce dont on
            # incrémentera la destination, sans jamais relire tout son historique.
            mirrored_qty_by_asset: dict[str, float] = {}

            # Clear broken references
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
                        text(
                            "SELECT id FROM assets WHERE portfolio_id = :pid" " AND symbol = :sym AND exchange = :exc"
                        ),
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

                # Calculate mirror quantity (subtract network fee if in same asset)
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

                # Skip if a transfer_in already exists on destination for same
                # symbol, similar date (±1 day), and similar quantity (within 1%)
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

                # Create mirror transfer_in
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
                # Link source → mirror
                conn.execute(
                    text("UPDATE transactions SET related_transaction_id = :mid WHERE id = :tid"),
                    {"mid": mirror_id, "tid": r.id},
                )
                mirrored_qty_by_asset[dest_asset_id] = mirrored_qty_by_asset.get(dest_asset_id, 0.0) + float(mirror_qty)

            # On INCREMENTE la destination du montant réellement miroité, au lieu de
            # recalculer son solde depuis tout son historique.
            #
            # Le recalcul supposait l'historique exhaustif. Il ne l'est jamais pour un
            # cold wallet : rien ne peut remonter ses sorties (pas d'API). Recalculer
            # y remplaçait donc un solde juste par la somme des seules entrées connues.
            # Même logique que create_mirror_transfer_in() dans transfer_service.py.
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


def _run_alembic_upgrade():
    """Run pending Alembic migrations (sync, called once at startup).

    If the database was created via create_all (no alembic_version row),
    stamp it at the last schema migration so only data-fix migrations run.
    """
    try:
        from sqlalchemy import create_engine, inspect, text

        from alembic import command
        from alembic.config import Config
        from app.core.config import settings

        alembic_cfg = Config("alembic.ini")

        # Check if alembic_version table exists and has a current revision
        sync_engine = create_engine(settings.DATABASE_URL_SYNC)
        with sync_engine.connect() as conn:
            inspector = inspect(conn)
            if inspector.has_table("alembic_version"):
                row = conn.execute(text("SELECT version_num FROM alembic_version")).fetchone()
                if row:
                    logger.info("Alembic current revision: %s", row[0])
                else:
                    # Table exists but empty — stamp to head so upgrade is a no-op
                    logger.info("alembic_version empty, stamping to head")
                    command.stamp(alembic_cfg, "head")
            else:
                # Table doesn't exist — DB was created by create_all, stamp to head
                logger.info("No alembic_version table, stamping to head")
                command.stamp(alembic_cfg, "head")
        sync_engine.dispose()

        command.upgrade(alembic_cfg, "head")
        logger.info("Alembic migrations applied successfully")
    except Exception as e:
        logger.warning("Alembic migration skipped or failed: %s", e)


async def _rehash_transactions_internal_hash():
    """One-shot, idempotent: recompute internal_hash with the precise formula.

    The dedup hash formula moved from float(.8f) to full Decimal(12) precision
    (fixes micro-price assets like PEPE collapsing to a single hash). Existing
    rows still carry the OLD hash, so a re-import would no longer dedup against
    them. This rewrites every row's internal_hash to the new formula. It only
    writes when a value actually changes, so after the first deploy it is a
    no-op pass. Collisions within the pass (genuinely near-identical rows kept
    intentionally) are excluded from the unique index by setting NULL.
    """
    try:
        from sqlalchemy import select

        from app.core.database import AsyncSessionLocal
        from app.models.transaction import Transaction, compute_transaction_hash

        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Transaction))
            txs = result.scalars().all()
            seen: dict = {}
            changed = 0
            nulled = 0
            for tx in txs:
                ts = tx.executed_at.strftime("%Y-%m-%d") if tx.executed_at else ""
                ttype = tx.transaction_type.value if hasattr(tx.transaction_type, "value") else str(tx.transaction_type)
                target = compute_transaction_hash(
                    asset_id=str(tx.asset_id),
                    transaction_type=ttype,
                    quantity=str(tx.quantity),
                    price=str(tx.price),
                    executed_at=ts,
                )
                if target in seen:
                    if tx.internal_hash is not None:
                        tx.internal_hash = None
                        nulled += 1
                    continue
                seen[target] = tx.id
                if tx.internal_hash != target:
                    tx.internal_hash = target
                    changed += 1
            if changed or nulled:
                await db.commit()
                logger.info(
                    "Rehashed transactions: %d updated, %d nulled on collision",
                    changed,
                    nulled,
                )
    except Exception as e:
        logger.warning("Transaction rehash skipped or failed: %s", e)


# Fixed key serializing concurrent boot migrations across processes.
_BOOT_LOCK_KEY = 4242424242


@asynccontextmanager
async def _boot_advisory_lock(key: int, lock_engine=None):
    """Hold a Postgres session-level advisory lock for the block's duration.

    Serializes concurrent boots (multi-worker / zero-downtime deploy overlap).
    Fail-open: if the lock can't be acquired, the block still runs (unlocked),
    identical to the pre-lock behaviour — it never blocks startup. The lock is
    released on exit, or auto-released if the process dies (connection closes).
    ``lock_engine`` defaults to the app engine and is injectable for tests.
    """
    eng = lock_engine if lock_engine is not None else engine
    lock_conn = None
    try:
        lock_conn = await eng.connect()
        await lock_conn.execute(text("SELECT pg_advisory_lock(:k)"), {"k": key})
        logger.info("Acquired boot advisory lock")
    except Exception as e:
        logger.warning("Boot advisory lock unavailable, proceeding without it: %s", e)
        if lock_conn is not None:
            try:
                await lock_conn.close()
            except Exception as close_exc:  # noqa: BLE001
                logger.debug(
                    "Failed to close boot advisory-lock connection after acquire error: %s",
                    close_exc,
                )
        lock_conn = None
    try:
        yield
    finally:
        if lock_conn is not None:
            try:
                await lock_conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": key})
            except Exception as unlock_exc:  # noqa: BLE001
                logger.debug(
                    "Failed to release boot advisory lock (auto-released on disconnect): %s",
                    unlock_exc,
                )
            try:
                await lock_conn.close()
            except Exception as close_exc:  # noqa: BLE001
                logger.debug("Failed to close boot advisory-lock connection: %s", close_exc)


async def _run_startup_migrations():
    """Run boot migrations + idempotent one-shots under the boot advisory lock.

    The lock serializes concurrent boots so Alembic, create_all and the data
    one-shots never race; everything inside is idempotent so a second waiter
    runs as a no-op.
    """
    async with _boot_advisory_lock(_BOOT_LOCK_KEY):
        # Run Alembic migrations before creating tables
        _run_alembic_upgrade()
        # One-shot fix: split transactions with mismatched exchange into separate assets
        _fix_multiplatform_assets()
        # One-shot fix: create mirror transfer_in for existing transfer_out (→ Tangem)
        _create_missing_transfer_mirrors()

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            # Guard: add columns that may be missing when the DB was created via
            # create_all before the column existed (Alembic stamp-to-head skips them).
            await conn.execute(
                text("ALTER TABLE portfolios ADD COLUMN IF NOT EXISTS cash_balances JSON NOT NULL DEFAULT '{}'")
            )

        # One-shot (idempotent): migrate internal_hash to the precise Decimal formula.
        await _rehash_transactions_internal_hash()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    # Startup
    logger.info(f"Starting {settings.APP_NAME} (env={settings.APP_ENV}, debug={settings.DEBUG})")

    # Boot migrations + idempotent one-shots, serialized by a Postgres advisory
    # lock so concurrent boots (multi-worker / deploy overlap) cannot race.
    await _run_startup_migrations()

    # Trigger historical data cache on startup — run inline (no Celery needed)
    async def _startup_backfill():
        try:
            from app.tasks.history_cache import _fetch_and_cache_all

            count = await _fetch_and_cache_all()
            logger.info("Startup price backfill complete: %d assets cached", count)
        except Exception as e:
            logger.warning("Startup price backfill failed: %s", e)

    import asyncio

    asyncio.create_task(_startup_backfill())
    logger.info("Triggered startup price backfill (background)")
    yield
    # Shutdown
    logger.info(f"Shutting down {settings.APP_NAME}")
    await engine.dispose()


# Conditionally expose OpenAPI docs (only in development/debug mode)
OPENAPI_TAGS = [
    {
        "name": "Authentication",
        "description": "Login, register, MFA (TOTP), JWT refresh, password reset, email verification.",
    },
    {
        "name": "Users",
        "description": "User management and preferences (admin: list/delete users).",
    },
    {
        "name": "Dashboard",
        "description": "Portfolio summary, allocation breakdown, performance overview, and recommendations.",
    },
    {
        "name": "Portfolios",
        "description": "CRUD portfolios, snapshot history, rebalancing suggestions.",
    },
    {
        "name": "Assets",
        "description": "CRUD assets (crypto, stocks, ETF, real estate), price history, exchange sync.",
    },
    {
        "name": "Transactions",
        "description": "CRUD transactions (buy/sell/dividend/fee/airdrop/conversion), CSV bulk import, P&L.",
    },
    {
        "name": "API Keys",
        "description": "Manage exchange API keys (Binance, Kraken, Crypto.com). Keys are Fernet-encrypted at rest.",
    },
    {
        "name": "Analytics",
        "description": "Sharpe, Sortino, Calmar ratios, VaR/CVaR, max drawdown, correlation matrix, "
        "Markowitz optimization, stress testing, diversification score.",
    },
    {
        "name": "Predictions",
        "description": "ML ensemble forecasts (Prophet + ARIMA + XGBoost + EMA + Linear). "
        "Confidence intervals, model breakdown, feature importance.",
    },
    {
        "name": "Alerts",
        "description": "Price and performance alerts with threshold conditions and notifications.",
    },
    {
        "name": "Reports",
        "description": "Generate PDF/Excel reports: performance summary, holdings, French fiscal form 2086.",
    },
    {
        "name": "Notes",
        "description": "Investment journal: create, search, and manage notes per asset or portfolio.",
    },
    {
        "name": "Calendar",
        "description": "Financial calendar: dividends, loyers, scheduled events with recurring support.",
    },
    {
        "name": "Simulations",
        "description": "FIRE calculator, DCA simulator, what-if scenarios, Monte Carlo projections.",
    },
    {
        "name": "Notifications",
        "description": "User notifications: list, mark as read, delete.",
    },
    {
        "name": "Insights",
        "description": "Rule-based insights: concentration risk, volatility alerts, rebalancing.",
    },
    {
        "name": "Smart Insights",
        "description": "AI-powered recommendations, portfolio health analysis, rebalancing suggestions.",
    },
    {
        "name": "Goals",
        "description": "Financial goals tracking with target amounts, deadlines, and progress.",
    },
    {
        "name": "WebSocket",
        "description": "Real-time price updates via WebSocket connection.",
    },
    {"name": "System", "description": "Health check, system stats, version info."},
]

app = FastAPI(
    title=settings.APP_NAME,
    description=(
        "**InvestAI** — API de gestion et d'analyse d'investissements multi-actifs.\n\n"
        "Supporte crypto, actions, ETF et immobilier avec analytics avancés, "
        "prédictions ML, et intégrations exchanges (Binance, Kraken, Crypto.com).\n\n"
        "**Auth**: JWT Bearer token (15min) + refresh token (7j). "
        "Inclure `Authorization: Bearer <token>` dans les headers."
    ),
    version="1.0.0",
    openapi_tags=OPENAPI_TAGS,
    # Disable OpenAPI in production for security
    openapi_url=f"{settings.API_V1_PREFIX}/openapi.json" if settings.DEBUG else None,
    docs_url=f"{settings.API_V1_PREFIX}/docs" if settings.DEBUG else None,
    redoc_url=f"{settings.API_V1_PREFIX}/redoc" if settings.DEBUG else None,
    lifespan=lifespan,
    # Disable trailing slash redirects — they break CORS (307 without CORS headers)
    redirect_slashes=False,
)


# Global exception handler to log errors
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catch all unhandled exceptions and log them."""
    import traceback

    logger.error(f"Unhandled exception: {type(exc).__name__}: {exc}")
    logger.error(f"Traceback:\n{traceback.format_exc()}")
    tb = traceback.format_exc()
    detail = "An internal error occurred. Please try again later."
    # Fail-safe: only expose internals when we're explicitly NOT in production.
    # settings.is_production == (APP_ENV == "production" and not DEBUG), so a
    # misconfigured/empty APP_ENV no longer leaks tracebacks by default.
    if not settings.is_production and settings.DEBUG:
        detail = f"{type(exc).__name__}: {exc}\n{tb}"
    # Safety net: add CORS headers directly in case the exception propagated
    # past the CORSMiddleware send wrapper (e.g. from an async generator edge case).
    origin = request.headers.get("origin", "")
    extra_headers: dict = {}
    if origin and _is_allowed_origin(origin):
        extra_headers["Access-Control-Allow-Origin"] = origin
        extra_headers["Access-Control-Allow-Credentials"] = "true"
    return JSONResponse(
        status_code=500,
        content={"detail": detail},
        headers=extra_headers if extra_headers else None,
    )


# Rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS middleware with restricted methods and headers
# Production frontend origin (always allowed even if CORS_ORIGINS env is unset).
_PROD_FRONTEND_ORIGINS = ["https://investai-orcin.vercel.app"]
_vercel_suffix = ".vercel.app"


def _is_allowed_origin(origin: str) -> bool:
    """Check if origin is in the explicit list or (non-prod only) a Vercel preview."""
    if origin in settings.CORS_ORIGINS or origin in _PROD_FRONTEND_ORIGINS:
        return True
    # Open *.vercel.app previews are only trusted outside production to avoid
    # treating any attacker-controlled vercel.app subdomain as a credentialed origin.
    if not settings.is_production and origin.startswith("https://") and origin.endswith(_vercel_suffix):
        return True
    return False


# Build the allowed-origin regex.
# - Explicit origins from CORS_ORIGINS env (e.g. https://investai-orcin.vercel.app)
# - The known production frontend origin (hardcoded fallback)
# - The broad *.vercel.app preview wildcard ONLY in non-production environments.
_allowed_origins = list(dict.fromkeys([*settings.CORS_ORIGINS, *_PROD_FRONTEND_ORIGINS]))
_explicit_escaped = [o.replace(".", r"\.").replace("://", r"://") for o in _allowed_origins]
_regex_parts = list(_explicit_escaped)
if not settings.is_production:
    _regex_parts.append(r"https://.*\.vercel\.app")
_cors_regex = "|".join(_regex_parts)

# Middleware order matters: last added = outermost.
# CORS must be outermost so headers are always present, even on 500 errors.
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(GZipMiddleware, minimum_size=500)
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=f"^({_cors_regex})$",
    allow_credentials=True,
    allow_methods=settings.CORS_ALLOWED_METHODS,  # Restricted, not "*"
    allow_headers=settings.CORS_ALLOWED_HEADERS,  # Restricted, not "*"
    expose_headers=["X-Total-Count", "X-Request-ID"],  # Pagination + tracing
    max_age=600,  # Cache preflight for 10 minutes
)


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    """Attach baseline security headers to every response.

    The API serves JSON only, so a strict CSP isn't required, but these headers
    harden against MIME sniffing, clickjacking and referrer leakage. HSTS is only
    sent in production (where TLS is guaranteed) to avoid breaking local http dev.
    """
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
    if settings.is_production:
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response


_MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


@app.middleware("http")
async def dashboard_cache_invalidation_middleware(request: Request, call_next):
    """Invalidate a user's cached dashboard after any successful write.

    The dashboard response is cached per user (see endpoints/dashboard.py). Any
    mutating request (POST/PUT/PATCH/DELETE) that completes with a 2xx status for
    an authenticated user drops all of their dashboard cache entries. Over-
    invalidation is harmless (it only forces a recompute on the next dashboard
    load); under-invalidation never happens, so a cache hit is never stale.
    """
    response = await call_next(request)
    try:
        if request.method in _MUTATING_METHODS and 200 <= response.status_code < 300:
            user_id = getattr(request.state, "user_id", None)
            if user_id:
                from app.core.redis_client import invalidate_dashboard_cache as invalidate_redis_dashboard
                from app.services.metrics_service import invalidate_dashboard_cache as invalidate_inmem_dashboard

                # Purge Redis (cross-worker) AND the per-process in-memory cache.
                # Skipping in-memory left stale data live for up to TTL (2 min)
                # after mutations -- which the user saw on 2026-06-08 when a
                # Tangem qty fix was masked by a stale +630 EUR PnL display.
                await invalidate_redis_dashboard(user_id)
                invalidate_inmem_dashboard(user_id)
    except Exception as exc:  # noqa: BLE001 — never let cache bookkeeping break a successful request
        logger.debug("Dashboard cache invalidation after write failed: %s", exc)
    return response


# Include API router
app.include_router(api_router, prefix=settings.API_V1_PREFIX)


# L'endpoint POST /api/v1/admin/fix-mirrors a été supprimé (SEC-04, 2026-09-01).
#
# Il déclenchait à la main ce que `_create_missing_transfer_mirrors()` fait déjà à
# chaque démarrage, sous verrou et de façon idempotente : il n'apportait aucune
# capacité. En revanche il exécutait un `ALTER TABLE` depuis une requête HTTP,
# renvoyait au client la liste des transactions de transfert (id, symbole, exchange)
# et son `except` renvoyait `str(e)` — la fuite d'exception corrigée par SEC-02.
# C'est aussi par ce chemin que les 5 entrées fantômes Tangem sont entrées
# (NEW-02/NEW-03). La création de colonne relève d'Alembic, pas d'une route.


# Version du code déployé, résolue une fois au démarrage.
#
# Vérifier qu'un déploiement a bien pris demandait jusqu'ici de sonder une route
# supprimée et d'espérer un 404 : la méthode marche une fois, puis le marqueur
# est consommé. Les seuls autres changements d'une release vivent derrière
# l'authentification, donc invérifiables depuis l'extérieur.
#
# `RENDER_GIT_COMMIT` est fourni par Render à chaque build ; `GIT_COMMIT` sert
# de repli pour les autres hébergeurs et Docker local.
#
# Le SHA est tronqué à 7 caractères : de quoi identifier une version sans en
# dire plus qu'un `git log` du dépôt, qui est privé.
def resoudre_commit(env: Mapping[str, str] | None = None) -> str:
    """SHA court du commit déployé, ou « inconnu » si l'hébergeur n'en fournit pas."""
    source = os.environ if env is None else env
    brut = (source.get("RENDER_GIT_COMMIT") or source.get("GIT_COMMIT") or "").strip()
    return brut[:7] if brut else "inconnu"


_COMMIT_DEPLOYE = resoudre_commit()
_DEMARRE_A = datetime.now(timezone.utc).isoformat(timespec="seconds")


@app.get("/health")
@app.get("/api/v1/health")
async def health_check():
    """Liveness probe — returns 200 if the process is running."""
    return {
        "app": settings.APP_NAME,
        "status": "alive",
        "commit": _COMMIT_DEPLOYE,
        "demarre_a": _DEMARRE_A,
    }


@app.get("/health/ready")
@app.get("/api/v1/health/ready")
async def readiness_check():
    """Readiness probe — checks DB and Redis connectivity."""
    checks = {"app": settings.APP_NAME, "status": "ready"}
    http_status = 200

    # Check database
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception:
        checks["database"] = "error"
        checks["status"] = "degraded"
        http_status = 503

    # Check Redis
    try:
        import redis.asyncio as aioredis

        from app.core.redis_client import redis_async_url, redis_ssl_kwargs

        r = aioredis.from_url(redis_async_url(), socket_timeout=2, **redis_ssl_kwargs())
        await r.ping()
        await r.aclose()
        checks["redis"] = "ok"
    except Exception:
        checks["redis"] = "error"
        checks["status"] = "degraded"
        http_status = 503

    return JSONResponse(content=checks, status_code=http_status)
