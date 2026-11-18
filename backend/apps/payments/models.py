"""Financial domain models — docs/FINANCIAL_ARCHITECTURE.md §4.

Cash is created only in Payment. PaymentAllocation is a directed claim on that
cash (active sum ≤ amount). AllocationConsumption moves a claim from the credit
pool to a period — it creates no money. Adjustment only moves/forgives debt.
Periods are computed, never stored. All financial records are append-only:
hard delete is forbidden and status changes happen only through services.
"""

from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


def validate_whole_afn(value: Decimal) -> None:
    """Whole-AFN contract (T3): exact integer SUMs in SQLite."""
    if value != value.to_integral_value():
        raise ValidationError("مبلغ باید عدد صحیح افغانی باشد (بدون اعشار).")


def validate_not_future_date(value) -> None:
    if value > timezone.localdate():
        raise ValidationError("تاریخ نمی‌تواند در آینده باشد.")


class PaymentStatus(models.TextChoices):
    RECEIVED = "received", "دریافت‌شده"
    VOIDED = "voided", "ابطال‌شده"
    CORRECTED = "corrected", "اصلاح‌شده"


class AllocationType(models.TextChoices):
    FEE_PERIOD = "fee_period", "تسویه فیس دوره"
    CREDIT = "credit", "اعتبار"


class AdjustmentType(models.TextChoices):
    WAIVER = "waiver", "بخشش"
    TRANSFER = "transfer", "انتقال"
    WAIVER_REVERSAL = "waiver_reversal", "بازگشت بخشش"
    TRANSFER_REVERSAL = "transfer_reversal", "بازگشت انتقال"


class AppendOnlyModel(models.Model):
    """Hard delete is forbidden (C8); admin also disables delete."""

    class Meta:
        abstract = True

    def delete(self, *args, **kwargs):
        raise PermissionError("رکوردهای مالی قابل حذف نیستند (append-only).")


class Payment(AppendOnlyModel):
    driver = models.ForeignKey(
        "drivers.Driver",
        on_delete=models.PROTECT,
        related_name="payments",
        verbose_name="راننده",
    )
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[validate_whole_afn],
        verbose_name="مبلغ (AFN)",
    )
    payment_date = models.DateField(
        validators=[validate_not_future_date],
        verbose_name="تاریخ دریافت نقد",
        help_text="تاریخ واقعی دریافت نقد؛ ثبت دیرهنگام نقد گذشته مجاز است.",
    )
    effective_date = models.DateField(
        verbose_name="تاریخ اثر در گزارش‌ها",
        help_text="رسید عادی = تاریخ دریافت؛ پرداخت جایگزین اصلاح = روز اصلاح.",
    )
    receipt_number = models.CharField(
        max_length=50, blank=True, default="", verbose_name="شماره رسید"
    )
    description = models.TextField(blank=True, default="", verbose_name="توضیحات")
    idempotency_key = models.CharField(
        max_length=64, unique=True, null=True, blank=True
    )
    status = models.CharField(
        max_length=20,
        choices=PaymentStatus.choices,
        default=PaymentStatus.RECEIVED,
        verbose_name="وضعیت",
    )
    correction_of = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="corrections",
    )
    void_reason = models.TextField(blank=True, default="")
    correction_reason = models.TextField(blank=True, default="")
    voided_at = models.DateTimeField(null=True, blank=True)
    corrected_at = models.DateTimeField(null=True, blank=True)
    voided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="payments_voided",
    )
    corrected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="payments_corrected",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="payments_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "پرداخت"
        verbose_name_plural = "پرداخت‌ها"
        indexes = [
            models.Index(fields=["driver", "payment_date"], name="pay_driver_date_idx"),
            models.Index(fields=["status"], name="pay_status_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gt=0), name="pay_amount_positive"
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(status="voided")
                    & models.Q(voided_at__isnull=False)
                    & models.Q(voided_by__isnull=False)
                    & ~models.Q(void_reason="")
                )
                | ~models.Q(status="voided"),
                name="pay_voided_consistent",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(status="corrected")
                    & models.Q(corrected_at__isnull=False)
                    & models.Q(corrected_by__isnull=False)
                    & ~models.Q(correction_reason="")
                )
                | ~models.Q(status="corrected"),
                name="pay_corrected_consistent",
            ),
            models.CheckConstraint(
                condition=models.Q(status="received")
                & models.Q(voided_at__isnull=True)
                & models.Q(corrected_at__isnull=True)
                | ~models.Q(status="received"),
                name="pay_received_clean",
            ),
            models.CheckConstraint(
                condition=models.Q(voided_at__isnull=True) | models.Q(status="voided"),
                name="pay_voided_at_only_when_voided",
            ),
            models.CheckConstraint(
                condition=models.Q(corrected_at__isnull=True)
                | models.Q(status="corrected"),
                name="pay_corrected_at_only_when_corrected",
            ),
        ]

    def __str__(self) -> str:
        return f"پرداخت {self.pk} — {self.amount} AFN"

    @property
    def is_void(self) -> bool:
        """Derived only (D7): status is the single source of truth."""
        return self.status != PaymentStatus.RECEIVED


