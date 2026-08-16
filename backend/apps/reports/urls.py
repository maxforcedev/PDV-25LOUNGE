from django.urls import path

from .views import (
    CashReportView,
    ConsumptionsReportView,
    DashboardView,
    InventoryMovementsReportView,
    ReportsOptionsView,
    SalesReportView,
    WithdrawalsReportView,
)


urlpatterns = [
    path('dashboard/', DashboardView.as_view(), name='dashboard'),
    path('reports/sales/', SalesReportView.as_view(), name='report-sales'),
    path('reports/options/', ReportsOptionsView.as_view(), name='report-options'),
    path('reports/consumptions/', ConsumptionsReportView.as_view(), name='report-consumptions'),
    path('reports/cash/', CashReportView.as_view(), name='report-cash'),
    path('reports/withdrawals/', WithdrawalsReportView.as_view(), name='report-withdrawals'),
    path(
        'reports/inventory-movements/',
        InventoryMovementsReportView.as_view(),
        name='report-inventory-movements',
    ),
]
