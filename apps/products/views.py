from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated

from apps.core.pagination import StandardResultsSetPagination
from apps.core.permissions import IsAdminOrReadOnly
from apps.core.response import api_error, api_success
from apps.products import services
from apps.products.filters import ProductFilter
from apps.products.models import Category, WishlistItem
from apps.products.serializers import (
    CategorySerializer,
    CreateReviewSerializer,
    ProductDetailSerializer,
    ProductImageSerializer,
    ProductListSerializer,
    ReviewSerializer,
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

    def get_serializer_context(self):
        context = super().get_serializer_context()
        user = self.request.user
        context["wishlisted_product_ids"] = (
            set(WishlistItem.objects.filter(user=user).values_list("product_id", flat=True))
            if user.is_authenticated
            else set()
        )
        return context

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

    @action(detail=True, methods=["get", "post"], url_path="reviews", permission_classes=[AllowAny])
    def reviews(self, request, slug=None):
        product = self.get_object()
        if request.method == "GET":
            queryset = product.reviews.select_related("user")
            page = self.paginate_queryset(queryset)
            serializer = ReviewSerializer(page if page is not None else queryset, many=True)
            if page is not None:
                return self.get_paginated_response(serializer.data)
            return api_success(serializer.data)

        if not request.user.is_authenticated:
            return api_error("You must be logged in to leave a review.", status=status.HTTP_401_UNAUTHORIZED)

        serializer = CreateReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            review = services.create_review(
                request.user,
                product,
                serializer.validated_data["order_id"],
                serializer.validated_data["rating"],
                serializer.validated_data.get("comment", ""),
            )
        except DjangoValidationError as exc:
            return api_error(str(exc.message) if hasattr(exc, "message") else str(exc), status=status.HTTP_400_BAD_REQUEST)
        return api_success(ReviewSerializer(review).data, message="Thanks for your review!", status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post", "delete"], url_path="wishlist", permission_classes=[IsAuthenticated])
    def wishlist(self, request, slug=None):
        product = self.get_object()
        if request.method == "POST":
            WishlistItem.objects.get_or_create(user=request.user, product=product)
            message = "Added to your wishlist."
        else:
            WishlistItem.objects.filter(user=request.user, product=product).delete()
            message = "Removed from your wishlist."
        return api_success(self.get_serializer(product).data, message=message)

    @action(detail=False, methods=["get"], url_path="wishlist", permission_classes=[IsAuthenticated])
    def my_wishlist(self, request):
        product_ids = WishlistItem.objects.filter(user=request.user).values_list("product_id", flat=True)
        # Preserve most-recently-wishlisted-first ordering rather than
        # falling back to the queryset's default (-created_at on Product).
        queryset = self.get_queryset().filter(id__in=product_ids)
        ordering = {product_id: index for index, product_id in enumerate(product_ids)}
        products = sorted(queryset, key=lambda product: ordering[product.id])
        page = self.paginate_queryset(products)
        serializer = ProductListSerializer(
            page if page is not None else products, many=True, context=self.get_serializer_context()
        )
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return api_success(serializer.data)
