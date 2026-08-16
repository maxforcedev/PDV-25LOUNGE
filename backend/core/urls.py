"""
URL configuration for core project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import include, path

from apps.base.views import health

urlpatterns = [
    path('admin/', admin.site.urls),
    path('health/', health, name='health'),
    path('api/v1/', include('apps.base.urls')),
    path('api/v1/', include('apps.companies.urls')),
    path('api/v1/', include('apps.products.urls')),
    path('api/v1/', include('apps.inventory.urls')),
    path('api/v1/', include('apps.cash.urls')),
    path('api/v1/', include('apps.sales.urls')),
    path('api/v1/', include('apps.reports.urls')),
    path('api/v1/', include('apps.accounts.api_urls')),
    path('api/v1/auth/', include('apps.accounts.urls')),
]
