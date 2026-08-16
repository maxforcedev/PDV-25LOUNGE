from rest_framework.routers import SimpleRouter

from .views import PaymentMethodViewSet, PromotionViewSet, SaleViewSet


router = SimpleRouter()
router.register('payment-methods', PaymentMethodViewSet, basename='payment-method')
router.register('promotions', PromotionViewSet, basename='promotion')
router.register('sales', SaleViewSet, basename='sale')

urlpatterns = router.urls
