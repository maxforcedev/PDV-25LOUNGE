from rest_framework.routers import SimpleRouter

from .views import (
    AdvancedInventoryReportViewSet,
    InventoryCountViewSet,
    LossRecordViewSet,
    StockMovementViewSet,
    StockTransferViewSet,
    StockViewSet,
    TransferDivergenceViewSet,
)

router = SimpleRouter()
router.register('stocks', StockViewSet, basename='stock')
router.register('stock-movements', StockMovementViewSet, basename='stock-movement')
router.register('stock-transfers', StockTransferViewSet, basename='stock-transfer')
router.register(
    'transfer-divergences', TransferDivergenceViewSet, basename='transfer-divergence'
)
router.register('loss-records', LossRecordViewSet, basename='loss-record')
router.register('inventory-counts', InventoryCountViewSet, basename='inventory-count')
router.register(
    'advanced-inventory-reports',
    AdvancedInventoryReportViewSet,
    basename='advanced-inventory-report',
)

urlpatterns = router.urls
