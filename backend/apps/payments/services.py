"""Financial service layer (§11).

Core operations: receive payment (§W1), consume credit (§W2–W3), void (§W4),
correct payment/allocation (§W5/W5-ext), waiver (§W6), transfer (§W7),
reverse adjustment (§W8), unsettle-and-reverse (§W9), change fee date/amount
(§W10/W11).
"""

import uuid
from datetime import date
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.utils import timezone

from .ledger import DriverLedger, ZERO
from .models import (
    Adjustment,
    AdjustmentType,
    AllocationConsumption,
    AllocationType,
    FeeSchedule,
    Payment,
    PaymentAllocation,
    PaymentRefund,
    PaymentStatus,
)
from .periods import (
    compute_effective_anchor,
    consecutive_periods,
    fee_for_period,
    target_period_error,
)
from apps.core.activity import log_activity
from apps.core.models import ActivityLog
from apps.drivers.models import Driver, DriverFeeHistory


def _period_label(start, end):
    """Readable quarter label for audit payloads."""
    if start is None or end is None:
        return ""
    return f"{start} → {end}"


class FinancialError(Exception):
    """Business-rule violation with a stable error code."""

    def __init__(self, message, code):
        super().__init__(message)
        self.detail = message
        self.code = code


def _validate_amount(amount):
    """Validate and coerce amount to a positive Decimal (whole AFN)."""
    amount = Decimal(str(amount))
    if amount <= 0:
        raise FinancialError("مبلغ باید مثبت باشد.", "invalid_amount")
    return amount


def _require_reason(reason):
    """Validate that a non-empty reason is provided."""
    if not reason or not str(reason).strip():
        raise FinancialError("دلیل الزامی است.", "reason_required")
    return str(reason)


def _touch_driver(driver):
    """Refresh the driver's updated_at timestamp."""
    driver.save(update_fields=["updated_at"])


def _ensure_writable_driver(driver):
    """Ensure the driver can receive new financial records."""
    if not driver.status:
        raise FinancialError("راننده غیرفعال است.", "driver_inactive")


def _validate_period(driver, start, end):
    """Validate and normalize a target period against driver constraints."""
    if start > end:
        raise FinancialError("شروع دوره بعد از پایان دوره است.", "invalid_period")
    return start, end


def _validate_allocation_period(driver, start, end, *, allow_future=False):
    """Validate an allocation / consumption target period (spec §8.2).

    The target must be one of the driver's reconstructed periods. A quarter
    that has not started yet is a prepayment: it is accepted for the fee
    allocation path (``allow_future=True``) and rejected for credit
    consumption, which settles a debt that has already started.
    """
    code = target_period_error(driver, start, end, allow_future=allow_future)
    if code is None:
        return start, end
    if code == "invalid_period":
        raise FinancialError("شروع دوره بعد از پایان دوره است.", "invalid_period")
    if code == "future_period":
        raise FinancialError(
            "دوره هدف هنوز آغاز نشده است؛ مصرف اعتبار فقط برای دوره‌های آغازشده ممکن است.",
            "future_period",
        )
    raise FinancialError(
        "بازه دوره هدف متعلق به راننده نیست؛ یک دوره معتبر را انتخاب کنید.",
        "unknown_period",
    )


def _target_periods(driver, target_period, periods_count):
    """The ordered list of periods a payment is spread over.

    ``periods_count`` quarters are taken consecutively from ``target_period``.
    A missing target yields no periods and is rejected by the allocator.
    """
    if target_period is None:
        return []
    start, end = target_period
    periods = consecutive_periods(driver, start, periods_count)
    if not periods:
        return [(start, end)]
    return periods


def _touch_payment(payment):
    """Refresh the payment's updated_at timestamp."""
    payment.save(update_fields=["updated_at"])


def _lock_payment_allocation(allocation_id):
    """Lock a payment's driver, payment, then allocation in the shared order."""
    payment_id = PaymentAllocation.objects.values_list(
        "payment_id", flat=True
    ).get(pk=allocation_id)
    driver_id = Payment.objects.values_list("driver_id", flat=True).get(
        pk=payment_id
    )
    driver = Driver.objects.select_for_update().get(pk=driver_id)
    payment = Payment.objects.select_for_update().get(pk=payment_id)
    if payment.driver_id != driver.pk:
        raise FinancialError(
            "راننده پرداخت هنگام قفل‌گذاری تغییر کرده است؛ دوباره تلاش کنید.",
            "concurrent_driver_change",
        )
    allocation = PaymentAllocation.objects.select_for_update().get(
        pk=allocation_id, payment_id=payment.pk
    )
    allocation.payment = payment
    return driver, payment, allocation


def lock_current_fee_schedule():
    """Serialize driver creation with changes to the global fee schedule."""
    return FeeSchedule.objects.select_for_update().order_by(
        "-effective_from", "-pk"
    ).first()


def _reverse_allocation(allocation, now, user, reason):
    """Mark an allocation as reversed (append-only reversal)."""
    allocation.reversed_at = now
    allocation.reversed_by = user
    allocation.reversal_reason = reason
    allocation.save(
        update_fields=[
            "reversed_at",
            "reversed_by",
            "reversal_reason",
        ]
    )


def _split_into_allocations(
    payment, driver, target_periods, user, payment_date, *, auto_extend=False
):
    """Spread a received payment over the target periods.

    Allocations use each period's full outstanding balance, including
    transferred debt. When enabled, periods are generated consecutively until
    the complete payment is assigned; no new CREDIT allocation is created.
    """
    if not target_periods:
        raise FinancialError(
            "دوره هدف الزامی است؛ پرداخت باید مستقیماً به یک دوره مالی تخصیص یابد.",
            "target_period_required",
        )

    remaining = payment.amount
    periods = iter(target_periods)
    last_period = None
    while remaining > 0:
        try:
            start, end = next(periods)
        except StopIteration:
            if not auto_extend or last_period is None:
                break
            following = consecutive_periods(driver, last_period[0], 2)
            if len(following) != 2:
                break
            start, end = following[1]
        last_period = (start, end)
        open_balance = DriverLedger(driver).period_state(start, end).balance
        fee_alloc_amount = min(open_balance, remaining)
        if fee_alloc_amount <= 0:
            continue
        PaymentAllocation.objects.create(
            payment=payment,
            allocation_type=AllocationType.FEE_PERIOD,
            target_period_start=start,
            target_period_end=end,
            allocated_amount=fee_alloc_amount,
            effective_date=payment_date,
            allocated_by=user,
        )
        remaining -= fee_alloc_amount
    if remaining > 0:
        raise FinancialError(
            "مبلغ پرداختی بیشتر از کل بدهی معتبر دوره‌های انتخاب‌شده است؛ "
            "هیچ مبلغی بدون تخصیص به دوره ثبت نمی‌شود.",
            "amount_exceeds_period_debt",
        )


