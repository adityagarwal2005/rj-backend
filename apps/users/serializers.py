from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from apps.users.models import User


class UserSerializer(serializers.ModelSerializer):
    """Read/update representation of the authenticated user's own profile."""

    class Meta:
        model = User
        fields = ["id", "email", "full_name", "phone", "role", "created_at"]
        read_only_fields = ["id", "email", "role", "created_at"]


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, validators=[validate_password])

    class Meta:
        model = User
        fields = ["id", "email", "full_name", "phone", "password"]
        read_only_fields = ["id"]

    def validate_email(self, value):
        value = value.lower().strip()
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("An account with this email already exists.")
        return value


class LoginSerializer(TokenObtainPairSerializer):
    """
    Extends simplejwt's serializer to embed the user's profile in the token
    response, so the frontend doesn't need a second round trip after login.
    """

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["role"] = user.role
        token["full_name"] = user.full_name
        return token

    def validate(self, attrs):
        data = super().validate(attrs)
        data["user"] = UserSerializer(self.user).data
        return data


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField()
