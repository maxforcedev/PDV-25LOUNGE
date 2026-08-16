from rest_framework.routers import SimpleRouter

from .viewsets import UserViewSet

router = SimpleRouter()
router.register('users', UserViewSet, basename='user')

urlpatterns = router.urls