def receive_payment(
    *,
    driver: Driver,
    amount,
    payment_date: date,
    user,
    target_period: tuple[date, date] | None = None,
    periods_count: int = 1,
    receipt_number: str = "",
    description: str = "",
    idempotency_key: str | None = None,
) -> Payment:
    """Receive a payment with robust idempotency handling.

    Idempotency contract:
    - A new key creates exactly one Payment.
    - A repeated key with identical logical payment data returns the
      original Payment.
    - A repeated key with conflicting logical payment data raises
      FinancialError with code "idempotency_key_conflict".
    - Concurrent requests using the same key cannot create duplicate
      Payments (unique constraint + IntegrityError handling).
    - Unrelated IntegrityError exceptions are re-raised, not suppressed.

    Logical fields compared for conflict detection:
    driver, amount, payment_date, target financial period.
    """
    amount = _validate_amount(amount)
    today = timezone.localdate()
    if payment_date > today:
        raise FinancialError("تاریخ دریافت نمی‌تواند در آینده باشد.", "invalid_date")
    if target_period is not None:
        # Reject an unusable target before anything is written (§8.2, C6).
        _validate_allocation_period(driver, *target_period, allow_future=True)
    with transaction.atomic():
        # Lock the driver row first to serialize concurrent financial
        # operations on the same driver and prevent over-allocation of
        # period debt across parallel requests (§ race-condition guard).
        driver = Driver.objects.select_for_update().get(pk=driver.pk)
        _touch_driver(driver)
        _ensure_writable_driver(driver)

        def matches_existing_payment(existing):
            if (
                existing.driver_id != driver.id
                or existing.amount != amount
                or existing.payment_date != payment_date
            ):
                return False
            alloc = existing.allocations.order_by("id").first()
            return bool(
                alloc
                and alloc.allocation_type == AllocationType.FEE_PERIOD
                and target_period is not None
                and alloc.target_period_start == target_period[0]
                and alloc.target_period_end == target_period[1]
            )

        # Idempotency: if key provided, check for an existing payment.
        if idempotency_key:
            existing = (
                Payment.objects.filter(idempotency_key=idempotency_key).first()
            )
            if existing is not None:
                if not matches_existing_payment(existing):
                    raise FinancialError(
                        "شناسه تکراری با پارامترهای متفاوت ثبت شده است.",
                        "idempotency_key_conflict",
                    )
                return existing
        try:
            with transaction.atomic():
                payment = Payment.objects.create(
                    driver=driver,
                    amount=amount,
                    payment_date=payment_date,
                    effective_date=payment_date,
                    receipt_number=receipt_number or "",
                    description=description or "",
                    idempotency_key=idempotency_key or None,
                    status=PaymentStatus.RECEIVED,
                    created_by=user,
                )
        except IntegrityError:
            if idempotency_key:
                existing = (
                    Payment.objects.filter(idempotency_key=idempotency_key).first()
                )
                if existing is not None:
                    if matches_existing_payment(existing):
                        return existing
                    raise FinancialError(
                        "شناسه تکراری با پارامترهای متفاوت ثبت شده است.",
                        "idempotency_key_conflict",
                    )
            raise
        _split_into_allocations(
            payment,
            driver,
            _target_periods(driver, target_period, periods_count),
            user,
            payment_date,
            auto_extend=True,
        )
        # Logged inside the transaction: a rolled-back payment leaves no entry,
        # and an idempotent replay returns above without a misleading record.
        log_activity(
            actor=user,
            action="payment_receive",
            module=ActivityLog.Module.PAYMENTS,
            description=f"ثبت پرداخت برای راننده «{driver.full_name}».",
            target_type="payment",
            target_id=payment.pk,
            target_label=f"{driver.driver_code} — {driver.full_name}",
            after_data={
                "payment_id": payment.pk,
                "driver_id": driver.pk,
                "driver_code": driver.driver_code,
                "amount": payment.amount,
                "payment_date": payment.payment_date,
                "receipt_number": payment.receipt_number,
                "target_period": _period_label(*(target_period or (None, None))),
                "status": payment.status,
            },
        )
        return payment



# ---------------------------------------------------------------------------
# W2 — consume credit (explicit manager approval, C5)
# ---------------------------------------------------------------------------
def consume_credit(
    *,
    source_allocation: PaymentAllocation,
    amount,
    target_period: tuple[date, date],
    user,
    consumption_id: str | None = None,
    reason: str = "",
) -> AllocationConsumption:
    amount = _validate_amount(amount)
    consumption_id = consumption_id or uuid.uuid4().hex
    with transaction.atomic():
        driver, payment, source_allocation = _lock_payment_allocation(
            source_allocation.pk
        )
        _touch_payment(payment)
        existing = AllocationConsumption.objects.filter(
            consumption_id=consumption_id
        ).first()
        if existing is not None:
            return existing
        _ensure_writable_driver(driver)
        if source_allocation.allocation_type != AllocationType.CREDIT:
            raise FinancialError(
                "مصرف اعتبار فقط از تخصیص اعتباری ممکن است.", "invalid_source"
            )
        ledger = DriverLedger(driver)
        if not ledger.allocation_active(source_allocation) or not ledger.payment_valid(
            payment
        ):
            raise FinancialError(
                "منبع اعتبار معتبر/فعال نیست.", "invalid_source"
            )
        start, end = _validate_allocation_period(driver, *target_period)
        available = ledger.source_available(source_allocation)
        need = ledger.period_state(start, end).balance
        if amount > min(available, need):
            raise FinancialError(
                "مبلغ مصرف بیش از موجودی اعتبار یا نیاز دوره هدف است.",
                "consumption_exceeds_balance",
            )
        consumption = AllocationConsumption.objects.create(
            source_allocation=source_allocation,
            consumption_amount=amount,
            target_period_start=start,
            target_period_end=end,
            effective_date=timezone.localdate(),
            consumption_id=consumption_id,
            consumed_by=user,
            reason=reason or "",
        )
        log_activity(
            actor=user,
            action="credit_consume",
            module=ActivityLog.Module.PAYMENTS,
            description=f"مصرف اعتبار برای راننده «{driver.full_name}».",
            target_type="consumption",
            target_id=consumption.pk,
            target_label=f"{driver.driver_code} — {driver.full_name}",
            after_data={
                "consumption_id": consumption.pk,
                "driver_id": driver.pk,
                "amount": amount,
                "target_period": _period_label(start, end),
                "reason": reason or "",
            },
        )
        return consumption


