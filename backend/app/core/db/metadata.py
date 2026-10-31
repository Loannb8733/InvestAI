from app.core.db.base import Base
from app.domains.alerts import models as alert_models
from app.domains.calendar import models as calendar_models
from app.domains.crowdfunding import models as crowdfunding_models
from app.domains.crowdfunding.audit import models as audit_models
from app.domains.dashboard import models as dashboard_models
from app.domains.exchanges import models as exchange_models
from app.domains.identity import models as identity_models
from app.domains.journal import models as journal_models
from app.domains.market_data.fx import models as fx_models
from app.domains.market_data.history import models as history_models
from app.domains.notifications import models as notification_models
from app.domains.planning.goals import models as goal_models
from app.domains.planning.simulations import models as simulation_models
from app.domains.portfolio import models as portfolio_models
from app.domains.predictions import models as prediction_models
from app.domains.strategies import models as strategy_models
from app.domains.system import models as system_models
from app.domains.transactions import models as transaction_models

metadata = Base.metadata

__all__ = [
    "alert_models",
    "audit_models",
    "calendar_models",
    "crowdfunding_models",
    "dashboard_models",
    "exchange_models",
    "fx_models",
    "goal_models",
    "history_models",
    "identity_models",
    "journal_models",
    "metadata",
    "notification_models",
    "portfolio_models",
    "prediction_models",
    "simulation_models",
    "strategy_models",
    "system_models",
    "transaction_models",
]
