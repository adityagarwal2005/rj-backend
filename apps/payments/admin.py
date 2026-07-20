from django.contrib import admin

from apps.payments.models import Payment


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ["id", "order", "gateway", "status", "amount", "created_at"]
    list_editable = ["status"]
    list_filter = ["gateway", "status"]
    search_fields = ["id", "order__id"]
