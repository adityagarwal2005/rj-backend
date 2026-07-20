from rest_framework.permissions import BasePermission


class IsOrderOwnerOrAdmin(BasePermission):
    def has_object_permission(self, request, view, obj):
        return bool(request.user.is_admin or obj.user_id == request.user.id)
