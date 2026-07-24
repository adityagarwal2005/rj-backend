from django.urls import path

from apps.payments import views

urlpatterns = [
    path("details/", views.PaymentDetailsInfoView.as_view(), name="payment-details-info"),
    path("initiate/", views.InitiatePaymentView.as_view(), name="payment-initiate"),
    path("utr/", views.SubmitPaymentUtrView.as_view(), name="payment-submit-utr"),
    path("<uuid:id>/", views.PaymentDetailView.as_view(), name="payment-detail"),
    path("<uuid:id>/webhook/", views.PaymentWebhookView.as_view(), name="payment-webhook"),
    path("razorpay/webhook/", views.RazorpayServerWebhookView.as_view(), name="razorpay-server-webhook"),
]
