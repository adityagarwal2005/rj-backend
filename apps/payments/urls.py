from django.urls import path

from apps.payments import views

urlpatterns = [
    path("details/", views.PaymentDetailsInfoView.as_view(), name="payment-details-info"),
    path("initiate/", views.InitiatePaymentView.as_view(), name="payment-initiate"),
    path("<uuid:id>/", views.PaymentDetailView.as_view(), name="payment-detail"),
    path("<uuid:id>/webhook/", views.PaymentWebhookView.as_view(), name="payment-webhook"),
]