# ---------------------------------------------------------------------------
# W3 — void payment (cascade, one timestamp)
# ---------------------------------------------------------------------------
def void_payment(*, payment: Payment, user, reason: str) -> Payment:
    reason = _require_reason(reason)
    driver_id = payment.driver_id
    with transaction.atomic():
        # Lock driver first to serialize concurrent financial operations
        # on the same driver (§ race-condition guard).
        driver = Driver.objects.select_for_update().get(pk=driver_id)
        payment = Payment.objects.select_for_update().get(pk=payment.pk)
        _touch_payment(payment)
        payment.refresh_from_db()
        if payment.status != PaymentStatus.RECEIVED:
            raise FinancialError(
                "فقط پرداخت دریافت‌شده قابل ابطال است.", "already_invalid"
            )
        if payment.refunds.exists():
            raise FinancialError(
                "پرداخت دارای برگشت پول است و قابل ابطال نیست.",
                "payment_has_refunds",
            )
        now = timezone.now()
        _reverse_payment_children(payment, now, user, reason)
        payment.status = PaymentStatus.VOIDED
        payment.voided_at = now
        payment.voided_by = user
        payment.void_reason = reason
        payment.save(
            update_fields=["status", "voided_at", "voided_by", "void_reason", "updated_at"]
        )
        log_activity(
            actor=user,
            action="payment_void",
            module=ActivityLog.Module.PAYMENTS,
            description=f"ابطال پرداخت برای راننده «{driver.full_name}».",
            target_type="payment",
            target_id=payment.pk,
            target_label=f"{driver.driver_code} — {driver.full_name}",
            before_data={"status": PaymentStatus.RECEIVED},
            after_data={
                "payment_id": payment.pk,
                "amount": payment.amount,
                "status": payment.status,
                "reason": reason,
            },
        )
        return payment


# ---------------------------------------------------------------------------
# Hard delete (manager-only, explicit exception to the append-only rule)
# ---------------------------------------------------------------------------
def delete_payment(*, payment: Payment, user) -> dict:
    """Permanently delete a payment and the records that belong to it.

    This is the only hard-delete path in the financial domain. It is an
    explicit exception to the append-only rule, so it is deliberately narrow:

    * the driver row is locked first, exactly like every other financial
      operation, so a deletion cannot race a payment/refund/correction;
    * only rows owned by this payment are removed (its allocations, their
      consumptions, and its refunds) — no other payment or driver is touched;
    * correction chains are refused: deleting one link would leave the other
      rows pointing at a missing payment and silently rewrite history;
    * a full snapshot is written to the append-only activity log inside the
      same transaction, so the deletion itself stays auditable.
    """
    driver_id = payment.driver_id
    payment_id = payment.pk
    with transaction.atomic():
        driver = Driver.objects.select_for_update().get(pk=driver_id)
        try:
            payment = Payment.objects.select_for_update().get(pk=payment_id)
        except Payment.DoesNotExist:
            raise FinancialError(
                "پرداخت یافت نشد یا قبلاً حذف شده است.", "payment_not_found"
            )

        if payment.corrections.exists():
            raise FinancialError(
                "این پرداخت دارای پرداخت اصلاحی است و برای حفظ زنجیره سوابق قابل حذف نیست.",
                "payment_has_corrections",
            )
        if payment.correction_of_id is not None:
            raise FinancialError(
                "این پرداخت خود یک پرداخت اصلاحی است و قابل حذف نیست.",
                "payment_is_correction",
            )

        allocations = list(
            payment.allocations.order_by("created_at", "id")
        )
        refunds = list(payment.refunds.order_by("created_at", "id"))
        snapshot = {
            "payment_id": payment.pk,
            "driver_id": driver.pk,
            "driver_code": driver.driver_code,
            "amount": payment.amount,
            "payment_date": payment.payment_date,
            "effective_date": payment.effective_date,
            "receipt_number": payment.receipt_number,
            "status": payment.status,
            "allocations": [
                {
                    "id": allocation.pk,
                    "type": allocation.allocation_type,
                    "amount": allocation.allocated_amount,
                    "period_start": allocation.target_period_start,
                    "period_end": allocation.target_period_end,
                    "reversed": allocation.reversed_at is not None,
                }
                for allocation in allocations
            ],
            "refunds": [
                {
                    "id": refund.pk,
                    "amount": refund.amount,
                    "refund_date": refund.refund_date,
                }
                for refund in refunds
            ],
        }

        # Children first, parents last: every FK in this domain is PROTECT.
        AllocationConsumption.objects.filter(
            source_allocation__payment=payment
        ).delete()
        # Break the self-referencing correction links before deleting the
        # allocations; the rows are removed in the next statement anyway.
        PaymentAllocation.objects.filter(payment=payment).update(correction_of=None)
        try:
            PaymentAllocation.objects.filter(payment=payment).delete()
        except ProtectedError:
            raise FinancialError(
                "تخصیص این پرداخت در رکورد دیگری استفاده شده و قابل حذف نیست.",
                "payment_allocation_protected",
            )
        PaymentRefund.objects.filter(payment=payment).delete()
        try:
            Payment.objects.filter(pk=payment.pk).delete()
        except ProtectedError:
            raise FinancialError(
                "این پرداخت در رکورد دیگری استفاده شده و قابل حذف نیست.",
                "payment_protected",
            )

        log_activity(
            actor=user,
            action="payment_delete",
            module=ActivityLog.Module.PAYMENTS,
            description=f"حذف دائمی پرداخت برای راننده «{driver.full_name}».",
            target_type="payment",
            target_id=payment_id,
            target_label=f"{driver.driver_code} — {driver.full_name}",
            before_data=snapshot,
            after_data={"deleted": True, "payment_id": payment_id},
        )

        return {
            "id": payment_id,
            "driver_id": driver_id,
            "amount": snapshot["amount"],
            "deleted_allocations": len(allocations),
            "deleted_refunds": len(refunds),
        }


