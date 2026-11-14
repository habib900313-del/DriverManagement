"""Financial permission classes.

IsManager: only users who are both staff AND superuser can perform
financial write operations. testadmin (is_staff=True, is_superuser=False)
is therefore NOT a manager and cannot perform financial write operations.
"""

from rest_framework.permissions import BasePermission


class IsManager(BasePermission):
    """
    Manager permission: requires both is_staff and is_superuser.
    testadmin (is_staff=True, is_superuser=False) is NOT a manager.
    """

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.is_staff
            and request.user.is_superuser
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
            and request.user.is_staff
            and request.user.is_superuser
        )