from rest_framework.routers import SimpleRouter

from .views import (
    AccessProfileViewSet,
    BranchViewSet,
    CompanyViewSet,
    CustomerViewSet,
    FunctionalPermissionViewSet,
    UserCommissionOverrideViewSet,
    UserPermissionBlockViewSet,
)

router = SimpleRouter()
router.register('companies', CompanyViewSet, basename='company')
router.register('customers', CustomerViewSet, basename='customer')
router.register('branches', BranchViewSet, basename='branch')
router.register(
    'functional-permissions',
    FunctionalPermissionViewSet,
    basename='functional-permission',
)
router.register('access-profiles', AccessProfileViewSet, basename='access-profile')
router.register('user-permission-blocks', UserPermissionBlockViewSet, basename='user-permission-block')
router.register('user-commission-overrides', UserCommissionOverrideViewSet, basename='user-commission-override')

urlpatterns = router.urls
