"""API v1 router."""

from fastapi import APIRouter

from app.api.v1.endpoints import (
    auth,
    users,
    portfolios,
    assets,
    transactions,
    dashboard,
    api_keys,
    analytics,
    predictions,
    alerts,
    reports,
    notes,
    calendar,
    simulations,
    notifications,
    insights,
    websocket,
    goals,
    smart_insights,
    system,
)

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
api_router.include_router(users.router, prefix="/users", tags=["Users"])
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["Dashboard"])
api_router.include_router(portfolios.router, prefix="/portfolios", tags=["Portfolios"])
api_router.include_router(assets.router, prefix="/assets", tags=["Assets"])
api_router.include_router(
    transactions.router, prefix="/transactions", tags=["Transactions"]
)
api_router.include_router(api_keys.router, prefix="/api-keys", tags=["API Keys"])
api_router.include_router(analytics.router, prefix="/analytics", tags=["Analytics"])
api_router.include_router(predictions.router, prefix="/predictions", tags=["Predictions"])
api_router.include_router(alerts.router, prefix="/alerts", tags=["Alerts"])
api_router.include_router(reports.router, prefix="/reports", tags=["Reports"])
api_router.include_router(notes.router, prefix="/notes", tags=["Notes"])
api_router.include_router(calendar.router, prefix="/calendar", tags=["Calendar"])
api_router.include_router(simulations.router, prefix="/simulations", tags=["Simulations"])
api_router.include_router(
    notifications.router, prefix="/notifications", tags=["Notifications"]
)
api_router.include_router(insights.router, prefix="/insights", tags=["Insights"])
api_router.include_router(websocket.router, tags=["WebSocket"])
api_router.include_router(goals.router, prefix="/goals", tags=["Goals"])
api_router.include_router(
    smart_insights.router, prefix="/smart-insights", tags=["Smart Insights"]
)
api_router.include_router(system.router, prefix="/system", tags=["System"])