class PaymentRefund(AppendOnlyModel):
    """Immutable cash refund against a received payment."""

    payment = models.ForeignKey(
        Payment,
        on_delete=models.PROTECT,
        related_name="refunds",
        verbose_name="پرداخت",
    )
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[validate_whole_afn],
        verbose_name="مبلغ برگشت (AFN)",
    )
    refund_date = models.DateField(
        validators=[validate_not_future_date],
        verbose_name="تاریخ برگشت",
    )
    effective_date = models.DateField(
        verbose_name="تاریخ اثر در گزارش‌ها",
        help_text="Refund از تاریخ ثبت عملیاتی در Ledger اثر می‌گذارد.",
    )
    reason = models.TextField(verbose_name="دلیل برگشت")
    refunded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="payment_refunds",
        verbose_name="کاربر ثبت‌کننده",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "برگشت پول"
        verbose_name_plural = "برگشت پول‌ها"
        indexes = [
            models.Index(fields=["payment", "refund_date"], name="refund_pay_date_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gt=0),
                name="refund_amount_positive",
            ),
        ]


class PaymentAllocation(AppendOnlyModel):
    payment = models.ForeignKey(
        Payment,
        on_delete=models.PROTECT,
        related_name="allocations",
        verbose_name="پرداخت",
    )
    allocation_type = models.CharField(
        max_length=20, choices=AllocationType.choices, verbose_name="نوع تخصیص"
    )
    target_period_start = models.DateField(null=True, blank=True)
    target_period_end = models.DateField(null=True, blank=True)
    allocated_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[validate_whole_afn],
        verbose_name="مبلغ تخصیص (AFN)",
    )
    effective_date = models.DateField(verbose_name="تاریخ اثر")
    correction_of = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="allocation_corrections",
    )
    reversed_at = models.DateTimeField(null=True, blank=True)
    reversed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="allocations_reversed",
    )
    reversal_reason = models.TextField(blank=True, default="")
    allocated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="allocations_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "تخصیص پرداخت"
        verbose_name_plural = "تخصیص‌های پرداخت"
        indexes = [
            models.Index(fields=["payment"], name="alloc_payment_idx"),
            models.Index(
                fields=["target_period_start", "target_period_end"],
                name="alloc_period_idx",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(allocated_amount__gt=0),
                name="alloc_amount_positive",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        allocation_type="fee_period",
                        target_period_start__isnull=False,
                        target_period_end__isnull=False,
                    )
                    | models.Q(
                        allocation_type="credit",
                        target_period_start__isnull=True,
                        target_period_end__isnull=True,
                    )
                ),
                name="alloc_target_matches_type",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(target_period_start__isnull=True)
                    | models.Q(target_period_end__isnull=True)
                    | models.Q(target_period_start__lte=models.F("target_period_end"))
                ),
                name="alloc_period_order",
            ),
            models.CheckConstraint(
                condition=models.Q(reversed_at__isnull=True)
                | (
                    models.Q(reversed_by__isnull=False)
                    & ~models.Q(reversal_reason="")
                ),
                name="alloc_reversal_consistent",
            ),
        ]

    def __str__(self) -> str:
        return f"تخصیص {self.pk} — {self.allocated_amount} AFN"

    @property
    def is_reversed(self) -> bool:
        return self.reversed_at is not None


