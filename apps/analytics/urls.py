from django.urls import path

from apps.analytics import views

urlpatterns = [
    path("pageview/", views.PageViewCreateView.as_view(), name="pageview-create"),
]
