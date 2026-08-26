from rest_framework.routers import SimpleRouter

from .views import (
    PayableInstallmentViewSet,
    PurchaseOrderViewSet,
    PurchaseReceiptViewSet,
)


router = SimpleRouter()
router.register('purchase-orders', PurchaseOrderViewSet, basename='purchase-order')
router.register('purchase-receipts', PurchaseReceiptViewSet, basename='purchase-receipt')
router.register(
    'payable-installments', PayableInstallmentViewSet, basename='payable-installment'
)

urlpatterns = router.urls
