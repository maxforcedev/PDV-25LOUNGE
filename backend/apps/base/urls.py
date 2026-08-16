from django.urls import path

from .views import api_root

app_name = 'base'

urlpatterns = [
    path('', api_root, name='api-root'),
]
