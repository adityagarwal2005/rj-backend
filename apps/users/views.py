from rest_framework import generics, status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from apps.core.response import api_error, api_success
from apps.users import services
from apps.users.serializers import (
    LoginSerializer,
    LogoutSerializer,
    RegisterSerializer,
    UserSerializer,
)


class RegisterView(APIView):
    """POST /api/auth/register - create an account and log the user straight in."""

    permission_classes = [AllowAny]
    throttle_scope = "auth"

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = services.register_user(serializer.validated_data)
        tokens = services.issue_tokens_for_user(user)
        return api_success(tokens, message="Account created successfully.", status=status.HTTP_201_CREATED)


class LoginView(TokenObtainPairView):
    """POST /api/auth/login - exchange email/password for an access+refresh token pair."""

    permission_classes = [AllowAny]
    serializer_class = LoginSerializer
    throttle_scope = "auth"

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
        except ValidationError:
            return api_error("Invalid email or password.", status=status.HTTP_401_UNAUTHORIZED)
        return api_success(serializer.validated_data, message="Login successful.")


class RefreshTokenView(TokenRefreshView):
    """POST /api/auth/refresh - exchange a refresh token for a new access token."""

    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
        except (ValidationError, TokenError):
            return api_error("Refresh token is invalid or expired.", status=status.HTTP_401_UNAUTHORIZED)
        return api_success(serializer.validated_data, message="Token refreshed successfully.")


class LogoutView(APIView):
    """POST /api/auth/logout - blacklist the given refresh token."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            services.blacklist_refresh_token(serializer.validated_data["refresh"])
        except ValueError as exc:
            return api_error(str(exc), status=status.HTTP_400_BAD_REQUEST)
        return api_success(message="Logged out successfully.")


class ProfileView(generics.RetrieveUpdateAPIView):
    """GET/PUT/PATCH /api/auth/profile - the authenticated user's own profile."""

    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user

    def retrieve(self, request, *args, **kwargs):
        return api_success(self.get_serializer(self.get_object()).data)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return api_success(serializer.data, message="Profile updated successfully.")
