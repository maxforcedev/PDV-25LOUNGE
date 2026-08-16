from rest_framework.routers import SimpleRouter

from .views import StockMovementViewSet, StockViewSet

router = SimpleRouter()
router.register('stocks', StockViewSet, basename='stock')
router.register('stock-movements', StockMovementViewSet, basename='stock-movement')

urlpatterns = router.urls
