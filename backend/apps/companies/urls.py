from rest_framework.routers import SimpleRouter

from .views import (
    AccessProfileViewSet,
    BranchViewSet,
    CompanyViewSet,
    FunctionalPermissionViewSet,
)

router = SimpleRouter()
router.register('companies', CompanyViewSet, basename='company')
router.register('branches', BranchViewSet, basename='branch')
router.register(
    'functional-permissions',
    FunctionalPermissionViewSet,
    basename='functional-permission',
)
router.register('access-profiles', AccessProfileViewSet, basename='access-profile')

urlpatterns = router.urls
