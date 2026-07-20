from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, MultiPartParser

from apps.core.pagination import StandardResultsSetPagination
from apps.core.permissions import IsAdminOrReadOnly
from apps.core.response import api_success
from apps.products import services
from apps.products.filters import ProductFilter
from apps.products.models import Category
from apps.products.serializers import (
    CategorySerializer,
    ProductDetailSerializer,
    ProductImageSerializer,
    ProductListSerializer,
)


class CategoryViewSet(viewsets.ModelViewSet):
    """
    /api/products/categories/       GET (public), POST (admin)
    /api/products/categories/{id}/  GET (public), PUT/PATCH/DELETE (admin)
    """

    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [IsAdminOrReadOnly]
    lookup_field = "slug"

    def get_queryset(self):
        if self.request.user.is_authenticated and self.request.user.is_admin:
            return Category.objects.all()
        return Category.objects.filter(is_active=True)

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        return response

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        return api_success(self.get_serializer(instance).data)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return api_success(serializer.data, message="Category created successfully.", status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return api_success(serializer.data, message="Category updated successfully.")

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.delete()
        return api_success(message="Category deleted successfully.", status=status.HTTP_200_OK)


class ProductViewSet(viewsets.ModelViewSet):
    """
    /api/products/                 GET (public), POST (admin)
    /api/products/{id}/            GET (public), PUT/PATCH/DELETE (admin)
    /api/products/{id}/images/     POST (admin) - upload a product image
    """

    permission_classes = [IsAdminOrReadOnly]
    pagination_class = StandardResultsSetPagination
    filterset_class = ProductFilter
    search_fields = ["name", "description"]
    ordering_fields = ["price", "created_at", "name"]
    lookup_field = "slug"

    def get_queryset(self):
        return services.visible_products_queryset(self.request.user)

    def get_serializer_class(self):
        if self.action == "list":
            return ProductListSerializer
        return ProductDetailSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return api_success(serializer.data, message="Product created successfully.", status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return api_success(serializer.data, message="Product updated successfully.")

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        return api_success(self.get_serializer(instance).data)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.delete()
        return api_success(message="Product deleted successfully.", status=status.HTTP_200_OK)

    @action(
        detail=True,
        methods=["post"],
        url_path="images",
        parser_classes=[MultiPartParser, FormParser],
        permission_classes=[IsAdminOrReadOnly],
    )
    def upload_image(self, request, slug=None):
        product = self.get_object()
        serializer = ProductImageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(product=product)
        return api_success(serializer.data, message="Image uploaded successfully.", status=status.HTTP_201_CREATED)
