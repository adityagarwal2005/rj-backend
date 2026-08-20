from django.urls import path

from apps.users import views

urlpatterns = [
    path("register/", views.RegisterView.as_view(), name="auth-register"),
    path("verify-email/", views.VerifyEmailView.as_view(), name="auth-verify-email"),
    path("resend-otp/", views.ResendOtpView.as_view(), name="auth-resend-otp"),
    path("login/", views.LoginView.as_view(), name="auth-login"),
    path("otp-login/request/", views.OtpLoginRequestView.as_view(), name="auth-otp-login-request"),
    path("otp-login/verify/", views.OtpLoginVerifyView.as_view(), name="auth-otp-login-verify"),
    path("password-reset/request/", views.PasswordResetRequestView.as_view(), name="auth-password-reset-request"),
    path("password-reset/confirm/", views.PasswordResetConfirmView.as_view(), name="auth-password-reset-confirm"),
    path("logout/", views.LogoutView.as_view(), name="auth-logout"),
    path("refresh/", views.RefreshTokenView.as_view(), name="auth-refresh"),
    path("profile/", views.ProfileView.as_view(), name="auth-profile"),
    path("referrals/", views.ReferralSummaryView.as_view(), name="auth-referrals"),
]
