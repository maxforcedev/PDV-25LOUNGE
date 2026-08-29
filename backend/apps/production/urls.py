from rest_framework.routers import SimpleRouter

from .views import PrintJobViewSet, PrinterDeviceViewSet, ProductionJobViewSet, TicketViewSet

router = SimpleRouter()
router.register('printer-devices', PrinterDeviceViewSet, basename='printer-device')
router.register('production-jobs', ProductionJobViewSet, basename='production-job')
router.register('print-jobs', PrintJobViewSet, basename='print-job')
router.register('tickets', TicketViewSet, basename='ticket')

urlpatterns = router.urls
