import re
from decimal import Decimal
from pathlib import Path

from PIL import Image, UnidentifiedImageError
from django.db import transaction
from rest_framework import serializers

from .models import Driver, DriverFeeHistory
from apps.documents.models import Document, validate_pdf_file
from apps.payments.services import (
    FinancialError,
    lock_current_fee_schedule,
    receive_payment,
)
from apps.payments.periods import period_for_start
from .models import normalize_digits, normalize_driver_code, normalize_plate_number

MAX_PHOTO_SIZE = 5 * 1024 * 1024  # 5 MB
ALLOWED_PHOTO_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
ALLOWED_PHOTO_TYPES = {"image/jpeg", "image/png", "image/webp"}
ALLOWED_IMAGE_FORMATS = {"JPEG", "PNG", "WEBP"}


class DriverSerializer(serializers.ModelSerializer):
    photo = serializers.ImageField(
        write_only=True,
        required=False,
        allow_null=True,
        error_messages={
            "invalid_image": "فایل انتخاب‌شده یک تصویر معتبر نیست.",
        },
    )
    photo_url = serializers.SerializerMethodField()
    status_label = serializers.SerializerMethodField()
    documents = serializers.ListField(
        child=serializers.FileField(
            validators=[validate_pdf_file],
        ),
        write_only=True,
        required=False,
        allow_empty=True,
        help_text="یک یا چند فایل PDF یا تصویر (حداکثر ۱۰ مگابایت هر فایل)",
    )
    initial_payment_amount = serializers.DecimalField(
        max_digits=10,
        decimal_places=2,
        min_value=Decimal("0"),
        required=False,
        write_only=True,
    )
    initial_payment_date = serializers.DateField(required=False, write_only=True)
    initial_payment_period_start = serializers.DateField(
        required=False, write_only=True
    )
    initial_payment_idempotency_key = serializers.CharField(
        required=False, allow_blank=True, max_length=64, write_only=True
    )
    documents_list = serializers.SerializerMethodField()

    class Meta:
        model = Driver
        fields = [
            "id",
            "driver_code",
            "full_name",
            "father_name",
            "phone",
            "tazkira_number",
            "plate_number",
            "address",
            "photo",
            "photo_url",
            "registration_date",
            "fee_start_date",
            "status",
            "status_label",
            "driver_type",
            "is_deleted",
            "deleted_at",
            "created_at",
            "updated_at",
            "documents",
            "initial_payment_amount",
            "initial_payment_date",
            "initial_payment_period_start",
            "initial_payment_idempotency_key",
            "documents_list",
        ]
        read_only_fields = [
            "id",
            "is_deleted",
            "deleted_at",
            "created_at",
            "updated_at",
        ]
        extra_kwargs = {
            "driver_code": {
                "required": True,
                "allow_blank": False,
                "error_messages": {
                    "required": "شماره serial الزامی است.",
                    "blank": "شماره serial نمی‌تواند خالی باشد.",
                    "unique": "این شماره serial قبلاً برای راننده دیگری ثبت شده است.",
                },
            },
            "full_name": {
                "error_messages": {
                    "required": "نام کامل الزامی است.",
                    "blank": "نام کامل نمی‌تواند خالی باشد.",
                }
            },
            "father_name": {
                "required": False,
                "allow_blank": True,
                "allow_null": True,
                "error_messages": {
                    "blank": "نام پدر نمی‌تواند خالی باشد.",
                }
            },
            "phone": {
                "required": False,
                "allow_blank": True,
                "allow_null": True,
                "error_messages": {
                    "blank": "شماره تماس نمی‌تواند خالی باشد.",
                }
            },
            "tazkira_number": {
                "required": False,
                "allow_blank": True,
                "allow_null": True,
                "error_messages": {
                    "blank": "شماره تذکره نمی‌تواند خالی باشد.",
                }
            },
            "plate_number": {
                "required": True,
                "allow_blank": False,
                "error_messages": {
                    "required": "پلیت موتر الزامی است.",
                    "blank": "پلیت موتر نمی‌تواند خالی باشد.",
                    "unique": "این پلیت موتر قبلاً برای راننده دیگری ثبت شده است.",
                },
            },
            "address": {
                "required": False,
                "allow_blank": True,
                "allow_null": True,
                "error_messages": {
                    "blank": "آدرس اختیاری است."
                }
            },
            "fee_start_date": {
                "error_messages": {
                    "required": False,
                    "null": "تاریخ شروع فیس اختیاری است."
                }
            },
            "driver_type": {
                "required": False,
                "error_messages": {
                    "invalid": "نوع راننده نامعتبر است.",
                }
            },
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # D6/§10.3: writable on create, read-only on update — changes go
        # through POST /api/drivers/{id}/fee-start-date/ (W10) only.
        if self.instance is not None:
            self.fields["fee_start_date"].read_only = True
            # driver_type cannot be changed after creation without manager approval
            self.fields["driver_type"].read_only = True
            self.fields["documents"].read_only = True
            for field in (
                "initial_payment_amount",
                "initial_payment_date",
                "initial_payment_period_start",
                "initial_payment_idempotency_key",
            ):
                self.fields[field].read_only = True

    def create(self, validated_data):
        with transaction.atomic():
            lock_current_fee_schedule()
            documents = validated_data.pop("documents", [])
            initial_payment_amount = validated_data.pop(
                "initial_payment_amount", None
            )
            initial_payment_date = validated_data.pop("initial_payment_date", None)
            initial_period_start = validated_data.pop(
                "initial_payment_period_start", None
            )
            initial_payment_key = validated_data.pop(
                "initial_payment_idempotency_key", ""
            )
            driver = super().create(validated_data)
            request = self.context.get("request")
            # Only guaranteed drivers get a DriverFeeHistory entry (quarterly fee system)
            # Online drivers do not participate in the guaranteed fee system.
            if driver.driver_type == "guaranteed":
                DriverFeeHistory.objects.create(
                    driver=driver,
                    old_fee_start_date=None,
                    requested_fee_start_date=driver.fee_start_date,
                    effective_fee_start_date=driver.fee_start_date,
                    reason="ردیف اولیه — ایجاد راننده",
                    changed_by=request.user if request else None,
                )
            if initial_payment_amount and initial_payment_amount > 0:
                if driver.driver_type != "guaranteed":
                    raise FinancialError(
                        "فقط برای راننده‌های تضمینی مجاز است.",
                        "driver_not_guaranteed",
                    )
                target_period = (
                    period_for_start(driver, initial_period_start)
                    if initial_period_start is not None
                    else None
                )
                if target_period is None:
                    raise FinancialError(
                        "تاریخ شروع باید آغاز یکی از دوره‌های سه‌ماهه معتبر باشد.",
                        "unknown_period",
                    )
                receive_payment(
                    driver=driver,
                    amount=initial_payment_amount,
                    payment_date=initial_payment_date,
                    user=request.user,
                    target_period=target_period,
                    idempotency_key=initial_payment_key or None,
                )
            # Create document records for uploaded files.
            for upload_file in documents:
                Document.objects.create(
                    driver=driver,
                    document_name=upload_file.name,
                    file=upload_file,
                    original_filename=upload_file.name,
                    file_size=upload_file.size,
                )
            return driver

    def get_photo_url(self, obj):
        if not obj.photo:
            return None
        version = int(obj.updated_at.timestamp()) if obj.updated_at else 0
        return f"/api/drivers/{obj.pk}/photo/?v={version}"

    def get_status_label(self, obj):
        return "فعال" if obj.status else "غیرفعال"

    def get_documents_list(self, obj):
        """Return list of documents for this driver"""
        docs = Document.objects.filter(driver=obj, status='active')
        return [
            {
                "id": doc.id,
                "document_name": doc.document_name,
                "original_filename": doc.original_filename,
                "file_size_mb": round(doc.file_size / 1024 / 1024, 2) if doc.file_size else 0,
                "upload_date": doc.upload_date,
                "description": doc.description,
                "file": f"/api/documents/{doc.pk}/download/" if doc.file else None,
            }
            for doc in docs
        ]

    def _clean_required_text(self, value, label):
        value = (value or "").strip()
        if not value:
            raise serializers.ValidationError(f"{label} الزامی است.")
        return value

    def validate_driver_code(self, value):
        value = normalize_driver_code(value)
        if not value:
            raise serializers.ValidationError("شماره serialized الزامی est.")
        queryset = Driver.objects.filter(
            driver_code__iexact=value,
            is_deleted=False,
        )
        if self.instance is not None:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise serializers.ValidationError(
                "این شماره serialized قبلاً برای راننده دیگری signup est."
            )
        return value

    def validate_plate_number(self, value):
        value = normalize_plate_number(value)
        if not value:
            raise serializers.ValidationError("پlitaxel optional est.")
        queryset = Driver.objects.filter(plate_number__iexact=value)
        if self.instance is not None:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise serializers.ValidationError(
                "این پلی serialized serializedsignup est."
            )
        return value

    def validate_full_name(self, value):
        return self._clean_required_text(value, "نام کامل")

    def validate_father_name(self, value):
        value = (value or "").strip()
        if not value and self.instance is None:
            raise serializers.ValidationError("نام پدر الزامی است.")
        return value

    def validate_phone(self, value):
        value = normalize_digits(value or "").strip()
        if not value and self.instance is None:
            raise serializers.ValidationError("شماره تماس الزامی است.")
        if not value:
            return value
        if not re.fullmatch(r"[0-9+\-() ]{6,30}", value):
            raise serializers.ValidationError(
                "شماره تماس معتبر نیست. فقط رقم، فاصله، +، - و پرانتز مجاز است."
            )
        if sum(character.isdigit() for character in value) < 6:
            raise serializers.ValidationError("شماره تماس باید حداقل ۶ رقم داشته باشد.")
        return value

    def validate_tazkira_number(self, value):
        value = normalize_digits(value or "").strip()
        if not value:
            if self.instance is None:
                raise serializers.ValidationError("شماره تذکره الزامی است.")
            return value
        if len(value) < 3:
            raise serializers.ValidationError("شماره تذکره معتبر نیست.")
        return value

    def validate(self, attrs):
        if self.instance is None:
            required_fields = {
                "father_name": "نام پدر",
                "phone": "شماره تماس",
                "tazkira_number": "شماره تذکره",
            }
            for field, label in required_fields.items():
                value = attrs.get(field)
                if value is None or not str(value).strip():
                    raise serializers.ValidationError(
                        {field: f"{label} الزامی است."}
                    )
            payment_amount = attrs.get("initial_payment_amount")
            payment_fields = (
                ("initial_payment_date", "تاریخ پرداخت اولیه الزامی است."),
                (
                    "initial_payment_period_start",
                    "شروع دوره پرداخت اولیه الزامی است.",
                ),
            )
            if payment_amount is None and any(
                field in attrs
                for field, _ in payment_fields
            ):
                raise serializers.ValidationError(
                    {"initial_payment_amount": "مبلغ پرداخت اولیه الزامی است."}
                )
            if payment_amount is not None and payment_amount > 0:
                for field, message in payment_fields:
                    if attrs.get(field) is None:
                        raise serializers.ValidationError({field: message})
        return attrs

    def validate_address(self, value):
        value = (value or "").strip()
        return value

    def validate_photo(self, value):
        if not value:
            return value

        if value.size > MAX_PHOTO_SIZE:
            raise serializers.ValidationError("حجم serialized photo بیشتر از ۵ MB باشد.")

        extension = Path(value.name).suffix.lower()
        if extension not in ALLOWED_PHOTO_EXTENSIONS:
            raise serializers.ValidationError(
                "فرضاً فرمت‌های JPG، JPEG، PNG و WebP serialized."
            )

        try:
            value.seek(0)
            image = Image.open(value)
            image.verify()
            image_format = (image.format or "").upper()
        except (UnidentifiedImageError, OSError, ValueError):
            raise serializers.ValidationError("فایل selecioned imaging imagingValid est.")
        finally:
            try:
                value.seek(0)
            except (AttributeError, OSError):
                pass

        if image_format not in ALLOWED_IMAGE_FORMATS:
            raise serializers.ValidationError(
                "فرضاًSerialized Imaged valid."
            )

        return value


class DriverSummarySerializer(serializers.ModelSerializer):
    """Compact representation used on the dashboard."""

    photo_url = serializers.SerializerMethodField()
    status_label = serializers.SerializerMethodField()
    documents = serializers.SerializerMethodField()

    class Meta:
        model = Driver
        fields = [
            "id",
            "driver_code",
            "full_name",
            "plate_number",
            "status",
            "status_label",
            "photo_url",
            "registration_date",
            "documents",
        ]

    def get_photo_url(self, obj):
        if not obj.photo:
            return None
        version = int(obj.updated_at.timestamp()) if obj.updated_at else 0
        return f"/api/drivers/{obj.pk}/photo/?v={version}"

    def get_status_label(self, obj):
        return "فعال" if obj.status else "غیرفعال"

    def get_documents(self, obj):
        docs = Document.objects.filter(driver=obj, status='active')
        return [
            {
                "id": doc.id,
                "document_name": doc.document_name,
                "original_filename": doc.original_filename,
                "file_size_mb": round(doc.file_size / 1024 / 1024, 2) if doc.file_size else 0,
                "upload_date": doc.upload_date,
                "description": doc.description,
            }
            for doc in docs
        ]
