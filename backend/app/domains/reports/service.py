from app.domains.reports.data import ReportDataMixin
from app.domains.reports.rebalancing import RebalancingMixin
from app.domains.reports.tax import TaxMixin


class ReportService(ReportDataMixin, TaxMixin, RebalancingMixin):
    pass


report_service = ReportService()
