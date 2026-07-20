"""
Shared, resource-agnostic permission classes.

App-specific ownership rules (e.g. "can only edit your own order") live in
each app's own permissions.py; only cross-cutting role checks belong here.
"""

from rest_framework.permissions import SAFE_METHODS, BasePermission


class IsAdmin(BasePermission):
    """Allows access only to users with the admin role."""

    message = "Only admin users can perform this action."

    def has_permission(self, request, view):
        return bool(
            request.user and request.user.is_authenticated and request.user.is_admin
        )


class IsAdminOrReadOnly(BasePermission):
    """Anyone can read (list/retrieve); only admins can write."""

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True
        return bool(
            request.user and request.user.is_authenticated and request.user.is_admin
        )


class IsOwnerOrAdmin(BasePermission):
    """Object-level check: the owning user or an admin may access it."""

    def has_object_permission(self, request, view, obj):
        owner_id = getattr(obj, "user_id", None)
        return bool(
            request.user.is_authenticated
            and (request.user.is_admin or owner_id == request.user.id)
        )
