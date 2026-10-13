from django.urls import path

from .views import (
    AttendanceCommandServiceFeeRegularizationView,
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
]