# ---------------------------------------------------------------------------
# W4 — correct payment (amount/driver) — separate from W5 (C9)
# ---------------------------------------------------------------------------
def correct_payment(
    *,
    payment: Payment,
    user,
    reason: str,
    new_amount=None,
    new_driver: Driver | None = None,
    new_payment_date: date | None = None,
    target_period: tuple[date, date] | None = None,
    periods_count: int = 1,
) -> Payment:
    reason = _require_reason(reason)
    driver_id = payment.driver_id
    driver_pks = {driver_id, new_driver.pk} if new_driver else {driver_id}
    with transaction.atomic():
        locked_drivers = {
            d.pk: d
            for d in Driver.objects.select_for_update()
            .filter(pk__in=driver_pks)
            .order_by("pk")
        }
        driver = locked_drivers[driver_id]
        new_driver_locked = locked_drivers.get(new_driver.pk) if new_driver else None
        payment = Payment.objects.select_for_update().get(pk=payment.pk)
        _touch_payment(payment)
        payment.refresh_from_db()
        if payment.status != PaymentStatus.RECEIVED:
            raise FinancialError(
                "فقط پرداخت دریافت شده قابل اصلاح است.", "already_invalid"
            )
        if payment.refunds.exists():
            raise FinancialError(
                "پرداخت دارای برگشت پول است و قابل اصلاح نیست.",
                "payment_has_refunds",
            )
        original_periods = list(
            payment.allocations.filter(
                reversed_at__isnull=True,
                allocation_type=AllocationType.FEE_PERIOD,
            )
            .order_by("target_period_start", "id")
            .values_list("target_period_start", "target_period_end")
        )
        now = timezone.now()
        today = timezone.localdate()
        _reverse_payment_children(payment, now, user, reason)
        payment.status = PaymentStatus.CORRECTED
        payment.corrected_at = now
        payment.corrected_by = user
        payment.correction_reason = reason
        payment.save(
            update_fields=[
                "status",
                "corrected_at",
                "corrected_by",
                "correction_reason",
                "updated_at",
            ]
        )
        driver = new_driver_locked or driver
        _ensure_writable_driver(driver)
        amount = _validate_amount(new_amount) if new_amount is not None else payment.amount
        cash_date = new_payment_date or payment.payment_date
        if cash_date > today:
            raise FinancialError("تاریخ دریافت نمی‌تواند در آینده باشد.", "invalid_date")
        replacement = Payment.objects.create(
            driver=driver,
            amount=amount,
            payment_date=cash_date,
            effective_date=today,  # D17: visibility = correction day, never backdated
            description=payment.description,
            correction_of=payment,
            status=PaymentStatus.RECEIVED,
            created_by=user,
        )
        target_periods = (
            _target_periods(driver, target_period, periods_count)
            if target_period is not None
            else original_periods
        )
        _split_into_allocations(
            replacement,
            driver,
            target_periods,
            user,
            today,
            auto_extend=(
                target_period is not None or driver.pk == payment.driver_id
            ),
        )
        log_activity(
            actor=user,
            action="payment_correct",
            module=ActivityLog.Module.PAYMENTS,
            description=f"اصلاح پرداخت برای راننده «{driver.full_name}».",
            target_type="payment",
            target_id=replacement.pk,
            target_label=f"{driver.driver_code} — {driver.full_name}",
            before_data={
                "payment_id": payment.pk,
                "amount": payment.amount,
                "payment_date": payment.payment_date,
                "status": PaymentStatus.CORRECTED,
            },
            after_data={
                "payment_id": replacement.pk,
                "amount": replacement.amount,
                "payment_date": replacement.payment_date,
                "correction_of": payment.pk,
                "status": replacement.status,
                "reason": reason,
            },
        )
        return replacement


# ---------------------------------------------------------------------------
# W5 — correct allocation (wrong period) — separate from W4 (C9)
# ---------------------------------------------------------------------------
def correct_allocation(
    *,
    allocation: PaymentAllocation,
    user,
    reason: str,
    new_target_period: tuple[date, date],
) -> PaymentAllocation:
    reason = _require_reason(reason)
    with transaction.atomic():
        driver, payment, allocation = _lock_payment_allocation(allocation.pk)
        _touch_payment(payment)
        if allocation.reversed_at is not None:
            raise FinancialError("این تخصیص قبلاً بازگردانده شده است.", "already_reversed")
        if allocation.allocation_type != AllocationType.FEE_PERIOD:
            raise FinancialError(
                "برای تخصیص اعتباری با مصرف وابسته از گردش کار W5-ext استفاده کنید.",
                "use_credit_correction",
            )
        start, end = _validate_allocation_period(
            driver, *new_target_period, allow_future=True
        )
        now = timezone.now()
        today = timezone.localdate()
        _reverse_allocation(allocation, now, user, reason)
        balance = DriverLedger(driver).period_state(start, end).balance
        if allocation.allocated_amount > balance:
            raise FinancialError(
                "مبلغ تخصیص بیش از مانده دوره هدف جدید است.",
                "allocation_exceeds_period_balance",
            )
        new_allocation = PaymentAllocation.objects.create(
            payment=payment,
            allocation_type=AllocationType.FEE_PERIOD,
            target_period_start=start,
            target_period_end=end,
            allocated_amount=allocation.allocated_amount,
            effective_date=today,
            correction_of=allocation,
            allocated_by=user,
        )
        log_activity(
            actor=user,
            action="allocation_correct",
            module=ActivityLog.Module.PAYMENTS,
            description=f"اصلاح تخصیص پرداخت برای راننده «{driver.full_name}».",
            target_type="allocation",
            target_id=new_allocation.pk,
            target_label=f"{driver.driver_code} — {driver.full_name}",
            before_data={
                "allocation_id": allocation.pk,
                "target_period": _period_label(
                    allocation.target_period_start, allocation.target_period_end
                ),
            },
            after_data={
                "allocation_id": new_allocation.pk,
                "target_period": _period_label(start, end),
                "amount": new_allocation.allocated_amount,
                "reason": reason,
            },
        )
        return new_allocation


