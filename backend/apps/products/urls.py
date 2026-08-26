from rest_framework.routers import SimpleRouter

from .views import (
    BranchProductPriceViewSet, CategoryViewSet, ModifierGroupViewSet,
    ModifierOptionViewSet, ProductModifierGroupViewSet, ProductViewSet,
    ProductionDestinationViewSet,
)

router = SimpleRouter()
router.register('categories', CategoryViewSet, basename='category')
router.register('products', ProductViewSet, basename='product')
router.register('branch-prices', BranchProductPriceViewSet, basename='branchprice')
router.register('modifier-groups', ModifierGroupViewSet, basename='modifiergroup')
router.register('modifier-options', ModifierOptionViewSet, basename='modifieroption')
router.register('product-modifier-groups', ProductModifierGroupViewSet, basename='productmodifiergroup')
router.register(
    'production-destinations', ProductionDestinationViewSet,
    basename='productiondestination',
)

urlpatterns = router.urls
