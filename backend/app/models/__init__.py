"""SQLAlchemy models."""

from sqlalchemy.orm import declarative_base

Base = declarative_base()

# Import all models so Base.metadata.create_all() picks them up
from app.models.user import User  # noqa: E402, F401
from app.models.portfolio import Portfolio  # noqa: E402, F401
from app.models.asset import Asset  # noqa: E402, F401
from app.models.transaction import Transaction  # noqa: E402, F401
from app.models.alert import Alert  # noqa: E402, F401
from app.models.notification import Notification  # noqa: E402, F401
from app.models.calendar_event import CalendarEvent  # noqa: E402, F401
from app.models.simulation import Simulation  # noqa: E402, F401
from app.models.goal import Goal  # noqa: E402, F401
from app.models.note import Note  # noqa: E402, F401
from app.models.api_key import APIKey  # noqa: E402, F401
from app.models.portfolio_snapshot import PortfolioSnapshot  # noqa: E402, F401
from app.models.prediction_log import PredictionLog  # noqa: E402, F401
