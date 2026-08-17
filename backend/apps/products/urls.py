from rest_framework.routers import SimpleRouter

from .views import BranchProductPriceViewSet, CategoryViewSet, ProductViewSet

router = SimpleRouter()
router.register('categories', CategoryViewSet, basename='category')
router.register('products', ProductViewSet, basename='product')
router.register('branch-prices', BranchProductPriceViewSet, basename='branchprice')

urlpatterns = router.urls
