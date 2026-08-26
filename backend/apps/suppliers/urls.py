from rest_framework.routers import SimpleRouter

from .views import (
    PresentationPresetViewSet, ProductSupplierUnitViewSet, ProductSupplierViewSet,
    SupplierViewSet,
)


router = SimpleRouter()
router.register('suppliers', SupplierViewSet, basename='supplier')
router.register('product-suppliers', ProductSupplierViewSet, basename='product-supplier')
router.register(
    'product-supplier-units', ProductSupplierUnitViewSet, basename='product-supplier-unit'
)
router.register('presentation-presets', PresentationPresetViewSet, basename='presentation-preset')

urlpatterns = router.urls