# ---------------------------------------------------------------------------
# W5-ext — correct credit allocation with dependent consumptions (D12)
# ---------------------------------------------------------------------------
def correct_credit_allocation(
    *,
    allocation: PaymentAllocation,
    user,
    reason: str,
    new_credit_amount,
    fee_allocations: list[dict] | None = None,
    consumptions: list[dict] | None = None,
) -> dict:
    reason = _require_reason(reason)
    try:
        credit_value = Decimal(str(new_credit_amount))
    except (InvalidOperation, ValueError, TypeError):
        raise FinancialError("مبلغ اعتبار جایگزین معتبر نیست.", "invalid_amount")
    if credit_value < ZERO:
        raise FinancialError("مبلغ اعتبار نمی‌تواند منفی باشد.", "invalid_amount")
    new_credit_amount = _validate_amount(credit_value) if credit_value > ZERO else ZERO
    with transaction.atomic():
        driver, payment, allocation = _lock_payment_allocation(allocation.pk)
        _touch_payment(payment)
        if allocation.allocation_type != AllocationType.CREDIT:
            raise FinancialError("این تخصیص اعتباری نیست.", "invalid_source")
        if allocation.reversed_at is not None:
            raise FinancialError("این تخصیص قبلاً بازگردانده شده است.", "already_reversed")
        now = timezone.now()
        today = timezone.localdate()

        # (1) reverse all active dependent consumptions (restore destination debts)
        for consumption in allocation.consumptions.filter(reversed_at__isnull=True):
            _reverse_consumption(consumption, now, user, reason)
        # (2) reverse the source credit allocation
        _reverse_allocation(allocation, now, user, reason)

        # (3) replacements under the same payment, effective today
        new_credit = None
        if new_credit_amount > ZERO:
            new_credit = PaymentAllocation.objects.create(
                payment=payment,
                allocation_type=AllocationType.CREDIT,
                target_period_start=None,
                target_period_end=None,
                allocated_amount=new_credit_amount,
                effective_date=today,
                correction_of=allocation,
                allocated_by=user,
            )
        new_fee = []
        for item in fee_allocations or []:
            amt = _validate_amount(item["amount"])
            start, end = _validate_allocation_period(
                driver, item["start"], item["end"], allow_future=True
            )
            balance = DriverLedger(driver).period_state(start, end).balance
            if amt > balance:
                raise FinancialError(
                    "مبلغ تسویه فیس بیش از مانده دوره هدف است.",
                    "allocation_exceeds_period_balance",
                )
            new_fee.append(
                PaymentAllocation.objects.create(
                    payment=payment,
                    allocation_type=AllocationType.FEE_PERIOD,
                    target_period_start=start,
                    target_period_end=end,
                    allocated_amount=amt,
                    effective_date=today,
                    correction_of=allocation,
                    allocated_by=user,
                )
            )

        # (4) re-approved consumptions only with explicit manager approval (C5)
        new_consumptions = []
        for item in consumptions or []:
            if new_credit is None:
                raise FinancialError(
                    "برای مصرف مجدد، ابتدا تخصیص اعتباری جایگزین لازم است.",
                    "invalid_source",
                )
            amt = _validate_amount(item["amount"])
            start, end = _validate_allocation_period(driver, item["start"], item["end"])
            ledger = DriverLedger(driver)
            available = ledger.source_available(new_credit)
            need = ledger.period_state(start, end).balance
            if amt > min(available, need):
                raise FinancialError(
                    "مبلغ مصرف مجدد بیش از موجودی اعتبار یا نیاز دوره هدف است.",
                    "consumption_exceeds_balance",
                )
            new_consumptions.append(
                AllocationConsumption.objects.create(
                    source_allocation=new_credit,
                    consumption_amount=amt,
                    target_period_start=start,
                    target_period_end=end,
                    effective_date=today,
                    consumption_id=uuid.uuid4().hex,
                    consumed_by=user,
                    reason=item.get("reason", "") or "",
                )
            )
        log_activity(
            actor=user,
            action="credit_allocation_correct",
            module=ActivityLog.Module.PAYMENTS,
            description=(
                f"اصلاح تخصیص اعتباری برای راننده «{driver.full_name}»."
            ),
            target_type="allocation",
            target_id=allocation.pk,
            target_label=f"{driver.driver_code} — {driver.full_name}",
            before_data={
                "allocation_id": allocation.pk,
                "credit_amount": allocation.allocated_amount,
            },
            after_data={
                "new_credit_allocation_id": new_credit.pk if new_credit else None,
                "new_credit_amount": new_credit.allocated_amount if new_credit else 0,
                "fee_allocations_count": len(new_fee),
                "consumptions_count": len(new_consumptions),
                "reason": reason,
            },
        )
        return {
            "reversed_allocation": allocation,
            "new_credit_allocation": new_credit,
            "new_fee_allocations": new_fee,
            "new_consumptions": new_consumptions,
        }


