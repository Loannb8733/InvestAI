"""
InvestAI - Backend API
Plateforme multi-utilisateurs de gestion et d'analyse d'investissements
"""

import time
import uuid
from contextlib import asynccontextmanager

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
from app.core.database import engine
from app.core.logging import get_logger, setup_logging
from app.core.rate_limit import limiter
from app.models import Base

# Setup structured logging
setup_logging()
logger = get_logger(__name__)

# Sentry error tracking
if settings.sentry_enabled:
    import sentry_sdk
    from sentry_sdk.integrations.celery import CeleryIntegration
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    from sentry_sdk.integrations.redis import RedisIntegration
    from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

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
    )
    logger.info("Sentry initialized (env=%s)", settings.APP_ENV)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware for logging HTTP requests with timing and trace_id."""

    async def dispatch(self, request: Request, call_next):
        """Log request details and timing."""
        start_time = time.perf_counter()

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
                except Exception:
                    pass

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
            raise


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
                        {"pid": r.portfolio_id, "sym": r.symbol, "exc": r.tx_exchange.strip()},
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
                        logger.info("Created asset %s/%s (id=%s)", r.symbol, r.tx_exchange.strip(), new_id)

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
                        " WHEN transaction_type::text IN ('buy','conversion_in','transfer_in','airdrop','staking_reward','dividend','interest')"
                        " THEN quantity ELSE 0 END), 0)"
                        " - COALESCE(SUM(CASE"
                        " WHEN transaction_type::text IN ('sell','transfer_out','conversion_out','fee')"
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
                        " AND transaction_type::text IN ('buy','conversion_in')"
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

        DEFAULT_DESTINATION = "Tangem"
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
                    " WHERE t.transaction_type::text = 'transfer_out'"
                    " AND (t.related_transaction_id IS NULL OR m.id IS NULL)"
                )
            ).fetchall()

            if not rows:
                logger.info("No unmirrored transfer_out transactions found")
                sync_engine.dispose()
                return

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
                        {"pid": r.portfolio_id, "sym": r.symbol, "exc": DEFAULT_DESTINATION},
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
                        logger.info("Created asset %s/%s (id=%s)", r.symbol, DEFAULT_DESTINATION, new_id)

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
                mirror_id = str(uuid_mod.uuid4())

                # Create mirror transfer_in
                conn.execute(
                    text(
                        "INSERT INTO transactions (id, asset_id, transaction_type, quantity, price,"
                        " fee, currency, executed_at, exchange, notes, related_transaction_id)"
                        " VALUES (:id, :aid, 'transfer_in', :qty, :price, 0, :cur,"
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

            # Recalculate quantities for all destination assets
            for key, aid in asset_cache.items():
                net = conn.execute(
                    text(
                        "SELECT COALESCE(SUM(CASE"
                        " WHEN transaction_type::text IN"
                        " ('buy','conversion_in','transfer_in','airdrop','staking_reward','dividend','interest')"
                        " THEN quantity ELSE 0 END), 0)"
                        " - COALESCE(SUM(CASE"
                        " WHEN transaction_type::text IN ('sell','transfer_out','conversion_out','fee')"
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
                        " AND transaction_type::text IN ('buy','conversion_in')"
                    ),
                    {"aid": aid},
                ).fetchone()
                avg = float(buy.tc) / float(buy.tq) if buy and float(buy.tq) > 0 else 0

                conn.execute(
                    text("UPDATE assets SET quantity = :qty, avg_buy_price = :avg WHERE id = :aid"),
                    {"qty": qty, "avg": avg, "aid": aid},
                )
                logger.info("Recalculated dest asset %s: qty=%s, avg=%s", aid, qty, avg)

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
        from alembic import command
        from alembic.config import Config
        from sqlalchemy import create_engine, inspect, text

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
                    # Table exists but empty — stamp to last schema migration
                    logger.info("alembic_version empty, stamping to 035_delay_months")
                    command.stamp(alembic_cfg, "035_delay_months")
            else:
                # Table doesn't exist — DB was created by create_all, stamp it
                logger.info("No alembic_version table, stamping to 035_delay_months")
                command.stamp(alembic_cfg, "035_delay_months")
        sync_engine.dispose()

        command.upgrade(alembic_cfg, "head")
        logger.info("Alembic migrations applied successfully")
    except Exception as e:
        logger.warning("Alembic migration skipped or failed: %s", e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    # Startup
    logger.info(f"Starting {settings.APP_NAME} (env={settings.APP_ENV}, debug={settings.DEBUG})")

    # Run Alembic migrations before creating tables
    _run_alembic_upgrade()

    # One-shot fix: split transactions with mismatched exchange into separate assets
    _fix_multiplatform_assets()

    # One-shot fix: create mirror transfer_in for existing transfer_out (→ Tangem)
    _create_missing_transfer_mirrors()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    # Trigger historical data cache on startup (via Celery)
    try:
        from app.tasks.history_cache import cache_historical_data

        cache_historical_data.delay()
        logger.info("Triggered historical data cache task")
    except Exception as e:
        logger.warning("Could not trigger history cache task: %s", e)
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
    {"name": "Users", "description": "User management and preferences (admin: list/delete users)."},
    {
        "name": "Dashboard",
        "description": "Portfolio summary, allocation breakdown, performance overview, and recommendations.",
    },
    {"name": "Portfolios", "description": "CRUD portfolios, snapshot history, rebalancing suggestions."},
    {"name": "Assets", "description": "CRUD assets (crypto, stocks, ETF, real estate), price history, exchange sync."},
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
    {"name": "Alerts", "description": "Price and performance alerts with threshold conditions and notifications."},
    {
        "name": "Reports",
        "description": "Generate PDF/Excel reports: performance summary, holdings, French fiscal form 2086.",
    },
    {"name": "Notes", "description": "Investment journal: create, search, and manage notes per asset or portfolio."},
    {
        "name": "Calendar",
        "description": "Financial calendar: dividends, loyers, scheduled events with recurring support.",
    },
    {
        "name": "Simulations",
        "description": "FIRE calculator, DCA simulator, what-if scenarios, Monte Carlo projections.",
    },
    {"name": "Notifications", "description": "User notifications: list, mark as read, delete."},
    {"name": "Insights", "description": "Rule-based insights: concentration risk, volatility alerts, rebalancing."},
    {
        "name": "Smart Insights",
        "description": "AI-powered recommendations, portfolio health analysis, rebalancing suggestions.",
    },
    {"name": "Goals", "description": "Financial goals tracking with target amounts, deadlines, and progress."},
    {"name": "WebSocket", "description": "Real-time price updates via WebSocket connection."},
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
    if settings.APP_ENV != "production":
        detail = f"{type(exc).__name__}: {exc}\n{tb}"
    return JSONResponse(
        status_code=500,
        content={"detail": detail},
    )


# Rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS middleware with restricted methods and headers
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=settings.CORS_ALLOWED_METHODS,  # Restricted, not "*"
    allow_headers=settings.CORS_ALLOWED_HEADERS,  # Restricted, not "*"
    expose_headers=["X-Total-Count", "X-Request-ID"],  # Pagination + tracing
    max_age=600,  # Cache preflight for 10 minutes
)

# GZip compression (min 500 bytes to avoid overhead on small responses)
app.add_middleware(GZipMiddleware, minimum_size=500)

# Request logging middleware
app.add_middleware(RequestLoggingMiddleware)

# Include API router
app.include_router(api_router, prefix=settings.API_V1_PREFIX)


@app.post("/api/v1/admin/fix-mirrors")
async def admin_fix_mirrors(request: Request):
    """Manually trigger the transfer mirror fix. Returns detailed results."""
    import traceback as tb_mod
    import uuid as uuid_mod

    from sqlalchemy import create_engine

    auth = request.headers.get("authorization", "")
    if not auth.startswith("Bearer "):
        return JSONResponse(status_code=401, content={"detail": "Unauthorized"})

    DEFAULT_DESTINATION = "Tangem"
    log = ["version=pr51-broken-refs"]
    try:
        sync_engine = create_engine(settings.DATABASE_URL_SYNC)
        with sync_engine.begin() as conn:
            # Check related_transaction_id column
            col_check = conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns"
                    " WHERE table_name = 'transactions'"
                    " AND column_name = 'related_transaction_id'"
                )
            ).fetchone()
            if not col_check:
                conn.execute(
                    text(
                        "ALTER TABLE transactions ADD COLUMN related_transaction_id UUID"
                        " REFERENCES transactions(id) ON DELETE SET NULL"
                    )
                )
                log.append("Added related_transaction_id column")
            else:
                log.append("related_transaction_id column exists")

            # Debug: show all distinct transaction_type values
            type_rows = conn.execute(
                text("SELECT DISTINCT transaction_type::text AS tt FROM transactions ORDER BY tt")
            ).fetchall()
            log.append(f"DEBUG all types: {[r.tt for r in type_rows]}")

            # Debug: show all transfer_out and their related_transaction_id state
            debug_rows = conn.execute(
                text(
                    "SELECT t.id, t.related_transaction_id, a.symbol, t.exchange,"
                    " t.transaction_type::text AS tt"
                    " FROM transactions t JOIN assets a ON t.asset_id = a.id"
                    " WHERE t.transaction_type::text ILIKE '%transfer%'"
                )
            ).fetchall()
            for dr in debug_rows:
                log.append(
                    f"DEBUG {dr.tt} {dr.symbol} ({str(dr.id)[:8]})"
                    f" related={str(dr.related_transaction_id)[:8] if dr.related_transaction_id else 'NULL'}"
                )

            # Find transfer_out without VALID mirrors:
            # - related_transaction_id IS NULL, OR
            # - related_transaction_id points to a non-existent transaction
            rows = conn.execute(
                text(
                    "SELECT t.id, t.asset_id, t.quantity, t.price, t.fee, t.fee_currency,"
                    " t.currency, t.executed_at, t.exchange AS tx_exchange,"
                    " a.portfolio_id, a.symbol, a.name, a.asset_type,"
                    " a.exchange AS asset_exchange, a.currency AS asset_currency"
                    " FROM transactions t JOIN assets a ON t.asset_id = a.id"
                    " LEFT JOIN transactions m ON t.related_transaction_id = m.id"
                    " WHERE t.transaction_type::text = 'transfer_out'"
                    " AND (t.related_transaction_id IS NULL OR m.id IS NULL)"
                )
            ).fetchall()

            log.append(f"Found {len(rows)} unmirrored transfer_out")

            if not rows:
                sync_engine.dispose()
                return {"status": "ok", "log": log}

            # Clear broken related_transaction_id references before creating mirrors
            for r in rows:
                conn.execute(
                    text("UPDATE transactions SET related_transaction_id = NULL WHERE id = :tid"),
                    {"tid": r.id},
                )

            asset_cache = {}
            mirrors_created = 0
            for r in rows:
                key = (str(r.portfolio_id), r.symbol, DEFAULT_DESTINATION)
                if key not in asset_cache:
                    existing = conn.execute(
                        text(
                            "SELECT id FROM assets WHERE portfolio_id = :pid" " AND symbol = :sym AND exchange = :exc"
                        ),
                        {"pid": r.portfolio_id, "sym": r.symbol, "exc": DEFAULT_DESTINATION},
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
                        log.append(f"Created asset {r.symbol}/{DEFAULT_DESTINATION}")

                qty = float(r.quantity)
                fee = float(r.fee) if r.fee else 0
                fee_currency = (r.fee_currency or "").upper()
                if fee > 0 and (not fee_currency or fee_currency == r.symbol.upper()):
                    mirror_qty = qty - fee
                else:
                    mirror_qty = qty
                if mirror_qty <= 0:
                    log.append(f"Skip {r.symbol}: mirror_qty={mirror_qty}")
                    continue

                dest_asset_id = asset_cache[key]
                mirror_id = str(uuid_mod.uuid4())
                conn.execute(
                    text(
                        "INSERT INTO transactions (id, asset_id, transaction_type, quantity, price,"
                        " fee, currency, executed_at, exchange, notes, related_transaction_id)"
                        " VALUES (:id, :aid, 'transfer_in', :qty, :price, 0, :cur,"
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
                mirrors_created += 1
                log.append(f"Mirror {r.symbol} {mirror_qty} -> {DEFAULT_DESTINATION}")

            # Recalculate destination asset quantities
            for key, aid in asset_cache.items():
                net = conn.execute(
                    text(
                        "SELECT COALESCE(SUM(CASE"
                        " WHEN transaction_type::text IN"
                        " ('buy','conversion_in','transfer_in','airdrop','staking_reward','dividend','interest')"
                        " THEN quantity ELSE 0 END), 0)"
                        " - COALESCE(SUM(CASE"
                        " WHEN transaction_type::text IN ('sell','transfer_out','conversion_out','fee')"
                        " THEN quantity ELSE 0 END), 0) AS net_qty"
                        " FROM transactions WHERE asset_id = :aid"
                    ),
                    {"aid": aid},
                ).fetchone()
                final_qty = max(0, float(net.net_qty)) if net else 0
                conn.execute(
                    text("UPDATE assets SET quantity = :qty WHERE id = :aid"),
                    {"qty": final_qty, "aid": aid},
                )
                log.append(f"Asset {key[1]}/{key[2]} qty={final_qty}")

        sync_engine.dispose()
        return {"status": "ok", "mirrors_created": mirrors_created, "log": log}
    except Exception as e:
        return {"status": "error", "message": str(e), "traceback": tb_mod.format_exc()}


@app.get("/health")
@app.get("/api/v1/health")
async def health_check():
    """Liveness probe — returns 200 if the process is running."""
    return {"app": settings.APP_NAME, "status": "alive"}


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
