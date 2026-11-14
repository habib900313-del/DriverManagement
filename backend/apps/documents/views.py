"""Document API views (upload, list, download, deactivate)."""

import mimetypes
from pathlib import Path

from django.db import transaction
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.drivers.models import Driver
from apps.payments.permissions import IsManager
from .models import Document


class DocumentUploadView(APIView):
    """Upload one or more PDF documents for a driver."""

    permission_classes = [IsManager]
    parser_classes = [MultiPartParser]

    def post(self, request):
        driver_id = request.data.get("driver_id")
        if not driver_id:
            return Response(
                {"driver_id": ["شناسه راننده الزامی است."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            driver = Driver.objects.get(pk=driver_id)
        except Driver.DoesNotExist:
            return Response(
                {"driver_id": ["راننده یافت نشد."]},
                status=status.HTTP_404_NOT_FOUND,
            )

        uploaded_files = request.FILES.getlist("documents")
        if not uploaded_files:
            return Response(
                {"documents": ["فقط یک یا چند فایل PDF آپلود کنید."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        created = []
        with transaction.atomic():
            for upload_file in uploaded_files:
                doc = Document.objects.create(
                    driver=driver,
                    document_name=upload_file.name,
                    file=upload_file,
                    original_filename=upload_file.name,
                    file_size=upload_file.size,
                )
                created.append({
                    "id": doc.id,
                    "document_name": doc.document_name,
                    "original_filename": doc.original_filename,
                    "file_size_mb": round(doc.file_size / 1024 / 1024, 2) if doc.file_size else 0,
                    "upload_date": doc.upload_date,
                    "status": doc.status,
                })

        return Response(
            {
                "driver_id": driver.id,
                "documents": created,
            },
            status=status.HTTP_201_CREATED,
        )


class DocumentListView(APIView):
    """List documents for a driver."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        driver_id = request.query_params.get("driver_id")
        if not driver_id:
            return Response(
                {"driver_id": ["شناسه راننده الزامی است."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            driver = Driver.objects.get(pk=driver_id)
        except Driver.DoesNotExist:
            return Response(
                {"driver_id": ["راننده یافت نشد."]},
                status=status.HTTP_404_NOT_FOUND,
            )

        docs = Document.objects.filter(driver=driver, status="active")
        data = [
            {
                "id": doc.id,
                "document_name": doc.document_name,
                "original_filename": doc.original_filename,
                "file_size_mb": round(doc.file_size / 1024 / 1024, 2) if doc.file_size else 0,
                "upload_date": doc.upload_date,
                "description": doc.description,
                "status": doc.status,
            }
            for doc in docs
        ]
        return Response({"documents": data})


class DocumentDownloadView(APIView):
    """Securely download a document PDF."""

    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        doc = get_object_or_404(Document, pk=pk)
        if doc.status != "active":
            return Response(
                {"detail": "این سند غیرفعال است و قابل دانلود نیست."},
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            file_handle = doc.file.open("rb")
        except (FileNotFoundError, OSError):
            raise Http404("فایل سند در حافظه محلی یافت نشد.")

        content_type, _ = mimetypes.guess_type(doc.file.name)
        response = FileResponse(
            file_handle,
            content_type=content_type or "application/pdf",
        )
        response["Content-Disposition"] = (
            f'attachment; filename="{Path(doc.file.name).name}"'
        )
        response["Content-Disposition"] = (
            f'attachment; filename="{Path(doc.original_filename or doc.file.name).name}"'
        )
        response["Cache-Control"] = "private, no-store"
        return response


class DocumentDeactivateView(APIView):
    """Deactivate a document (soft delete)."""

    permission_classes = [IsManager]

    def post(self, request, pk):
        doc = get_object_or_404(Document, pk=pk)
        doc.status = "inactive"
        doc.save(update_fields=["status", "upload_date"])
        return Response(
            {
                "id": doc.id,
                "status": doc.status,
                "detail": "سند غیرفعال شد.",
            }
        )