# ---------------------------------------------------------------------------
# W6 — waiver
# ---------------------------------------------------------------------------
def create_waiver(
    *, driver: Driver, amount, source_period: tuple[date, date], user, reason: str
) -> Adjustment:
    amount = _validate_amount(amount)
    reason = _require_reason(reason)
    with transaction.atomic():
        # Lock driver row first to serialize concurrent financial operations
        # on the same driver (§ race-condition guard).
        driver = Driver.objects.select_for_update().get(pk=driver.pk)
        _touch_driver(driver)
        _ensure_writable_driver(driver)
        start, end = _validate_period(driver, *source_period)
        balance = DriverLedger(driver).period_state(start, end).balance
        if amount > balance:
            raise FinancialError(
                "مبلغ بخشش بیش از مانده دوره مبدأ است.", "waiver_exceeds_balance"
            )
        waiver = Adjustment.objects.create(
            driver=driver,
            adjustment_type=AdjustmentType.WAIVER,
            amount=amount,
            source_period_start=start,
            source_period_end=end,
            destination_period_start=None,
            destination_period_end=None,
            reason=reason,
            effective_date=timezone.localdate(),
            created_by=user,
        )
        log_activity(
            actor=user,
            action="waiver_create",
            module=ActivityLog.Module.PAYMENTS,
            description=f"ثبت بخشودگی برای راننده «{driver.full_name}».",
            target_type="adjustment",
            target_id=waiver.pk,
            target_label=f"{driver.driver_code} — {driver.full_name}",
            after_data={
                "adjustment_id": waiver.pk,
                "amount": waiver.amount,
                "source_period": _period_label(start, end),
                "reason": reason,
            },
        )
        return waiver


# ---------------------------------------------------------------------------
# W7 — transfer
# ---------------------------------------------------------------------------
def create_transfer(
    *,
    driver: Driver,
    amount,
    source_period: tuple[date, date],
    destination_period: tuple[date, date],
    user,
    reason: str,
) -> Adjustment:
    amount = _validate_amount(amount)
    reason = _require_reason(reason)
    with transaction.atomic():
        # Lock driver row first to serialize concurrent financial operations
        # on the same driver (§ race-condition guard).
        driver = Driver.objects.select_for_update().get(pk=driver.pk)
        _touch_driver(driver)
        _ensure_writable_driver(driver)
        s_start, s_end = _validate_period(driver, *source_period)
        d_start, d_end = _validate_period(driver, *destination_period)
        if (s_start, s_end) == (d_start, d_end):
            raise FinancialError("مبدأ و مقصد انتقال یکسان است.", "invalid_period")
        balance = DriverLedger(driver).period_state(s_start, s_end).balance
        if amount > balance:
            raise FinancialError(
                "مبلغ انتقال بیش از مانده دوره مبدأ است.", "transfer_exceeds_balance"
            )
        transfer = Adjustment.objects.create(
            driver=driver,
            adjustment_type=AdjustmentType.TRANSFER,
            amount=amount,
            source_period_start=s_start,
            source_period_end=s_end,
            destination_period_start=d_start,
            destination_period_end=d_end,
            reason=reason,
            effective_date=timezone.localdate(),
            created_by=user,
        )
        log_activity(
            actor=user,
            action="transfer_create",
            module=ActivityLog.Module.PAYMENTS,
            description=f"انتقال بدهی برای راننده «{driver.full_name}».",
            target_type="adjustment",
            target_id=transfer.pk,
            target_label=f"{driver.driver_code} — {driver.full_name}",
            after_data={
                "adjustment_id": transfer.pk,
                "amount": transfer.amount,
                "source_period": _period_label(s_start, s_end),
                "destination_period": _period_label(d_start, d_end),
                "reason": reason,
            },
        )
        return transfer


# ---------------------------------------------------------------------------
# W8 — reversal of waiver/transfer (append-only, stack cap for transfers)
# ---------------------------------------------------------------------------
def _reverse_consumption(consumption, now, user, reason):
    """Mark an AllocationConsumption as reversed (append-only reversal)."""
    consumption.reversed_at = now
    consumption.reversed_by = user
    consumption.reversal_reason = reason
    consumption.save(
        update_fields=[
            "reversed_at",
            "reversed_by",
            "reversal_reason",
        ]
    )


def _reverse_payment_children(payment, now, user, reason):
    """Reverse all non-reversed allocations of a payment (void cascade)."""
    for allocation in payment.allocations.filter(reversed_at__isnull=True):
        _reverse_allocation(allocation, now, user, reason)
        for consumption in allocation.consumptions.filter(reversed_at__isnull=True):
            _reverse_consumption(consumption, now, user, reason)


