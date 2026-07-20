"""
Business logic for the users app. Views stay thin: validate the request via
a serializer, delegate to a service function, return the response.
"""

from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from apps.users.models import User
from apps.users.serializers import UserSerializer


def register_user(validated_data: dict) -> User:
    password = validated_data.pop("password")
    validated_data["email"] = validated_data["email"].lower().strip()
    user = User(**validated_data)
    user.set_password(password)
    user.save()
    return user


def issue_tokens_for_user(user: User) -> dict:
    refresh = RefreshToken.for_user(user)
    refresh["role"] = user.role
    refresh["full_name"] = user.full_name
    return {
        "refresh": str(refresh),
        "access": str(refresh.access_token),
        "user": UserSerializer(user).data,
    }


def blacklist_refresh_token(refresh_token: str) -> None:
    try:
        token = RefreshToken(refresh_token)
        token.blacklist()
    except TokenError as exc:
        raise ValueError("Invalid or already blacklisted refresh token.") from exc
