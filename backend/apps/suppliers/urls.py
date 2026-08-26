from rest_framework.routers import SimpleRouter

from .views import ProductSupplierUnitViewSet, ProductSupplierViewSet, SupplierViewSet


router = SimpleRouter()
router.register('suppliers', SupplierViewSet, basename='supplier')
router.register('product-suppliers', ProductSupplierViewSet, basename='product-supplier')
router.register(
    'product-supplier-units', ProductSupplierUnitViewSet, basename='product-supplier-unit'
)

urlpatterns = router.urls
