from django.urls import path

from .views import (
    OwnerCancellationView,
    OwnerChangeRequestView,
    OwnerPaymentHistoryView,
    OwnerSubscriptionView,
    OwnerSupportHistoryView,
    PublicPlanVersionListView,
    PublicSettingsView,
    PublicSignupView,
)

urlpatterns = [
    path('public/plans/', PublicPlanVersionListView.as_view(), name='saas-public-plan-list'),
    path('public/settings/', PublicSettingsView.as_view(), name='saas-public-settings'),
    path('public/signup/', PublicSignupView.as_view(), name='saas-public-signup'),
    path('saas/owner/subscription/', OwnerSubscriptionView.as_view(), name='saas-owner-subscription'),
    path('saas/owner/payments/', OwnerPaymentHistoryView.as_view(), name='saas-owner-payments'),
    path('saas/owner/change-requests/', OwnerChangeRequestView.as_view(), name='saas-owner-change-requests'),
    path('saas/owner/cancel/', OwnerCancellationView.as_view(), name='saas-owner-cancel'),
    path('saas/owner/support-history/', OwnerSupportHistoryView.as_view(), name='saas-owner-support-history'),
]
