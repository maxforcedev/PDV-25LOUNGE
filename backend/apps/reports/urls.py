from django.urls import path

from .views import (
    CashReportView,
    CancellationsReportView,
    ConsumptionsReportView,
    DashboardView,
    InventoryMovementsReportView,
    OperationalResultReportView,
    ReportsOptionsView,
    SalesReportView,
    StockConsumptionReportView,
    WithdrawalsReportView,
)


urlpatterns = [
    path('dashboard/', DashboardView.as_view(), name='dashboard'),
    path('reports/sales/', SalesReportView.as_view(), name='report-sales'),
    path('reports/cancellations/', CancellationsReportView.as_view(), name='report-cancellations'),
    path(
        'reports/operational-result/',
        OperationalResultReportView.as_view(),
        name='report-operational-result',
    ),
    path('reports/options/', ReportsOptionsView.as_view(), name='report-options'),
    path('reports/consumptions/', ConsumptionsReportView.as_view(), name='report-consumptions'),
    path('reports/cash/', CashReportView.as_view(), name='report-cash'),
    path('reports/withdrawals/', WithdrawalsReportView.as_view(), name='report-withdrawals'),
    path(
        'reports/inventory-movements/',
        InventoryMovementsReportView.as_view(),
        name='report-inventory-movements',
    ),
    path(
        'reports/stock-consumption/',
        StockConsumptionReportView.as_view(),
        name='report-stock-consumption',
    ),
]
