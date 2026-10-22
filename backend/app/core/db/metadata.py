from app.core.db.base import Base
from app.domains.identity import models as identity_models
from app.domains.journal import models as journal_models
from app.domains.market_data.fx import models as fx_models
from app.domains.market_data.history import models as history_models
from app.domains.portfolio import models as portfolio_models
from app.domains.transactions import models as transaction_models
from app.models import (
    alert,
    api_key,
    audit_log,
    calendar_event,
    cold_wallet_address,
    crowdfunding_payment_schedule,
    crowdfunding_project,
    crowdfunding_repayment,
    goal,
    notification,
    planned_order,
    portfolio_snapshot,
    prediction_log,
    project_audit,
    project_document,
    simulation,
    strategy,
)

metadata = Base.metadata

__all__ = [
    "alert",
    "api_key",
    "audit_log",
    "calendar_event",
    "cold_wallet_address",
    "crowdfunding_payment_schedule",
    "crowdfunding_project",
    "crowdfunding_repayment",
    "fx_models",
    "goal",
    "history_models",
    "identity_models",
    "journal_models",
    "metadata",
    "notification",
    "planned_order",
    "portfolio_models",
    "portfolio_snapshot",
    "prediction_log",
    "project_audit",
    "project_document",
    "simulation",
    "strategy",
    "transaction_models",
]
