"""Driver API views."""

import mimetypes
from pathlib import Path

from django.db import IntegrityError, OperationalError, transaction
from django.db.models import Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated

from apps.core.activity import log_activity
from apps.core.models import ActivityLog
from apps.payments.permissions import IsManager
from apps.payments.services import FinancialError
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import (
    Driver,
    normalize_digits,
    normalize_driver_code,
    normalize_plate_number,
)
from .serializers import DriverSerializer, DriverSummarySerializer

ORDERING_FIELDS = {
    "driver_code",
    "full_name",
    "plate_number",
    "registration_date",
    "fee_start_date",
    "status",
    "created_at",
    "updated_at",
}


def _driver_snapshot(driver):
    """Comparable, non-sensitive snapshot used for before/after logging."""
    return {
        "driver_code": driver.driver_code,
        "full_name": driver.full_name,
        "father_name": driver.father_name,
        "phone": driver.phone,
        "tazkira_number": driver.tazkira_number,
        "plate_number": driver.plate_number,
        "address": driver.address,
        "driver_type": driver.driver_type,
        "status": driver.status,
        "fee_start_date": driver.fee_start_date,
        "registration_date": driver.registration_date,
    }


def _driver_label(driver):
    return f"{driver.driver_code} — {driver.full_name}"


class DriverPageNumberPagination(PageNumberPagination):
    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 100


