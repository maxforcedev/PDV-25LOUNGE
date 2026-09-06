from django.urls import path
from rest_framework.routers import SimpleRouter

from .views import (
    BootstrapView, HeartbeatView, OperatorLoginView, OperatorLogoutView, OperatorsView,
    PairingConfirmView, PairingIdentifyView, PairingRequestOtpView, PinConfirmView,
    POSAdminDeviceViewSet, POSCashOverviewView, POSCashSessionCloseView,
    POSCashSessionEntryView, POSCashSessionOpenView, POSCashSessionSummaryView,
    POSCashSessionWithdrawalView,
)

app_name = 'pos'

urlpatterns = [
    path('pairing/identify/', PairingIdentifyView.as_view(), name='pairing-identify'),
    path('pairing/request-otp/', PairingRequestOtpView.as_view(), name='pairing-request-otp'),
    path('pairing/confirm/', PairingConfirmView.as_view(), name='pairing-confirm'),
    path('operators/', OperatorsView.as_view(), name='operators'),
    path('auth/operator/', OperatorLoginView.as_view(), name='operator-login'),
    path('auth/logout/', OperatorLogoutView.as_view(), name='operator-logout'),
    path('bootstrap/', BootstrapView.as_view(), name='bootstrap'),
    path('cash/overview/', POSCashOverviewView.as_view(), name='cash-overview'),
    path('cash/sessions/open/', POSCashSessionOpenView.as_view(), name='cash-session-open'),
    path('cash/sessions/<int:session_id>/summary/', POSCashSessionSummaryView.as_view(), name='cash-session-summary'),
    path('cash/sessions/<int:session_id>/entry/', POSCashSessionEntryView.as_view(), name='cash-session-entry'),
    path('cash/sessions/<int:session_id>/withdrawal/', POSCashSessionWithdrawalView.as_view(), name='cash-session-withdrawal'),
    path('cash/sessions/<int:session_id>/close/', POSCashSessionCloseView.as_view(), name='cash-session-close'),
    path('heartbeat/', HeartbeatView.as_view(), name='heartbeat'),
    path('pin/confirm/', PinConfirmView.as_view(), name='pin-confirm'),
]

router = SimpleRouter()
router.register('admin/devices', POSAdminDeviceViewSet, basename='pos-admin-device')
urlpatterns += router.urls
