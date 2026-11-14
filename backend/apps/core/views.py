"""System-level endpoints: health and session authentication.

Authentication uses Django's built-in User model and session framework only.
No custom user table or public registration exists.
"""

from django.contrib.auth import authenticate, get_user_model, login, logout
from django.db import connection
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import AllowAny, BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import LoginSerializer, ManagedUserCreateSerializer

API_VERSION = "0.1.0"


def user_payload(user):
    return {
        "id": user.pk,
        "username": user.username,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "display_name": user.get_full_name() or user.username,
        "is_staff": user.is_staff,
        "is_superuser": user.is_superuser,
    }


def managed_user_payload(user):
    """Safe, password-free representation for the user-management screen."""
    if user.is_superuser:
        role = "superuser"
    elif user.is_staff:
        role = "admin"
    else:
        role = "guest"
    return {
        "id": user.pk,
        "username": user.username,
        "full_name": user.get_full_name() or user.username,
        "role": role,
        "is_active": user.is_active,
    }


class IsSuperuser(BasePermission):
    """User administration is reserved for actual Django superusers."""

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.is_superuser
        )


class HealthView(APIView):
    """Lightweight readiness probe used by the frontend status card."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        database_ok = True
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
        except Exception:  # pragma: no cover - defensive
            database_ok = False

        return Response(
            {
                "status": "ok" if database_ok else "degraded",
                "service": "Driver Management API",
                "version": API_VERSION,
                "database": "ok" if database_ok else "unavailable",
                "timezone": timezone.get_current_timezone_name(),
                "server_time": timezone.localtime().isoformat(),
            }
        )


@method_decorator(ensure_csrf_cookie, name="get")
class CsrfView(APIView):
    """Sets the CSRF cookie so the SPA can authenticate with a session."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        return Response({"detail": "csrf cookie set"})


class LoginView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        # DRF marks APIViews as csrf_exempt; force CSRF validation on the
        # anonymous login endpoint explicitly.
        SessionAuthentication().enforce_csrf(request)

        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = authenticate(
            request=request,
            username=serializer.validated_data["username"],
            password=serializer.validated_data["password"],
        )
        if user is None:
            return Response(
                {"detail": "نام کاربری یا رمز عبور نادرست است."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        login(request, user)
        return Response(user_payload(user))


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        logout(request)
        return Response({"detail": "با موفقیت خارج شدید."})


class MeView(APIView):
    """Returns the current session user, or 401 for the SPA to redirect."""

    permission_classes = [AllowAny]

    def get(self, request):
        if not request.user.is_authenticated:
            return Response(
                {"detail": "برای دسترسی باید وارد شوید."},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        return Response(user_payload(request.user))


class UserManagementView(APIView):
    """List and create non-superuser accounts for local administration."""

    permission_classes = [IsSuperuser]

    def get(self, request):
        users = get_user_model().objects.order_by("username")
        return Response([managed_user_payload(user) for user in users])

    def post(self, request):
        serializer = ManagedUserCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        first_name, *last_name_parts = data["full_name"].split(None, 1)
        user = get_user_model().objects.create_user(
            username=data["username"],
            password=data["password"],
            first_name=first_name,
            last_name=last_name_parts[0] if last_name_parts else "",
            is_staff=data["role"] == "admin",
            # Never accept or derive superuser status from client input.
            is_superuser=False,
            is_active=True,
        )
        return Response(managed_user_payload(user), status=status.HTTP_201_CREATED)