def refund_payment(*, payment: Payment, amount, refund_date: date, user, reason: str):
    """Record an append-only refund and rebuild affected allocation claims."""
    amount = _validate_amount(amount)
    if amount != amount.to_integral_value():
        raise FinancialError("مبلغ برگشت باید عدد صحیح افغانی باشد.", "invalid_amount")
    reason = _require_reason(reason)
    today = timezone.localdate()
    if refund_date > today:
        raise FinancialError("تاریخ برگشت نمی‌تواند در آینده باشد.", "invalid_date")

    driver_id = payment.driver_id
    with transaction.atomic():
        # Lock driver first to serialize concurrent financial operations
        # on the same driver (§ race-condition guard).
        driver = Driver.objects.select_for_update().get(pk=driver_id)
        payment = Payment.objects.select_for_update().get(pk=payment.pk)
        if payment.status != PaymentStatus.RECEIVED:
            raise FinancialError(
                "فقط پرداخت دریافت‌شده قابل برگشت پول است.", "already_invalid"
            )

        refunded_total = sum(
            payment.refunds.values_list("amount", flat=True),
            ZERO,
        )
        refundable = payment.amount - refunded_total
        if amount > refundable:
            raise FinancialError(
                "مبلغ برگشت از مانده قابل‌برگشت پرداخت بیشتر است.",
                "refund_exceeds_balance",
            )

        allocations = list(
            payment.allocations.filter(reversed_at__isnull=True)
            .prefetch_related("consumptions")
            .order_by("created_at", "id")
        )
        allocated_total = sum((allocation.allocated_amount for allocation in allocations), ZERO)
        unallocated = refundable - allocated_total
        if unallocated < ZERO:
            raise FinancialError(
                "جمع تخصیص‌های فعال از مبلغ قابل‌برگشت بیشتر است.",
                "invalid_allocation_state",
            )

        reduce_allocated = max(ZERO, amount - unallocated)
        reductions = {}
        remaining_reduction = reduce_allocated
        for allocation in reversed(allocations):
            reduction = min(allocation.allocated_amount, remaining_reduction)
            reductions[allocation.id] = reduction
            remaining_reduction -= reduction
        if remaining_reduction > ZERO:
            raise FinancialError(
                "تخصیص‌های فعال با مانده قابل‌برگشت سازگار نیستند.",
                "invalid_allocation_state",
            )

        refund = PaymentRefund.objects.create(
            payment=payment,
            amount=amount,
            refund_date=refund_date,
            effective_date=today,
            reason=reason,
            refunded_by=user,
        )
        log_activity(
            actor=user,
            action="payment_refund",
            module=ActivityLog.Module.PAYMENTS,
            description=f"ثبت برگشت پول برای راننده «{driver.full_name}».",
            target_type="refund",
            target_id=refund.pk,
            target_label=f"{driver.driver_code} — {driver.full_name}",
            after_data={
                "refund_id": refund.pk,
                "payment_id": payment.pk,
                "amount": refund.amount,
                "refund_date": refund.refund_date,
                "reason": reason,
            },
        )

        if reduce_allocated == ZERO:
            return refund

        now = timezone.now()
        active_consumptions = {
            allocation.id: list(
                allocation.consumptions.filter(reversed_at__isnull=True).order_by(
                    "consumed_at", "id"
                )
            )
            for allocation in allocations
            if allocation.allocation_type == AllocationType.CREDIT
        }
        for allocation in allocations:
            _reverse_allocation(allocation, now, user, reason)
            for consumption in active_consumptions.get(allocation.id, []):
                _reverse_consumption(consumption, now, user, reason)

        replacement_credits = {}
        for allocation in allocations:
            new_amount = allocation.allocated_amount - reductions.get(
                allocation.id, ZERO
            )
            if new_amount <= ZERO:
                continue
            replacement = PaymentAllocation.objects.create(
                payment=payment,
                allocation_type=allocation.allocation_type,
                target_period_start=allocation.target_period_start,
                target_period_end=allocation.target_period_end,
                allocated_amount=new_amount,
                effective_date=today,
                correction_of=allocation,
                allocated_by=user,
            )
            if allocation.allocation_type == AllocationType.CREDIT:
                replacement_credits[allocation.id] = replacement

        for allocation_id, consumptions in active_consumptions.items():
            replacement_credit = replacement_credits.get(allocation_id)
            if replacement_credit is None:
                continue
            for consumption in consumptions:
                ledger = DriverLedger(payment.driver)
                available = ledger.source_available(replacement_credit)
                need = ledger.period_state(
                    consumption.target_period_start,
                    consumption.target_period_end,
                ).balance
                restored_amount = min(
                    consumption.consumption_amount,
                    available,
                    need,
                )
                if restored_amount <= ZERO:
                    continue
                AllocationConsumption.objects.create(
                    source_allocation=replacement_credit,
                    consumption_amount=restored_amount,
                    target_period_start=consumption.target_period_start,
                    target_period_end=consumption.target_period_end,
                    effective_date=today,
                    consumption_id=uuid.uuid4().hex,
                    consumed_by=user,
                    reason=consumption.reason,
                )

        return refund


def reverse_adjustment(*, adjustment: Adjustment, amount, user, reason: str) -> Adjustment:
    amount = _validate_amount(amount)
    reason = _require_reason(reason)
    adjustment_id = adjustment.pk
    with transaction.atomic():
        driver_id = Adjustment.objects.values_list("driver_id", flat=True).get(
            pk=adjustment_id
        )
        # Lock driver first to serialize concurrent financial operations
        # on the same driver (§ race-condition guard).
        driver = Driver.objects.select_for_update().get(pk=driver_id)
        adjustment = Adjustment.objects.select_for_update().get(pk=adjustment_id)
        if adjustment.adjustment_type not in (
            AdjustmentType.WAIVER,
            AdjustmentType.TRANSFER,
        ):
            raise FinancialError(
                "بازگشت‌ها terminal هستند و قابل بازگشت نیستند.",
                "terminal_reversal",
            )
        _touch_driver(driver)
        _ensure_writable_driver(driver)
        ledger = DriverLedger(driver)
        previous = sum(
            (
                r.amount
                for r in driver.adjustments.all()
                if r.reverses_adjustment_id == adjustment.id
            ),
            ZERO,
        )
        if previous + amount > adjustment.amount:
            raise FinancialError(
                "جمع بازگشت‌ها بیش از مبلغ اصلی است.", "reversal_exceeds_original"
            )
        if adjustment.adjustment_type == AdjustmentType.TRANSFER:
            state = ledger.period_state(
                adjustment.destination_period_start, adjustment.destination_period_end
            )
            transfer = next(
                (t for t in state.transfers if t.adjustment.id == adjustment.id), None
            )
            remaining = transfer.remaining if transfer else ZERO
            if amount > remaining:
                raise FinancialError(
                    "مبلغ بازگشت بیش از مانده unpaid همین انتقال است؛ "
                    "ابتدا تسویه مقصد را باز کنید (گردش کار W9).",
                    "reversal_exceeds_remaining_transfer",
                )
        is_transfer = adjustment.adjustment_type == AdjustmentType.TRANSFER
        reversal = Adjustment.objects.create(
            driver=driver,
            adjustment_type=(
                AdjustmentType.TRANSFER_REVERSAL
                if is_transfer
                else AdjustmentType.WAIVER_REVERSAL
            ),
            amount=amount,
            source_period_start=adjustment.source_period_start,
            source_period_end=adjustment.source_period_end,
            destination_period_start=(
                adjustment.destination_period_start if is_transfer else None
            ),
            destination_period_end=(
                adjustment.destination_period_end if is_transfer else None
            ),
            reverses_adjustment=adjustment,
            reason=reason,
            effective_date=timezone.localdate(),
            created_by=user,
        )
        log_activity(
            actor=user,
            action="adjustment_reverse",
            module=ActivityLog.Module.PAYMENTS,
            description=(
                f"برگشت {'انتقال' if is_transfer else 'بخشودگی'} برای راننده "
                f"«{driver.full_name}»."
            ),
            target_type="adjustment",
            target_id=reversal.pk,
            target_label=f"{driver.driver_code} — {driver.full_name}",
            after_data={
                "reversal_id": reversal.pk,
                "reverses_adjustment_id": adjustment.pk,
                "amount": reversal.amount,
                "reason": reason,
            },
        )
        return reversal


