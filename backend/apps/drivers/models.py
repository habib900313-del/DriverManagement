"""Driver domain model.

Only the Driver model belongs to this phase. Payment and Document models are
intentionally deferred, and vehicle details live on the Driver record.
"""

import re
import uuid
from datetime import date
from pathlib import Path

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models.functions import Lower
from django.utils import timezone

PERSIAN_DIGITS = "۰۱۲۳۴۵۶۷۸۹"
ARABIC_DIGITS = "٠١٢٣٤٥٦٧٨٩"
LATIN_DIGITS = "0123456789"

_DIGIT_TRANSLATION = str.maketrans(
    PERSIAN_DIGITS + ARABIC_DIGITS,
    LATIN_DIGITS + LATIN_DIGITS,
)


def normalize_digits(value: str) -> str:
    """Convert Persian/Arabic digits to ASCII so lookups are predictable."""
    return (value or "").translate(_DIGIT_TRANSLATION)


def normalize_driver_code(value: str) -> str:
    return re.sub(r"\s+", " ", normalize_digits(value or "").strip())


def normalize_plate_number(value: str) -> str:
    """Canonical plate form: trimmed, upper-case, single spaces."""
    value = normalize_digits(value or "").strip().upper()
    return re.sub(r"\s+", " ", value)


def safe_folder_name(value: str) -> str:
    """Make a driver code safe to use as a single directory name."""
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "_", value or "").strip("_")
    return cleaned or "driver"


def driver_photo_upload_to(instance: "Driver", filename: str) -> str:
    """Generate a collision-free path under the driver's own folder."""
    extension = Path(filename).suffix.lower()
    if extension not in {".jpg", ".jpeg", ".png", ".webp"}:
        extension = ".jpg"
    unique_name = f"{uuid.uuid4().hex}{extension}"
    return f"drivers/{safe_folder_name(instance.driver_code)}/photos/{unique_name}"


class Driver(models.Model):
    PERIOD_CALENDAR_GREGORIAN = "gregorian"
    PERIOD_CALENDAR_JALALI = "jalali"
    PERIOD_CALENDAR_CHOICES = [
        (PERIOD_CALENDAR_GREGORIAN, "میلادی — دوره‌های قبلی"),
        (PERIOD_CALENDAR_JALALI, "هجری شمسی"),
    ]

    driver_code = models.CharField(
        max_length=50,
        verbose_name="شماره مسلسل",
        help_text="شماره مسلسل دستی و یکتای راننده",
    )
    full_name = models.CharField(max_length=200, verbose_name="نام کامل")
    father_name = models.CharField(
        max_length=200,
        blank=True,
        null=True,
        verbose_name="نام پدر",
    )
    phone = models.CharField(
        max_length=30,
        blank=True,
        null=True,
        verbose_name="شماره تماس",
    )
    tazkira_number = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        verbose_name="شماره تذکره",
    )
    plate_number = models.CharField(
        max_length=30,
        unique=True,
        verbose_name="پلیت موتر",
    )
    address = models.TextField(
        blank=True,
        null=True,
        verbose_name="آدرس",
    )
    photo = models.ImageField(
        upload_to=driver_photo_upload_to,
        blank=True,
        null=True,
        verbose_name="عکس پروفایل",
    )
    registration_date = models.DateField(
        default=timezone.localdate,
        validators=[
            MinValueValidator(date(1900, 1, 1)),
            MaxValueValidator(date(2100, 12, 31)),
        ],
        verbose_name="تاریخ ثبت",
    )
    fee_start_date = models.DateField(
        validators=[
            MinValueValidator(date(1900, 1, 1)),
            MaxValueValidator(date(2100, 12, 31)),
        ],
        verbose_name="تاریخ شروع فیس",
    )
    period_calendar = models.CharField(
        max_length=16,
        choices=PERIOD_CALENDAR_CHOICES,
        default=PERIOD_CALENDAR_JALALI,
        verbose_name="تقویم دوره‌های مالی",
    )
    status = models.BooleanField(default=True, verbose_name="وضعیت فعال")
    driver_type = models.CharField(
        max_length=20,
        choices=[
            ("guaranteed", "تضمینی"),
            ("online", "آنلاین"),
        ],
        default="guaranteed",
        verbose_name="نوع راننده",
        help_text="نوع راننده: تضمینی (با فیس دوره‌ای) یا آنلاین (بدون فیس دوره‌ای)",
    )
    is_deleted = models.BooleanField(default=False, verbose_name='حذف شده')
    deleted_at = models.DateTimeField(null=True, blank=True, verbose_name='زمان حذف')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-is_deleted", "-created_at", "-id"]
        verbose_name = "راننده"
        verbose_name_plural = "رانندگان"
        constraints = [
            # Keep codes unique among active drivers; archived codes may be reused.
            models.UniqueConstraint(
                Lower("driver_code"),
                name="uniq_driver_code_not_reused",
                condition=~models.Q(is_deleted=True),
            ),
        ]

    def __str__(self) -> str:
        return f"{self.driver_code} — {self.full_name}"

    def save(self, *args, **kwargs):
        # Normalize before every write so uniqueness compares canonical values.
        self.driver_code = normalize_driver_code(self.driver_code)
        self.plate_number = normalize_plate_number(self.plate_number)
        for field in ("full_name", "father_name", "phone", "tazkira_number", "address"):
            value = getattr(self, field)
            if isinstance(value, str):
                setattr(self, field, value.strip())
        # When marking a driver as deleted, clear the deleted_at on restore
        if self.is_deleted and not self.pk:
            self.deleted_at = timezone.now()
        super().save(*args, **kwargs)


class DriverFeeHistory(models.Model):
    """Append-only era log of fee_start_date changes (spec §4.6, W10).

    Driver.fee_start_date is only a display mirror of the latest requested
    value; period reconstruction reads this history.
    """

    driver = models.ForeignKey(
        Driver,
        on_delete=models.PROTECT,
        related_name="fee_history",
        verbose_name="راننده",
    )
    old_fee_start_date = models.DateField(
        null=True, blank=True, verbose_name="تاریخ شروع پیشین"
    )
    requested_fee_start_date = models.DateField(verbose_name="تاریخ درخواستی")
    effective_fee_start_date = models.DateField(verbose_name="لنگر era مؤثر")
    reason = models.TextField(verbose_name="دلیل")
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="fee_history_changes",
    )
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "سابقه تاریخ شروع فیس"
        verbose_name_plural = "سوابق تاریخ شروع فیس"
        ordering = ["changed_at", "id"]
        indexes = [
            models.Index(fields=["driver", "changed_at"], name="feehist_driver_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(reason=""), name="feehist_reason_required"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.driver_id}: {self.old_fee_start_date} → {self.effective_fee_start_date}"

    def delete(self, *args, **kwargs):
        raise PermissionError("سوابق مالی قابل حذف نیستند (append-only).")
