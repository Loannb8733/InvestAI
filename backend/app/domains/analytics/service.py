from app.domains.analytics.allocation import AnalyticsAllocation
from app.domains.analytics.correlation import AnalyticsCorrelation
from app.domains.analytics.monte_carlo import AnalyticsMonteCarlo
from app.domains.analytics.returns import AnalyticsReturns
from app.domains.analytics.stress import AnalyticsStress


class AnalyticsService(
    AnalyticsCorrelation,
    AnalyticsAllocation,
    AnalyticsMonteCarlo,
    AnalyticsReturns,
    AnalyticsStress,
):
    pass


analytics_service = AnalyticsService()
