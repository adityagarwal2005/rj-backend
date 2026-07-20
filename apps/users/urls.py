from django.urls import path

from apps.users import views

urlpatterns = [
    path("register/", views.RegisterView.as_view(), name="auth-register"),
    path("login/", views.LoginView.as_view(), name="auth-login"),
    path("logout/", views.LogoutView.as_view(), name="auth-logout"),
    path("refresh/", views.RefreshTokenView.as_view(), name="auth-refresh"),
    path("profile/", views.ProfileView.as_view(), name="auth-profile"),
]
