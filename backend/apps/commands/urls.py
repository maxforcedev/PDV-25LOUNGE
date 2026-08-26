from rest_framework.routers import SimpleRouter

from .views import CommandViewSet, OrderItemViewSet, TableViewSet

router = SimpleRouter()
router.register('tables', TableViewSet, basename='table')
router.register('commands', CommandViewSet, basename='command')
router.register('order-items', OrderItemViewSet, basename='orderitem')

urlpatterns = router.urls