# ---------------------------------------------------------------------------
# W9 — un-settle destination then reversal (recovery when W8 capacity is zero)
# ---------------------------------------------------------------------------
def unsettle_and_reverse(*, adjustment: Adjustment, amount, user, reason: str) -> Adjustment:
    amount = _validate_amount(amount)
    reason = _require_reason(reason)
    adjustment_id = adjustment.pk
    with transaction.atomic():
        driver_id = Adjustment.objects.values_list("driver_id", flat=True).get(
            pk=adjustment_id
        )
        # Lock driver row first to serialize concurrent financial operations
        # on the same driver (§ race-condition guard).
        driver = Driver.objects.select_for_update().get(pk=driver_id)
        adjustment = Adjustment.objects.select_for_update().get(pk=adjustment_id)
        if adjustment.adjustment_type != AdjustmentType.TRANSFER:
            raise FinancialError("W9 فقط برای بازگشت انتقال است.", "invalid_operation")
        _touch_driver(driver)
        _ensure_writable_driver(driver)
        dest = (
            adjustment.destination_period_start,
            adjustment.destination_period_end,
        )
        now = timezone.now()
        today = timezone.localdate()
        fee_allocations = list(
            PaymentAllocation.objects.filter(
                payment__driver=driver,
                allocation_type=AllocationType.FEE_PERIOD,
                target_period_start=dest[0],
                target_period_end=dest[1],
                reversed_at__isnull=True,
            ).select_related("payment").order_by("id")
        )
        for alloc in fee_allocations:
            _reverse_allocation(alloc, now, user, reason)
        credit_remainders = []
        for alloc in fee_allocations:
            remaining = alloc.allocated_amount
            open_own = DriverLedger(driver).period_state(*dest).remaining_own
            fee_amount = min(open_own, remaining)
            if fee_amount > ZERO:
                PaymentAllocation.objects.create(
                    payment=alloc.payment,
                    allocation_type=AllocationType.FEE_PERIOD,
                    target_period_start=dest[0],
                    target_period_end=dest[1],
                    allocated_amount=fee_amount,
                    effective_date=today,
                    correction_of=alloc,
                    allocated_by=user,
                )
                remaining -= fee_amount
            if remaining > ZERO:
                credit_remainders.append((alloc, remaining))
        reversal = reverse_adjustment(
            adjustment=adjustment, amount=amount, user=user, reason=reason
        )
        for alloc, credit_amount in credit_remainders:
            PaymentAllocation.objects.create(
                payment=alloc.payment,
                allocation_type=AllocationType.CREDIT,
                target_period_start=None,
                target_period_end=None,
                allocated_amount=credit_amount,
                effective_date=today,
                correction_of=alloc,
                allocated_by=user,
            )
        log_activity(
            actor=user,
            action="transfer_unsettle_reverse",
            module=ActivityLog.Module.PAYMENTS,
            description=(
                f"بازگشایی تسویه مقصد و برگشت انتقال برای راننده "
                f"«{driver.full_name}»."
            ),
            target_type="adjustment",
            target_id=reversal.pk,
            target_label=f"{driver.driver_code} — {driver.full_name}",
            after_data={
                "reversal_id": reversal.pk,
                "reverses_adjustment_id": adjustment.pk,
                "amount": amount,
                "reason": reason,
            },
        )
        return reversal

# ---------------------------------------------------------------------------
# W10 — change fee_start_date (dedicated endpoint, reason required)
# ---------------------------------------------------------------------------
def change_fee_start_date(*, driver: Driver, requested: date, user, reason: str):
    reason = _require_reason(reason)
    with transaction.atomic():
        driver = Driver.objects.select_for_update().get(pk=driver.pk)
        _touch_driver(driver)
        effective = compute_effective_anchor(driver, requested)
        old = driver.fee_start_date
        history = DriverFeeHistory.objects.create(
            driver=driver,
            old_fee_start_date=old,
            requested_fee_start_date=requested,
            effective_fee_start_date=effective,
            reason=reason,
            changed_by=user,
        )
        driver.fee_start_date = requested  # display mirror of latest requested
        driver.save(update_fields=["fee_start_date", "updated_at"])
        log_activity(
            actor=user,
            action="fee_start_date_change",
            module=ActivityLog.Module.PAYMENTS,
            description=f"تغییر تاریخ شروع فیس راننده «{driver.full_name}».",
            target_type="driver",
            target_id=driver.pk,
            target_label=f"{driver.driver_code} — {driver.full_name}",
            before_data={"fee_start_date": old},
            after_data={
                "requested_fee_start_date": requested,
                "effective_fee_start_date": effective,
                "reason": reason,
            },
        )
        return history


# ---------------------------------------------------------------------------
# W11 — change fee amount (append-only FeeSchedule)
# ---------------------------------------------------------------------------
def change_fee_schedule(*, amount, effective_from: date, user, reason: str) -> FeeSchedule:
    amount = _validate_amount(amount)
    reason = _require_reason(reason)
    if effective_from < timezone.localdate():
        raise FinancialError(
            "تاریخ اثر برنامه فیس نمی‌تواند گذشته باشد (بدون backdate).", "no_backdate"
        )
    with transaction.atomic():
        list(Driver.objects.select_for_update().order_by("pk"))
        lock_current_fee_schedule()
        schedule = FeeSchedule.objects.create(
            amount=amount,
            effective_from=effective_from,
            reason=reason,
            created_by=user,
        )
        log_activity(
            actor=user,
            action="fee_schedule_change",
            module=ActivityLog.Module.PAYMENTS,
            description="تغییر مبلغ فیس دوره‌ای.",
            target_type="fee_schedule",
            target_id=schedule.pk,
            target_label=str(schedule.amount),
            after_data={
                "amount": schedule.amount,
                "effective_from": schedule.effective_from,
                "reason": reason,
            },
        )
        return schedule
