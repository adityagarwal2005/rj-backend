from rest_framework.permissions import BasePermission


class IsProfileOwner(BasePermission):
    """A user may only view/edit their own profile."""

    def has_object_permission(self, request, view, obj):
        return obj.id == request.user.id
