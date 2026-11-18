"""System-level endpoints: health and session authentication.

Authentication uses Django's built-in User model and session framework only.
No custom user table or public registration exists.
"""

from django.contrib.auth import authenticate, get_user_model, login, logout
from django.db import connection
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.contrib.auth import update_session_auth_hash
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework import generics, status
from rest_framework.authentication import SessionAuthentication
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny, BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .activity import log_activity, log_activity_safe
from .serializers import (
    ActivityLogDetailSerializer,
    ActivityLogSerializer,
    LoginSerializer,
    ManagedUserCreateSerializer,
    ManagedUserPasswordResetSerializer,
    ManagedUserUpdateSerializer,
)
from .models import ActivityLog, UserPasswordChangeAudit

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
            # Record the failed attempt independently; never store the password.
            log_activity_safe(
                actor=None,
                action="login_failed",
                module=ActivityLog.Module.AUTH,
                description="تلاش ناموفق برای ورود به سیستم.",
                target_type="user",
                target_label=serializer.validated_data["username"],
                metadata={"username": serializer.validated_data["username"]},
                status=ActivityLog.Status.FAILURE,
                request=request,
            )
            return Response(
                {"detail": "نام کاربری یا رمز عبور نادرست است."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        login(request, user)
        log_activity_safe(
            actor=user,
            action="login",
            module=ActivityLog.Module.AUTH,
            description="ورود موفق به سیستم.",
            target_type="user",
            target_id=user.pk,
            target_label=user.get_username(),
            request=request,
        )
        return Response(user_payload(user))


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        log_activity_safe(
            actor=user,
            action="logout",
            module=ActivityLog.Module.AUTH,
            description="خروج از سیستم.",
            target_type="user",
            target_id=user.pk,
            target_label=user.get_username(),
            request=request,
        )
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
        with transaction.atomic():
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
            # Log inside the transaction: a failed operation leaves no entry,
            # and the password is never part of the payload.
            log_activity(
                actor=request.user,
                action="user_create",
                module=ActivityLog.Module.USERS,
                description=f"ایجاد کاربر «{user.get_username()}».",
                target_type="user",
                target_id=user.pk,
                target_label=user.get_username(),
                after_data={
                    "username": user.get_username(),
                    "full_name": user.get_full_name(),
                    "role": "admin" if user.is_staff else "guest",
                    "is_active": user.is_active,
                },
                request=request,
            )
        return Response(managed_user_payload(user), status=status.HTTP_201_CREATED)


class UserManagementDetailView(APIView):
    """Edit or deactivate a non-superuser account."""

    permission_classes = [IsSuperuser]

    def patch(self, request, pk):
        user = get_object_or_404(get_user_model(), pk=pk)
        if user.is_superuser:
            log_activity_safe(
                actor=request.user,
                action="user_edit_denied",
                module=ActivityLog.Module.USERS,
                description="تلاش برای ویرایش حساب Superuser از مسیر مدیریت کاربران.",
                target_type="user",
                target_id=user.pk,
                target_label=user.get_username(),
                status=ActivityLog.Status.FAILURE,
                request=request,
            )
            return Response(
                {"detail": "ویرایش حساب Superuser از این مسیر مجاز نیست."},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = ManagedUserUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        updated_fields = []

        def role_of(account):
            if account.is_superuser:
                return "superuser"
            return "admin" if account.is_staff else "guest"

        before = {
            "full_name": user.get_full_name(),
            "role": role_of(user),
            "is_active": user.is_active,
        }

        if "full_name" in data:
            first_name, *last_name_parts = data["full_name"].split(None, 1)
            user.first_name = first_name
            user.last_name = last_name_parts[0] if last_name_parts else ""
            updated_fields.extend(("first_name", "last_name"))
        if "role" in data:
            user.is_staff = data["role"] == "admin"
            updated_fields.append("is_staff")
        if "is_active" in data:
            user.is_active = data["is_active"]
            updated_fields.append("is_active")

        with transaction.atomic():
            user.save(update_fields=updated_fields)
            after = {
                "full_name": user.get_full_name(),
                "role": role_of(user),
                "is_active": user.is_active,
            }
            log_activity(
                actor=request.user,
                action="user_update",
                module=ActivityLog.Module.USERS,
                description=f"ویرایش کاربر «{user.get_username()}».",
                target_type="user",
                target_id=user.pk,
                target_label=user.get_username(),
                before_data=before,
                after_data=after,
                metadata={"changed_fields": updated_fields},
                request=request,
            )
        return Response(managed_user_payload(user))


class UserPasswordResetView(APIView):
    permission_classes = [IsSuperuser]

    def post(self, request, pk):
        user = get_object_or_404(get_user_model(), pk=pk)
        serializer = ManagedUserPasswordResetSerializer(
            data=request.data,
            context={"user": user},
        )
        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            user.set_password(serializer.validated_data["new_password"])
            user.save(update_fields=["password"])
            UserPasswordChangeAudit.objects.create(
                actor=request.user,
                actor_username=request.user.get_username(),
                target=user,
                target_username=user.get_username(),
            )
            # The new password is never persisted; only the fact of the change.
            log_activity(
                actor=request.user,
                action="user_password_set",
                module=ActivityLog.Module.USERS,
                description=f"تعیین رمز عبور جدید برای کاربر «{user.get_username()}».",
                target_type="user",
                target_id=user.pk,
                target_label=user.get_username(),
                metadata={"password_changed": True},
                request=request,
            )

        if user.pk == request.user.pk:
            update_session_auth_hash(request, user)

        return Response({"detail": "رمز عبور با موفقیت تغییر کرد."})


class ActivityLogPagination(PageNumberPagination):
    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 100


class ActivityLogListView(generics.ListAPIView):
    """Read-only, Superuser-only listing of the activity audit trail.

    There is deliberately no create/update/delete endpoint here: the trail is
    append-only and grows only from trusted backend code.
    """

    permission_classes = [IsSuperuser]
    serializer_class = ActivityLogSerializer
    pagination_class = ActivityLogPagination
    # Read-only surface: never expose write verbs.
    http_method_names = ["get", "head", "options"]

    def get_queryset(self):
        queryset = ActivityLog.objects.all()
        params = self.request.query_params

        actor = params.get("actor", "").strip()
        if actor:
            queryset = queryset.filter(actor_username__iexact=actor)

        action = params.get("action", "").strip()
        if action:
            queryset = queryset.filter(action=action)

        module = params.get("module", "").strip()
        if module:
            queryset = queryset.filter(module=module)

        status_filter = params.get("status", "").strip()
        if status_filter in ActivityLog.Status.values:
            queryset = queryset.filter(status=status_filter)

        date_from = params.get("date_from", "").strip()
        if date_from:
            queryset = queryset.filter(timestamp__date__gte=date_from)

        date_to = params.get("date_to", "").strip()
        if date_to:
            queryset = queryset.filter(timestamp__date__lte=date_to)

        search = params.get("search", "").strip()
        if search:
            queryset = queryset.filter(
                Q(actor_username__icontains=search)
                | Q(target_id__icontains=search)
                | Q(target_label__icontains=search)
                | Q(description__icontains=search)
            )

        return queryset


class ActivityLogDetailView(generics.RetrieveAPIView):
    permission_classes = [IsSuperuser]
    serializer_class = ActivityLogDetailSerializer
    queryset = ActivityLog.objects.all()
    http_method_names = ["get", "head", "options"]


class ActivityLogFilterOptionsView(APIView):
    """Distinct module/action values, to populate the frontend filters."""

    permission_classes = [IsSuperuser]

    def get(self, request):
        actions = (
            ActivityLog.objects.values_list("action", flat=True)
            .distinct()
            .order_by("action")
        )
        actors = (
            ActivityLog.objects.values_list("actor_username", flat=True)
            .distinct()
            .order_by("actor_username")
        )
        return Response(
            {
                "modules": [
                    {"value": value, "label": label}
                    for value, label in ActivityLog.Module.choices
                ],
                "actions": [action for action in actions if action],
                "actors": [actor for actor in actors if actor],
            }
        )
