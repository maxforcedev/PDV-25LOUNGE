from django.urls import path
from rest_framework.routers import SimpleRouter

from .views import (
    BootstrapView, HeartbeatView, OperatorLoginView, OperatorLogoutView, OperatorPinResetView, OperatorsView,
    PairingConfirmView, PairingIdentifyView, PairingRequestOtpView, PinConfirmView,
    POSAdminDeviceViewSet, POSCashBeneficiariesView, POSCashOverviewView, POSCashSessionCloseView,
    POSCashSessionEntryView, POSCashSessionOpenView, POSCashSessionSummaryView,
    POSCashSessionWithdrawalView,
    POSBarcodeProductView, POSCatalogCategoriesView, POSCatalogView, POSFinalizeSaleView,
    POSCustomerActivateView, POSCustomersView, POSSaleAvailabilityView, POSSaleCheckoutOptionsView, POSSalePreviewView,
    POSDiscountAuthorizersView, POSDiscountAuthorizationValidationView,
    POSItemDiscountAuthorizersView, POSServiceFeeAuthorizersView,
    POSTicketLookupView, POSTicketValidateView,
)

app_name = 'pos'

urlpatterns = [
    path('pairing/identify/', PairingIdentifyView.as_view(), name='pairing-identify'),
    path('pairing/request-otp/', PairingRequestOtpView.as_view(), name='pairing-request-otp'),
    path('pairing/confirm/', PairingConfirmView.as_view(), name='pairing-confirm'),
    path('operators/', OperatorsView.as_view(), name='operators'),
    path('operators/<int:operator_id>/pin-reset/', OperatorPinResetView.as_view(), name='operator-pin-reset'),
    path('auth/operator/', OperatorLoginView.as_view(), name='operator-login'),
    path('auth/logout/', OperatorLogoutView.as_view(), name='operator-logout'),
    path('bootstrap/', BootstrapView.as_view(), name='bootstrap'),
    path('cash/overview/', POSCashOverviewView.as_view(), name='cash-overview'),
    path('cash/beneficiaries/', POSCashBeneficiariesView.as_view(), name='cash-beneficiaries'),
    path('cash/sessions/open/', POSCashSessionOpenView.as_view(), name='cash-session-open'),
    path('cash/sessions/<int:session_id>/summary/', POSCashSessionSummaryView.as_view(), name='cash-session-summary'),
    path('cash/sessions/<int:session_id>/entry/', POSCashSessionEntryView.as_view(), name='cash-session-entry'),
    path('cash/sessions/<int:session_id>/withdrawal/', POSCashSessionWithdrawalView.as_view(), name='cash-session-withdrawal'),
    path('cash/sessions/<int:session_id>/close/', POSCashSessionCloseView.as_view(), name='cash-session-close'),
    path('catalog/', POSCatalogView.as_view(), name='catalog'),
    path('catalog/categories/', POSCatalogCategoriesView.as_view(), name='catalog-categories'),
    path('products/barcode/<str:barcode>/', POSBarcodeProductView.as_view(), name='product-barcode'),
    path('customers/', POSCustomersView.as_view(), name='customers'),
    path('customers/<int:customer_id>/activate/', POSCustomerActivateView.as_view(), name='customer-activate'),
    path('sales/preview/', POSSalePreviewView.as_view(), name='sale-preview'),
    path('sales/availability/', POSSaleAvailabilityView.as_view(), name='sale-availability'),
    path('sales/discount-authorizers/', POSDiscountAuthorizersView.as_view(), name='sale-discount-authorizers'),
    path('sales/item-discount-authorizers/', POSItemDiscountAuthorizersView.as_view(), name='sale-item-discount-authorizers'),
    path('sales/service-fee-authorizers/', POSServiceFeeAuthorizersView.as_view(), name='sale-service-fee-authorizers'),
    path('sales/discount-authorizations/validate/', POSDiscountAuthorizationValidationView.as_view(), name='sale-discount-authorization-validate'),
    path('sales/checkout-options/', POSSaleCheckoutOptionsView.as_view(), name='sale-checkout-options'),
    path('sales/', POSFinalizeSaleView.as_view(), name='sale-finalize'),
    path('tickets/lookup/', POSTicketLookupView.as_view(), name='ticket-lookup'),
    path('tickets/validate/', POSTicketValidateView.as_view(), name='ticket-validate'),
    path('heartbeat/', HeartbeatView.as_view(), name='heartbeat'),
    path('pin/confirm/', PinConfirmView.as_view(), name='pin-confirm'),
]

router = SimpleRouter()
router.register('admin/devices', POSAdminDeviceViewSet, basename='pos-admin-device')
urlpatterns += router.urls