class AllocationConsumption(AppendOnlyModel):
    source_allocation = models.ForeignKey(
        PaymentAllocation,
        on_delete=models.PROTECT,
        related_name="consumptions",
        verbose_name="تخصیص اعتباری مبدأ",
    )
    consumption_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[validate_whole_afn],
        verbose_name="مبلغ مصرف (AFN)",
    )
    target_period_start = models.DateField()
    target_period_end = models.DateField()
    effective_date = models.DateField(verbose_name="تاریخ تأیید مدیر")
    consumption_id = models.CharField(max_length=64, unique=True)
    consumed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="consumptions_approved",
    )
    reason = models.TextField(blank=True, default="")
    reversed_at = models.DateTimeField(null=True, blank=True)
    reversed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="consumptions_reversed",
    )
    reversal_reason = models.TextField(blank=True, default="")
    consumed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "مصرف اعتبار"
        verbose_name_plural = "مصرف‌های اعتبار"
        indexes = [
            models.Index(fields=["source_allocation"], name="cons_source_idx"),
            models.Index(
                fields=["target_period_start", "target_period_end"],
                name="cons_period_idx",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(consumption_amount__gt=0),
                name="cons_amount_positive",
            ),
            models.CheckConstraint(
                condition=models.Q(target_period_start__lte=models.F("target_period_end")),
                name="cons_period_order",
            ),
            models.CheckConstraint(
                condition=models.Q(reversed_at__isnull=True)
                | (
                    models.Q(reversed_by__isnull=False)
                    & ~models.Q(reversal_reason="")
                ),
                name="cons_reversal_consistent",
            ),
        ]

    def __str__(self) -> str:
        return f"مصرف {self.pk} — {self.consumption_amount} AFN"

    @property
    def is_reversed(self) -> bool:
        return self.reversed_at is not None


class Adjustment(AppendOnlyModel):
    # Transfers/waivers are intra-driver (between this driver's periods); the
    # driver link is required for per-driver conservation (T) and reporting,
    # since period date-pairs alone are ambiguous across drivers sharing an anchor.
    driver = models.ForeignKey(
        "drivers.Driver",
        on_delete=models.PROTECT,
        related_name="adjustments",
        verbose_name="راننده",
    )
    adjustment_type = models.CharField(
        max_length=20, choices=AdjustmentType.choices, verbose_name="نوع تعدیل"
    )
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[validate_whole_afn],
        verbose_name="مبلغ (AFN)",
    )
    source_period_start = models.DateField()
    source_period_end = models.DateField()
    destination_period_start = models.DateField(null=True, blank=True)
    destination_period_end = models.DateField(null=True, blank=True)
    reverses_adjustment = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="reversals",
    )
    reason = models.TextField(verbose_name="دلیل")
    effective_date = models.DateField(verbose_name="تاریخ تصمیم")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="adjustments_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "تعدیل"
        verbose_name_plural = "تعدیل‌ها"
        indexes = [
            models.Index(fields=["driver"], name="adj_driver_idx"),
            models.Index(
                fields=["source_period_start", "source_period_end"],
                name="adj_source_period_idx",
            ),
            models.Index(
                fields=["destination_period_start", "destination_period_end"],
                name="adj_dest_period_idx",
            ),
            models.Index(fields=["reverses_adjustment"], name="adj_reverses_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gt=0), name="adj_amount_positive"
            ),
            models.CheckConstraint(
                condition=~models.Q(reason=""), name="adj_reason_required"
            ),
            models.CheckConstraint(
                condition=models.Q(source_period_start__lte=models.F("source_period_end")),
                name="adj_source_period_order",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        adjustment_type__in=["transfer", "transfer_reversal"],
                        destination_period_start__isnull=False,
                        destination_period_end__isnull=False,
                    )
                    | models.Q(
                        adjustment_type__in=["waiver", "waiver_reversal"],
                        destination_period_start__isnull=True,
                        destination_period_end__isnull=True,
                    )
                ),
                name="adj_destination_matches_type",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(destination_period_start__isnull=True)
                    | models.Q(destination_period_end__isnull=True)
                    | models.Q(
                        destination_period_start__lte=models.F("destination_period_end")
                    )
                ),
                name="adj_dest_period_order",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        adjustment_type__in=["waiver_reversal", "transfer_reversal"],
                        reverses_adjustment__isnull=False,
                    )
                    | models.Q(
                        adjustment_type__in=["waiver", "transfer"],
                        reverses_adjustment__isnull=True,
                    )
                ),
                name="adj_reversal_link_matches_type",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.get_adjustment_type_display()} {self.pk} — {self.amount} AFN"


