from django.urls import path

from .views import (
    BootstrapView, HeartbeatView, OperatorLoginView, OperatorLogoutView, OperatorsView,
    PairingConfirmView, PairingIdentifyView, PairingRequestOtpView, PinConfirmView,
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
    path('heartbeat/', HeartbeatView.as_view(), name='heartbeat'),
    path('pin/confirm/', PinConfirmView.as_view(), name='pin-confirm'),
]
