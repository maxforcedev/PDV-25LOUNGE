from django.urls import path

from .views import ChangePasswordView, CsrfView, LoginView, LogoutView, MeView, ProfilePhotoView

app_name = 'accounts'

urlpatterns = [
    path('csrf/', CsrfView.as_view(), name='csrf'),
    path('login/', LoginView.as_view(), name='login'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('me/', MeView.as_view(), name='me'),
    path('me/photo/', ProfilePhotoView.as_view(), name='profile-photo'),
    path('change-password/', ChangePasswordView.as_view(), name='change-password'),
]
