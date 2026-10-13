from django.urls import path

from .views import (
    AttendanceCommandServiceFeeRegularizationView,
    AttendanceCommandFinancialRegularizationView,
    AttendanceCommandItemFinancialRegularizationView,
    AttendanceLegacyServiceFeeRegularizationsView,
)


urlpatterns = [
    path(
        'attendance-commands/legacy-service-fee-regularizations/',
        AttendanceLegacyServiceFeeRegularizationsView.as_view(),
        name='attendance-legacy-service-fee-regularizations',
    ),
    path(
        'attendance-commands/<int:command_id>/service-fee-regularization/',
        AttendanceCommandServiceFeeRegularizationView.as_view(),
        name='attendance-command-service-fee-regularization',
    ),
    path('attendance-commands/<int:command_id>/financial-regularization/', AttendanceCommandFinancialRegularizationView.as_view(), name='attendance-command-financial-regularization'),
    path('attendance-commands/<int:command_id>/item-financial-regularization/', AttendanceCommandItemFinancialRegularizationView.as_view(), name='attendance-command-item-financial-regularization'),
]
