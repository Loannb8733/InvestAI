from app.core.db.base import Base
from app.domains.exchanges import models as exchange_models
from app.domains.identity import models as identity_models
from app.domains.journal import models as journal_models
from app.domains.market_data.fx import models as fx_models
from app.domains.market_data.history import models as history_models
from app.domains.portfolio import models as portfolio_models
from app.domains.predictions import models as prediction_models
from app.domains.strategies import models as strategy_models
from app.domains.transactions import models as transaction_models
from app.models import (
    alert,
    audit_log,
    calendar_event,
    crowdfunding_payment_schedule,
    crowdfunding_project,
    crowdfunding_repayment,
    goal,
    notification,
    planned_order,
    portfolio_snapshot,
    project_audit,
    project_document,
    simulation,
)

metadata = Base.metadata

__all__ = [
    "alert",
    "audit_log",
    "calendar_event",
    "crowdfunding_payment_schedule",
    "crowdfunding_project",
    "crowdfunding_repayment",
    "exchange_models",
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
    "prediction_models",
    "project_audit",
    "project_document",
    "simulation",
    "strategy_models",
    "transaction_models",
]