class FeeSchedule(AppendOnlyModel):
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[validate_whole_afn],
        verbose_name="مبلغ فیس (AFN)",
    )
    effective_from = models.DateField(unique=True, verbose_name="تاریخ اثر")
    reason = models.TextField(verbose_name="دلیل")
    # Nullable only for the system seed row (600 @ 1900-01-01); W11 always sets a user.
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="fee_schedules_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "برنامه فیس"
        verbose_name_plural = "برنامه‌های فیس"
        ordering = ["effective_from"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gt=0), name="fee_amount_positive"
            ),
            models.CheckConstraint(
                condition=~models.Q(reason=""), name="fee_reason_required"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.amount} AFN از {self.effective_from}"

    def clean(self):
        super().clean()
        if self.effective_from and self.effective_from < timezone.localdate():
            raise ValidationError(
                {"effective_from": "تاریخ اثر برنامه فیس نمی‌تواند گذشته باشد (بدون backdate)."}
            )


class OnlinePaymentStatus(models.TextChoices):
    RECEIVED = "received", "دریافت‌شده"
    CORRECTED = "corrected", "اصلاح‌شده"
    VOIDED = "voided", "ابطال‌شده"


class OnlinePayment(AppendOnlyModel):
    """Payment for online drivers — independent from guaranteed driver financial system.

    No FeeSchedule, Credit, Allocation, or Transfer logic applies to online payments.
    Completely separate from the Payment model used by guaranteed drivers.
    """

    driver = models.ForeignKey(
        "drivers.Driver",
        on_delete=models.PROTECT,
        related_name="online_payments",
        verbose_name="راننده",
    )
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[validate_whole_afn],
        verbose_name="مبلغ (AFN)",
    )
    payment_date = models.DateField(
        validators=[validate_not_future_date],
        verbose_name="تاریخ پرداخت",
        help_text="تاریخ پرداخت اقدامی",
    )
    purpose = models.TextField(verbose_name="بابت پرداخت")
    description = models.TextField(blank=True, default="", verbose_name="توضیحات")
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="online_payments_created",
        verbose_name="ثبت‌کننده",
    )
    status = models.CharField(
        max_length=20,
        choices=OnlinePaymentStatus.choices,
        default=OnlinePaymentStatus.RECEIVED,
        verbose_name="وضعیت",
    )
    voided_at = models.DateTimeField(null=True, blank=True, verbose_name="زمان ابطال")
    voided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="online_payments_voided",
        verbose_name="باطل‌کننده",
    )
    void_reason = models.TextField(blank=True, default="", verbose_name="دلیل ابطال")
    correction_of = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="corrections",
        verbose_name="پرداخت اصلاح‌شده",
    )
    corrected_at = models.DateTimeField(
        null=True, blank=True, verbose_name="زمان اصلاح"
    )
    corrected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="online_payments_corrected",
        verbose_name="اصلاح‌کننده",
    )
    correction_reason = models.TextField(
        blank=True, default="", verbose_name="دلیل اصلاح"
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="زمان ثبت")

    class Meta:
        verbose_name = "پرداخت آنلاین"
        verbose_name_plural = "پرداخت‌های آنلاین"
        indexes = [
            models.Index(fields=["driver", "payment_date"], name="onlpay_driver_date_idx"),
            models.Index(fields=["status"], name="onlpay_status_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gt=0),
                name="onlpay_amount_positive",
            ),
        ]

    def __str__(self) -> str:
        return f"پرداخت آنلاین {self.pk} — {self.amount} AFN"

    @property
    def is_void(self) -> bool:
        return self.status != OnlinePaymentStatus.RECEIVED