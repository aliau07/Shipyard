from django.urls import path

from . import views

urlpatterns = [
    path('auth/token/', views.LoginView.as_view(), name='auth-token'),
    path('auth/register/', views.RegisterView.as_view(), name='auth-register'),
    path('auth/logout/', views.LogoutView.as_view(), name='auth-logout'),
    path('auth/me/', views.MeView.as_view(), name='auth-me'),
]
