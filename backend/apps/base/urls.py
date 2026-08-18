from django.urls import path
from rest_framework.routers import SimpleRouter

from .views import AuditLogViewSet, api_root

app_name = 'base'

router = SimpleRouter()
router.register('audit-logs', AuditLogViewSet, basename='audit-log')

urlpatterns = [
    path('', api_root, name='api-root'),
] + router.urls
