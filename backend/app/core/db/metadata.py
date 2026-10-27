from app.core.db.base import Base
from app.domains.alerts import models as alert_models
from app.domains.crowdfunding import models as crowdfunding_models
from app.domains.crowdfunding.audit import models as audit_models
from app.domains.exchanges import models as exchange_models
from app.domains.identity import models as identity_models
from app.domains.journal import models as journal_models
from app.domains.market_data.fx import models as fx_models
from app.domains.market_data.history import models as history_models
from app.domains.planning.goals import models as goal_models
from app.domains.planning.simulations import models as simulation_models
from app.domains.portfolio import models as portfolio_models
from app.domains.predictions import models as prediction_models
from app.domains.strategies import models as strategy_models
from app.domains.transactions import models as transaction_models
from app.models import (
    audit_log,
    calendar_event,
    notification,
    planned_order,
    portfolio_snapshot,
)

metadata = Base.metadata

__all__ = [
    "alert_models",
    "audit_log",
    "audit_models",
    "calendar_event",
    "crowdfunding_models",
    "exchange_models",
    "fx_models",
    "goal_models",
    "history_models",
    "identity_models",
    "journal_models",
    "metadata",
    "notification",
    "planned_order",
    "portfolio_models",
    "portfolio_snapshot",
    "prediction_models",
    "simulation_models",
    "strategy_models",
    "transaction_models",
]
