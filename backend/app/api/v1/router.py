"""API v1 router."""

from fastapi import APIRouter

from app.api.v1.endpoints import (
    alerts,
    calendar,
    cron,
    crowdfunding,
    dashboard,
    insights,
    notifications,
    smart_insights,
    system,
    telegram_webhook,
    websocket,
)
from app.domains.analytics.router import router as analytics_router
from app.domains.exchanges.router import keys_router, wallets_router
from app.domains.identity.admin_router import router as users_router
from app.domains.identity.router import router as auth_router
from app.domains.journal.router import router as journal_router
from app.domains.planning.goals.router import router as goals_router
from app.domains.planning.simulations.router import router as simulations_router
from app.domains.portfolio.router import assets_router, portfolios_router
from app.domains.predictions.router import router as predictions_router
from app.domains.reports.router import router as reports_router
from app.domains.strategies.router import router as strategies_router
from app.domains.transactions.router import router as transactions_router

api_router = APIRouter()

api_router.include_router(telegram_webhook.router, prefix="/bot", tags=["Telegram Bot"])
api_router.include_router(auth_router, prefix="/auth", tags=["Authentication"])
api_router.include_router(users_router, prefix="/users", tags=["Users"])
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["Dashboard"])
api_router.include_router(portfolios_router, prefix="/portfolios", tags=["Portfolios"])
api_router.include_router(assets_router, prefix="/assets", tags=["Assets"])
api_router.include_router(transactions_router, prefix="/transactions", tags=["Transactions"])
api_router.include_router(keys_router, prefix="/api-keys", tags=["API Keys"])
api_router.include_router(wallets_router, prefix="/cold-wallets", tags=["Cold Wallets"])
api_router.include_router(cron.router, prefix="/cron", tags=["Cron"])
api_router.include_router(analytics_router, prefix="/analytics", tags=["Analytics"])
api_router.include_router(predictions_router, prefix="/predictions", tags=["Predictions"])
api_router.include_router(alerts.router, prefix="/alerts", tags=["Alerts"])
api_router.include_router(reports_router, prefix="/reports", tags=["Reports"])
api_router.include_router(journal_router, prefix="/notes", tags=["Notes"])
api_router.include_router(calendar.router, prefix="/calendar", tags=["Calendar"])
api_router.include_router(simulations_router, prefix="/simulations", tags=["Simulations"])
api_router.include_router(notifications.router, prefix="/notifications", tags=["Notifications"])
api_router.include_router(insights.router, prefix="/insights", tags=["Insights"])
api_router.include_router(websocket.router, tags=["WebSocket"])
api_router.include_router(goals_router, prefix="/goals", tags=["Goals"])
api_router.include_router(smart_insights.router, prefix="/smart-insights", tags=["Smart Insights"])
api_router.include_router(crowdfunding.router, prefix="/crowdfunding", tags=["Crowdfunding"])
api_router.include_router(strategies_router, prefix="/strategies", tags=["Strategies"])
api_router.include_router(system.router, prefix="/system", tags=["System"])
