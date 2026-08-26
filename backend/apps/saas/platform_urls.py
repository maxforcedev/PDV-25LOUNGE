from django.urls import include, path
from rest_framework.routers import SimpleRouter

from .views import (
    CapabilityViewSet,
    PlanEntitlementViewSet,
    PlanVersionViewSet,
    PlanViewSet,
    PlatformDashboardView,
    PlatformLoginView,
    PlatformLogoutView,
    PlatformMeView,
    PlatformPaymentViewSet,
    PlatformSettingsView,
    PlatformSupportSessionViewSet,
    PlatformSubscriptionRequestViewSet,
    PlatformSubscriptionViewSet,
    PlatformTenantViewSet,
)

router = SimpleRouter()
router.register('tenants', PlatformTenantViewSet, basename='platform-tenant')
router.register('plans', PlanViewSet, basename='platform-plan')
router.register('plan-versions', PlanVersionViewSet, basename='platform-plan-version')
router.register('capabilities', CapabilityViewSet, basename='platform-capability')
router.register('entitlements', PlanEntitlementViewSet, basename='platform-entitlement')
router.register('payments', PlatformPaymentViewSet, basename='platform-payment')
router.register('subscriptions', PlatformSubscriptionViewSet, basename='platform-subscription')
router.register('support-sessions', PlatformSupportSessionViewSet, basename='platform-support-session')
router.register(
    'subscription-requests',
    PlatformSubscriptionRequestViewSet,
    basename='platform-subscription-request',
)

urlpatterns = [
    path('auth/login/', PlatformLoginView.as_view(), name='platform-login'),
    path('auth/logout/', PlatformLogoutView.as_view(), name='platform-logout'),
    path('auth/me/', PlatformMeView.as_view(), name='platform-me'),
    path('dashboard/', PlatformDashboardView.as_view(), name='platform-dashboard'),
    path('settings/', PlatformSettingsView.as_view(), name='platform-settings'),
    path('', include(router.urls)),
]
