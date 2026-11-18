from django.conf import settings
from django.db import models


class ActivityLog(models.Model):
    """Append-only audit trail of important user actions.

    Visible to Superusers only. Rows can never be edited or deleted through
    normal code paths; ``save`` on an existing row and ``delete`` both raise,
    mirroring :class:`UserPasswordChangeAudit`.

    Sensitive values (passwords, tokens, secrets) must never reach this table;
    the central helper in ``apps.core.activity`` sanitizes payloads before
    writing.
    """

    class Module(models.TextChoices):
        DRIVERS = "drivers", "رانندگان"
        PAYMENTS = "payments", "عملیات مالی"
        USERS = "users", "مدیریت کاربران"
        DOCUMENTS = "documents", "اسناد"
        AUTH = "auth", "احراز هویت"
        OTHER = "other", "سایر"

    class Status(models.TextChoices):
        SUCCESS = "success", "موفق"
        FAILURE = "failure", "ناموفق"

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="activity_logs",
        verbose_name="انجام‌دهنده",
    )
    # Snapshot of the username at action time, kept even if the account is later
    # deleted, so the audit trail stays readable.
    actor_username = models.CharField(max_length=150, verbose_name="نام کاربری انجام‌دهنده")
    action = models.CharField(max_length=64, verbose_name="نوع عملیات")
    module = models.CharField(max_length=64, verbose_name="بخش سیستم")
    description = models.TextField(blank=True, verbose_name="توضیح عملیات")
    target_type = models.CharField(max_length=64, blank=True, verbose_name="نوع موجودیت هدف")
    target_id = models.CharField(max_length=64, blank=True, verbose_name="شناسه رکورد هدف")
    target_label = models.CharField(max_length=255, blank=True, verbose_name="مشخصه رکورد هدف")
    timestamp = models.DateTimeField(auto_now_add=True, verbose_name="زمان عملیات")
    ip_address = models.GenericIPAddressField(null=True, blank=True, verbose_name="آدرس IP")
    metadata = models.JSONField(default=dict, blank=True, verbose_name="اطلاعات تکمیلی")
    before_data = models.JSONField(null=True, blank=True, verbose_name="اطلاعات قبل از تغییر")
    after_data = models.JSONField(null=True, blank=True, verbose_name="اطلاعات بعد از تغییر")
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.SUCCESS,
        verbose_name="نتیجه عملیات",
    )

    class Meta:
        ordering = ["-timestamp", "-id"]
        verbose_name = "گزارش فعالیت"
        verbose_name_plural = "گزارش فعالیت‌ها"
        indexes = [
            models.Index(fields=["-timestamp", "-id"], name="actlog_order_idx"),
            models.Index(fields=["actor_username"], name="actlog_actor_idx"),
            models.Index(fields=["module"], name="actlog_module_idx"),
            models.Index(fields=["action"], name="actlog_action_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.actor_username} · {self.action} · {self.timestamp}"

    def save(self, *args, **kwargs):
        # Append-only: an existing row can never be modified.
        if self.pk:
            raise PermissionError("سوابق فعالیت قابل ویرایش نیستند.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionError("سوابق فعالیت قابل حذف نیستند.")


class UserPasswordChangeAudit(models.Model):
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="password_changes_performed",
    )
    actor_username = models.CharField(max_length=150)
    target = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="password_changes_received",
    )
    target_username = models.CharField(max_length=150)
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-changed_at", "-id"]

    def save(self, *args, **kwargs):
        if self.pk:
            raise PermissionError("سوابق ممیزی قابل ویرایش نیستند.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionError("سوابق ممیزی قابل حذف نیستند.")
