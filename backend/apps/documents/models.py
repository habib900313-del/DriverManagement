import os
import uuid

from django.conf import settings
from django.db import models
from django.core.exceptions import ValidationError


def document_upload_path(instance, filename):
    """
    Generate upload path: drivers/<DRIVER-CODE>/documents/<UUID>.<ext>
    """
    driver_code = instance.driver.driver_code if instance.driver else "unknown"
    ext = os.path.splitext(filename)[1].lower()
    unique_name = f"{uuid.uuid4().hex}{ext}"
    return f"drivers/{driver_code}/documents/{unique_name}"


def validate_pdf_file(value):
    # Check extension
    ext = os.path.splitext(value.name)[1].lower()
    if ext != '.pdf':
        raise ValidationError(
            "فایل باید پسوند .pdf داشته باشد."
        )
    
    # Check file size (max 10MB)
    max_size = 10 * 1024 * 1024  # 10MB
    if value.size > max_size:
        raise ValidationError(
            f"حجم فایل نباید بیش از ۱۰ مگابایت باشد. (حجم فعلی: {value.size / 1024 / 1024:.2f} MB)"
        )
    
    # Check PDF magic bytes (%PDF-)
    try:
        value.open('rb')
        header = value.read(5)
        value.seek(0)
        if not header.startswith(b'%PDF'):
            raise ValidationError(
                "فایل انتخابی یک فایل PDF معتبر نیست. (آدرس شروع فایل %PDF نمی‌باشد)"
            )
    except Exception:
        raise ValidationError(
            "خطا در بررسی محتوای فایل. لطفاً مطمئن شوید فایل PDF سالم است."
        )
    finally:
        try:
            value.seek(0)
        except:
            pass


class Document(models.Model):
    STATUS_CHOICES = [
        ('active', 'فعال'),
        ('inactive', 'غیر فعال'),
    ]
    
    driver = models.ForeignKey(
        'drivers.Driver',
        on_delete=models.CASCADE,
        related_name='documents',
        verbose_name="راننده"
    )
    document_name = models.CharField(
        max_length=200,
        help_text="عنوان یا نامbrief سند (مث licence, tazkira, etc.)"
    )
    file = models.FileField(
        upload_to=document_upload_path,
        validators=[validate_pdf_file],
        help_text="فایل PDF را آپلود کنید (حداکثر 10MB)"
    )
    original_filename = models.CharField(
        max_length=200,
        blank=True,
        help_text="نام اصلی فایل قبل از آپلود (اختیاری)"
    )
    file_size = models.PositiveIntegerField(
        default=0,
        help_text="حجم آپلوده شده (اختیاری،Auto-calculated)"
    )
    upload_date = models.DateTimeField(
        auto_now_add=True,
        verbose_name="تاریخ ثبت"
    )
    description = models.TextField(
        blank=True,
        help_text="توضیحات additional درباره این سند"
    )
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default='active',
    )
    
    class Meta:
        verbose_name = " سند "
        verbose_name_plural = " اسناد "
        ordering = ["-upload_date"]
        indexes = [
            models.Index(fields=["driver", "-upload_date"]),
        ]
    
    def __str__(self):
        return f"{self.document_name} - {self.driver.driver_code}"
    
    def clean(self):
        super().clean()
        if self.file and not self.original_filename:
            self.original_filename = os.path.basename(self.file.name)
        if not self.file_size and self.file:
            self.file_size = self.file.size
    
    def save(self, *args, **kwargs):
        self.full_clean()
        if self.file and not self.file.name:
            self.file.name = document_upload_path(self, self.file.name)
        super().save(*args, **kwargs)
    
    def delete(self, *args, **kwargs):
        raise PermissionError(
            "حذف سند مستقیم غیرمجاز است._manager باید از پنل مدیریت استفاده کند."
        )
    
    @property
    def is_active_status(self):
        return self.status == 'active'
