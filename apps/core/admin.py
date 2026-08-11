"""
Registers a single extra page, /admin/dashboard/, on top of the default
Django admin - a quick "what needs attention right now" view (pending/
WhatsApp orders, today's revenue, site traffic) instead of digging through
several changelists. Patches admin.site.get_urls() rather than subclassing
AdminSite, so every existing @admin.register(...) call across the project
keeps working unchanged.
"""

from datetime import timedelta

from django.contrib import admin
from django.db.models import Count, Sum
from django.shortcuts import render
from django.urls import path
from django.utils import timezone

from apps.analytics.models import PageView
from apps.orders.models import Order, OrderStatus


def dashboard_view(request):
    now = timezone.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=7)

    pending_orders = Order.objects.filter(status=OrderStatus.PENDING).order_by("-created_at")
    whatsapp_orders = Order.objects.filter(status=OrderStatus.AWAITING_DETAILS).order_by("-created_at")

    revenue_today = Order.objects.filter(
        status=OrderStatus.CONFIRMED, created_at__gte=today_start,
    ).aggregate(total=Sum("total_amount"))["total"] or 0

    orders_today_count = Order.objects.filter(created_at__gte=today_start).count()

    pageviews_today = PageView.objects.filter(created_at__gte=today_start).count()
    visitors_today = PageView.objects.filter(created_at__gte=today_start).values("visitor_id").distinct().count()
    pageviews_week = PageView.objects.filter(created_at__gte=week_start).count()
    visitors_week = PageView.objects.filter(created_at__gte=week_start).values("visitor_id").distinct().count()

    top_paths = (
        PageView.objects.filter(created_at__gte=week_start)
        .values("path")
        .annotate(views=Count("id"))
        .order_by("-views")[:8]
    )

    context = {
        **admin.site.each_context(request),
        "title": "Dashboard",
        "pending_orders": pending_orders[:15],
        "pending_orders_count": pending_orders.count(),
        "whatsapp_orders": whatsapp_orders[:15],
        "whatsapp_orders_count": whatsapp_orders.count(),
        "revenue_today": revenue_today,
        "orders_today_count": orders_today_count,
        "pageviews_today": pageviews_today,
        "visitors_today": visitors_today,
        "pageviews_week": pageviews_week,
        "visitors_week": visitors_week,
        "top_paths": top_paths,
    }
    return render(request, "admin/dashboard.html", context)


admin.site.site_header = "RajwadiTukda admin"
admin.site.site_title = "RajwadiTukda admin"
admin.site.index_title = "Store administration"

_original_get_urls = admin.site.get_urls


def _get_urls():
    return [
        path("dashboard/", admin.site.admin_view(dashboard_view), name="dashboard"),
    ] + _original_get_urls()


admin.site.get_urls = _get_urls
