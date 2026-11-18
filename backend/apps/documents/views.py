"""Document API views (upload, list, download, deactivate)."""

import logging
from pathlib import Path

from django.core.exceptions import ValidationError
from django.db import IntegrityError, OperationalError, transaction
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.activity import log_activity, log_activity_safe
from apps.core.models import ActivityLog
from apps.drivers.models import Driver
from apps.payments.permissions import IsManager
from .models import Document, validate_pdf_file

logger = logging.getLogger(__name__)
DOCUMENT_CONTENT_TYPES = {
    ".pdf": "application/pdf",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}


def _document_payload(document):
    filename = document.original_filename or document.file.name
    content_type = DOCUMENT_CONTENT_TYPES.get(
        Path(filename).suffix.lower(), "application/octet-stream"
    )
    return {
        "id": document.id,
        "document_name": document.document_name,
        "original_filename": document.original_filename,
        "content_type": content_type,
        "file_size_mb": round(document.file_size / 1024 / 1024, 2)
        if document.file_size
        else 0,
        "upload_date": document.upload_date,
        "description": document.description,
        "status": document.status,
    }


def _cleanup_uploaded_files(documents):
    for document in documents:
        if document.file and document.file.name:
            try:
                document.file.delete(save=False)
            except OSError:
                logger.exception("Could not remove a rolled-back document upload.")


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
        if not str(driver_id).isdigit():
            return Response(
                {"driver_id": ["شناسه راننده معتبر نیست."]},
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
                {"documents": ["یک یا چند فایل PDF یا تصویر معتبر آپلود کنید."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            for upload_file in uploaded_files:
                validate_pdf_file(upload_file)
        except ValidationError as exc:
            return Response(
                {"documents": exc.messages},
                status=status.HTTP_400_BAD_REQUEST,
            )

        created = []
        try:
            with transaction.atomic():
                for upload_file in uploaded_files:
                    doc = Document(
                        driver=driver,
                        document_name=upload_file.name,
                        file=upload_file,
                        original_filename=upload_file.name,
                        file_size=upload_file.size,
                    )
                    try:
                        doc.save()
                    except (IntegrityError, OSError):
                        if (
                            doc.file.name
                            and doc.file.name.startswith(
                                f"drivers/{driver.driver_code}/documents/"
                            )
                        ):
                            doc.file.delete(save=False)
                        raise
                    created.append(doc)
                log_activity(
                    actor=request.user,
                    action="document_upload",
                    module=ActivityLog.Module.DOCUMENTS,
                    description=(
                        f"آپلود {len(created)} سند برای راننده «{driver.full_name}»."
                    ),
                    target_type="document",
                    target_id=created[0].id if created else None,
                    target_label=f"{driver.driver_code} — {driver.full_name}",
                    after_data={
                        "documents": [
                            {
                                "document_name": document.document_name,
                                "original_filename": document.original_filename,
                                "file_size": document.file_size,
                            }
                            for document in created
                        ]
                    },
                    request=request,
                )
        except ValidationError as exc:
            _cleanup_uploaded_files(created)
            return Response(
                {"documents": exc.messages},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except IntegrityError:
            _cleanup_uploaded_files(created)
            return Response(
                {"detail": "ثبت اسناد انجام نشد؛ لطفاً دوباره تلاش کنید."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except OperationalError:
            _cleanup_uploaded_files(created)
            return Response(
                {"detail": "دیتابیس موقتاً قفل است؛ لطفاً دوباره تلاش کنید."},
                status=status.HTTP_409_CONFLICT,
            )
        except OSError:
            _cleanup_uploaded_files(created)
            return Response(
                {"detail": "ذخیره فایل در مسیر اسناد ممکن نشد."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(
            {
                "driver_id": driver.id,
                "documents": [_document_payload(document) for document in created],
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
        if not str(driver_id).isdigit():
            return Response(
                {"driver_id": ["شناسه راننده معتبر نیست."]},
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
        data = [_document_payload(document) for document in docs]
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

        filename = Path(doc.original_filename or doc.file.name).name
        content_type = DOCUMENT_CONTENT_TYPES.get(
            Path(filename).suffix.lower(), "application/octet-stream"
        )
        inline = (
            request.query_params.get("inline") == "1"
            and content_type in {
                "application/pdf",
                "image/jpeg",
                "image/png",
                "image/webp",
            }
        )
        # Sensitive-document access trail. Logged independently so a logging
        # failure never blocks a legitimate download.
        log_activity_safe(
            actor=request.user,
            action="document_view" if inline else "document_download",
            module=ActivityLog.Module.DOCUMENTS,
            description=(
                f"{'مشاهده' if inline else 'دانلود'} سند «{doc.document_name}»."
            ),
            target_type="document",
            target_id=doc.pk,
            target_label=doc.document_name,
            metadata={"driver_id": doc.driver_id, "filename": filename},
            request=request,
        )
        response = FileResponse(
            file_handle,
            as_attachment=not inline,
            filename=filename,
            content_type=content_type,
        )
        response["Cache-Control"] = "private, no-store"
        return response


class DocumentDeactivateView(APIView):
    """Deactivate a document (soft delete)."""

    permission_classes = [IsManager]

    def post(self, request, pk):
        doc = get_object_or_404(Document, pk=pk)
        with transaction.atomic():
            doc.status = "inactive"
            doc.save(update_fields=["status", "upload_date"])
            log_activity(
                actor=request.user,
                action="document_deactivate",
                module=ActivityLog.Module.DOCUMENTS,
                description=f"غیرفعال‌سازی سند «{doc.document_name}».",
                target_type="document",
                target_id=doc.pk,
                target_label=doc.document_name,
                before_data={"status": "active"},
                after_data={"status": "inactive"},
                metadata={"driver_id": doc.driver_id},
                request=request,
            )
        return Response(
            {
                "id": doc.id,
                "status": doc.status,
                "detail": "سند غیرفعال شد.",
            }
        )