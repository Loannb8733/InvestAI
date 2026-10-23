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