class DriverListCreateView(generics.ListCreateAPIView):
    serializer_class = DriverSerializer
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    pagination_class = DriverPageNumberPagination

    def get_permissions(self):
        if self.request.method in ("POST", "PUT", "PATCH", "DELETE"):
            return [IsManager()]
        return [IsAuthenticated()]

    def get_queryset(self):
        queryset = Driver.objects.filter(is_deleted=False)
        params = self.request.query_params

        search = params.get("search", "").strip()
        if search:
            normalized_plate = normalize_plate_number(search)
            normalized_code = normalize_driver_code(search)
            normalized_text = normalize_digits(search)
            queryset = queryset.filter(
                Q(full_name__icontains=search)
                | Q(driver_code__icontains=normalized_code)
                | Q(plate_number__icontains=normalized_plate)
                | Q(phone__icontains=normalized_text)
            )

        name = params.get("name", "").strip()
        if name:
            queryset = queryset.filter(full_name__icontains=name)

        plate = params.get("plate", "").strip()
        if plate:
            queryset = queryset.filter(
                plate_number__icontains=normalize_plate_number(plate)
            )

        code = params.get("code", "").strip()
        if code:
            queryset = queryset.filter(
                driver_code__icontains=normalize_driver_code(code)
            )

        status_filter = params.get("status", "").strip().lower()
        if status_filter in {"active", "true", "1"}:
            queryset = queryset.filter(status=True)
        elif status_filter in {"inactive", "false", "0"}:
            queryset = queryset.filter(status=False)

        driver_type = params.get("driver_type", "").strip()
        if driver_type in ("guaranteed", "online"):
            queryset = queryset.filter(driver_type=driver_type)

        ordering = params.get("ordering", "").strip()
        if ordering:
            field_name = ordering.lstrip("-")
            if field_name in ORDERING_FIELDS:
                queryset = queryset.order_by(ordering, "-id")

        return queryset

    def create(self, request, *args, **kwargs):
        try:
            with transaction.atomic():
                response = super().create(request, *args, **kwargs)
                new_id = response.data.get("id") if hasattr(response.data, "get") else None
                if new_id is not None:
                    driver = Driver.objects.get(pk=new_id)
                    log_activity(
                        actor=request.user,
                        action="driver_create",
                        module=ActivityLog.Module.DRIVERS,
                        description=f"ایجاد راننده «{driver.full_name}».",
                        target_type="driver",
                        target_id=driver.pk,
                        target_label=_driver_label(driver),
                        after_data=_driver_snapshot(driver),
                        request=request,
                    )
                return response
        except FinancialError as exc:
            return Response(
                {"detail": exc.detail, "code": exc.code},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except IntegrityError:
            return Response(
                {
                    "detail": "شماره مسلسل یا پلیت وارد شده قبلاً ثبت شده است.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        except OperationalError:
            return Response(
                {"detail": "دیتابیس موقتاً قفل است؛ لطفاً دوباره تلاش کنید."},
                status=status.HTTP_409_CONFLICT,
            )


class DriverDetailView(generics.RetrieveUpdateAPIView):
    queryset = Driver.objects.filter(is_deleted=False)
    serializer_class = DriverSerializer
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    # Permanent deletion is intentionally unavailable: deactivate instead.
    http_method_names = ["get", "put", "patch", "head", "options"]

    def get_permissions(self):
        if self.request.method in ("POST", "PUT", "PATCH", "DELETE"):
            return [IsManager()]
        return [IsAuthenticated()]

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        old_photo_name = None

        try:
            with transaction.atomic():
                instance = get_object_or_404(
                    Driver.objects.select_for_update(),
                    pk=instance.pk,
                    is_deleted=False,
                )
                old_photo_name = instance.photo.name if instance.photo else None
                before = _driver_snapshot(instance)
                response = super().update(request, *args, **kwargs)
                instance.refresh_from_db()
                log_activity(
                    actor=request.user,
                    action="driver_update",
                    module=ActivityLog.Module.DRIVERS,
                    description=f"ویرایش اطلاعات راننده «{instance.full_name}».",
                    target_type="driver",
                    target_id=instance.pk,
                    target_label=_driver_label(instance),
                    before_data=before,
                    after_data=_driver_snapshot(instance),
                    request=request,
                )
        except IntegrityError:
            return Response(
                {
                    "detail": "شماره مسلسل یا پلیت وارد شده قبلاً ثبت شده است.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        instance.refresh_from_db()
        new_photo_name = instance.photo.name if instance.photo else None
        if old_photo_name and new_photo_name and old_photo_name != new_photo_name:
            # Remove the replaced file only after the database write succeeded.
            try:
                instance.photo.storage.delete(old_photo_name)
            except OSError:
                pass

        return response


class DriverStatusView(APIView):
    """Activate or deactivate a driver. Deletion is never offered."""

    permission_classes = [IsManager]

    def post(self, request, pk):
        driver = get_object_or_404(Driver, pk=pk, is_deleted=False)
        new_status = request.data.get("status")

        if not isinstance(new_status, bool):
            return Response(
                {"status": ["مقدار وضعیت باید true (فعال) یا false (غیرفعال) باشد."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            driver = get_object_or_404(
                Driver.objects.select_for_update(),
                pk=driver.pk,
                is_deleted=False,
            )
            if driver.status != new_status:
                old_status = driver.status
                driver.status = new_status
                driver.save(update_fields=["status", "updated_at"])
                log_activity(
                    actor=request.user,
                    action="driver_activate" if new_status else "driver_deactivate",
                    module=ActivityLog.Module.DRIVERS,
                    description=(
                        f"{'فعال‌سازی' if new_status else 'غیرفعال‌سازی'} راننده "
                        f"«{driver.full_name}»."
                    ),
                    target_type="driver",
                    target_id=driver.pk,
                    target_label=_driver_label(driver),
                    before_data={"status": old_status},
                    after_data={"status": new_status},
                    request=request,
                )

        serializer = DriverSerializer(driver, context={"request": request})
        return Response(serializer.data)


class DriverStatsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        drivers = Driver.objects.filter(is_deleted=False)
        total = drivers.count()
        active = drivers.filter(status=True).count()
        recent = drivers.order_by("-created_at", "-id")[:5]
        return Response(
            {
                "total": total,
                "active": active,
                "inactive": total - active,
                "recent": DriverSummarySerializer(
                    recent, many=True, context={"request": request}
                ).data,
            }
        )


class DriverUniqueCheckView(APIView):
    """Debounced availability check used by the create/edit forms."""

    permission_classes = [IsManager]

    def get(self, request):
        code = normalize_driver_code(request.query_params.get("driver_code", ""))
        plate = normalize_plate_number(request.query_params.get("plate_number", ""))
        exclude = request.query_params.get("exclude", "").strip()

        active_drivers = Driver.objects.filter(is_deleted=False)
        all_drivers = Driver.objects.all()
        if exclude.isdigit():
            active_drivers = active_drivers.exclude(pk=int(exclude))
            all_drivers = all_drivers.exclude(pk=int(exclude))

        result = {}
        if code:
            result["driver_code_taken"] = active_drivers.filter(
                driver_code__iexact=code
            ).exists()
        if plate:
            result["plate_number_taken"] = all_drivers.filter(
                plate_number__iexact=plate
            ).exists()
        return Response(result)


class ArchivedDriverListView(generics.ListAPIView):
    serializer_class = DriverSerializer
    permission_classes = [IsManager]
    pagination_class = DriverPageNumberPagination

    def get_queryset(self):
        return Driver.objects.filter(is_deleted=True).order_by(
            "-deleted_at", "-id"
        )


class DriverArchiveView(APIView):
    permission_classes = [IsManager]

    def post(self, request, pk):
        with transaction.atomic():
            driver = get_object_or_404(
                Driver.objects.select_for_update(),
                pk=pk,
                is_deleted=False,
            )
            driver.is_deleted = True
            driver.deleted_at = timezone.now()
            driver.save(
                update_fields=["is_deleted", "deleted_at", "updated_at"]
            )
            log_activity(
                actor=request.user,
                action="driver_archive",
                module=ActivityLog.Module.DRIVERS,
                description=f"آرشیف راننده «{driver.full_name}».",
                target_type="driver",
                target_id=driver.pk,
                target_label=_driver_label(driver),
                before_data={"is_deleted": False},
                after_data={"is_deleted": True},
                request=request,
            )
        return Response(DriverSerializer(driver, context={"request": request}).data)


class DriverRestoreView(APIView):
    permission_classes = [IsManager]

    def post(self, request, pk):
        try:
            with transaction.atomic():
                driver = get_object_or_404(
                    Driver.objects.select_for_update(),
                    pk=pk,
                    is_deleted=True,
                )
                code_in_use = Driver.objects.filter(
                    driver_code__iexact=driver.driver_code,
                    is_deleted=False,
                ).exclude(pk=driver.pk).exists()
                if code_in_use:
                    return Response(
                        {
                            "detail": (
                                f"شماره مسلسل «{driver.driver_code}» اکنون برای "
                                "راننده فعال دیگری استفاده می‌شود."
                            )
                        },
                        status=status.HTTP_409_CONFLICT,
                    )

                driver.is_deleted = False
                driver.deleted_at = None
                driver.save(
                    update_fields=["is_deleted", "deleted_at", "updated_at"]
                )
                log_activity(
                    actor=request.user,
                    action="driver_restore",
                    module=ActivityLog.Module.DRIVERS,
                    description=f"بازگردانی راننده «{driver.full_name}».",
                    target_type="driver",
                    target_id=driver.pk,
                    target_label=_driver_label(driver),
                    before_data={"is_deleted": True},
                    after_data={"is_deleted": False},
                    request=request,
                )
        except IntegrityError:
            return Response(
                {
                    "detail": (
                        "شماره مسلسل این راننده اکنون برای راننده فعال دیگری "
                        "استفاده می‌شود."
                    )
                },
                status=status.HTTP_409_CONFLICT,
            )
        return Response(DriverSerializer(driver, context={"request": request}).data)


class DriverPhotoView(APIView):
    """Authenticated photo delivery; media files are never served publicly."""

    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        driver = get_object_or_404(Driver, pk=pk)
        if not driver.photo:
            raise Http404("عکسی برای این راننده ثبت نشده است.")

        try:
            file_handle = driver.photo.open("rb")
        except (FileNotFoundError, OSError):
            raise Http404("فایل عکس در حافظه محلی یافت نشد.")

        content_type, _ = mimetypes.guess_type(driver.photo.name)
        response = FileResponse(
            file_handle,
            content_type=content_type or "application/octet-stream",
        )
        response["Content-Disposition"] = (
            f'inline; filename="{Path(driver.photo.name).name}"'
        )
        response["Cache-Control"] = "private, no-store"
        return response
