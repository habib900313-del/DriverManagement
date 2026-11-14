"""Driver API views."""

import mimetypes
from pathlib import Path

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated

from apps.payments.permissions import IsManager, IsManagerOrReadOnly
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
        queryset = Driver.objects.all()
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
                return super().create(request, *args, **kwargs)
        except IntegrityError:
            return Response(
                {
                    "detail": "شماره مسلسل یا پلیت وارد شده قبلاً ثبت شده است.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )


class DriverDetailView(generics.RetrieveUpdateAPIView):
    queryset = Driver.objects.all()
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
        old_photo_name = instance.photo.name if instance.photo else None

        try:
            with transaction.atomic():
                response = super().update(request, *args, **kwargs)
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
        driver = get_object_or_404(Driver, pk=pk)
        new_status = request.data.get("status")

        if not isinstance(new_status, bool):
            return Response(
                {"status": ["مقدار وضعیت باید true (فعال) یا false (غیرفعال) باشد."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if driver.status != new_status:
            driver.status = new_status
            driver.save(update_fields=["status", "updated_at"])

        serializer = DriverSerializer(driver, context={"request": request})
        return Response(serializer.data)


class DriverStatsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        total = Driver.objects.count()
        active = Driver.objects.filter(status=True).count()
        recent = Driver.objects.order_by("-created_at", "-id")[:5]
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

    permission_classes = [IsAuthenticated]

    def get(self, request):
        code = normalize_driver_code(request.query_params.get("driver_code", ""))
        plate = normalize_plate_number(request.query_params.get("plate_number", ""))
        exclude = request.query_params.get("exclude", "").strip()

        queryset = Driver.objects.all()
        if exclude.isdigit():
            queryset = queryset.exclude(pk=int(exclude))

        result = {}
        if code:
            result["driver_code_taken"] = queryset.filter(
                driver_code__iexact=code
            ).exists()
        if plate:
            result["plate_number_taken"] = queryset.filter(
                plate_number__iexact=plate
            ).exists()
        return Response(result)


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
