"""Permission classes for operational write access."""

from rest_framework.permissions import BasePermission


class IsManager(BasePermission):
    """Allow operational writes to Admin and Superuser accounts."""

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and (request.user.is_staff or request.user.is_superuser)
        )


class IsManagerOrReadOnly(BasePermission):
    """
    Manager permission for write operations; IsAuthenticated for read.
    """

    def has_permission(self, request, view):
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return bool(
                request.user and request.user.is_authenticated
            )
        return bool(
            request.user
            and request.user.is_authenticated
            and (request.user.is_staff or request.user.is_superuser)
        )