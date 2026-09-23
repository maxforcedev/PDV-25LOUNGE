from rest_framework.routers import SimpleRouter

from .views import (
    PrintDocumentViewSet, PrintJobViewSet, PrintRouteOverrideViewSet, PrintRouteViewSet,
    PrinterDeviceViewSet, ProductionJobViewSet, TicketViewSet,
)

router = SimpleRouter()
router.register('printer-devices', PrinterDeviceViewSet, basename='printer-device')
router.register('production-jobs', ProductionJobViewSet, basename='production-job')
router.register('print-jobs', PrintJobViewSet, basename='print-job')
router.register('print-documents', PrintDocumentViewSet, basename='print-document')
router.register('print-routes', PrintRouteViewSet, basename='print-route')
router.register('print-route-overrides', PrintRouteOverrideViewSet, basename='print-route-override')
router.register('tickets', TicketViewSet, basename='ticket')

urlpatterns = router.urls
