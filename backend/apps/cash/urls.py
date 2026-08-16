from rest_framework.routers import SimpleRouter

from .views import (
    CashBeneficiaryViewSet,
    CashMovementViewSet,
    CashRegisterViewSet,
    CashSessionViewSet,
)

router = SimpleRouter()
router.register('cash-registers', CashRegisterViewSet, basename='cash-register')
router.register('cash-sessions', CashSessionViewSet, basename='cash-session')
router.register('cash-movements', CashMovementViewSet, basename='cash-movement')
router.register(
    'cash-beneficiaries', CashBeneficiaryViewSet, basename='cash-beneficiary'
)

urlpatterns = router.urls
