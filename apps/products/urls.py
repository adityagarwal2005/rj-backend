from rest_framework.routers import DefaultRouter

from apps.products.views import CategoryViewSet, ProductViewSet

router = DefaultRouter()
router.register("categories", CategoryViewSet, basename="category")
router.register("", ProductViewSet, basename="product")

urlpatterns = router.urls
