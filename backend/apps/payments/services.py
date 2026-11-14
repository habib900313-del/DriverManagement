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
    PaymentStatus,
)
from .periods import (
    compute_effective_anchor,
    consecutive_periods,
    fee_for_period,
    target_period_error,
)
from apps.drivers.models import Driver, DriverFeeHistory


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
    With no target period the payment is not booked on any quarter and stays
    entirely on the credit path.
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


def _split_into_allocations(payment, driver, target_periods, user, payment_date):
    """Spread a received payment over the target periods.

    - For each target period (in order): one FEE_PERIOD allocation for that
      period's fee, limited by the amount still left.
    - Whatever is left over becomes one CREDIT allocation — a trackable
      prepayment that can be booked on a later quarter or consumed manually.
    - Without any target period the whole amount stays on the credit path.

    The sum of the allocations never exceeds the payment amount, so the
    allocation-cap trigger stays satisfied.
    """
    if not target_periods:
        PaymentAllocation.objects.create(
            payment=payment,
            allocation_type=AllocationType.CREDIT,
            target_period_start=None,
            target_period_end=None,
            allocated_amount=payment.amount,
            effective_date=payment_date,
            allocated_by=user,
        )
        return

    remaining = payment.amount
    for start, end in target_periods:
        if remaining <= 0:
            break
        # Spec W1: the fee allocation is limited by what is still open on the
        # target period's own fee — not by the period's fee itself. Using the
        # fee would let a period be over-allocated (a second payment on a
        # period that is already settled) and equation (O) would break.
        # `remaining_own` is the own fee minus every reduction already
        # booked on the period (its own allocations, waivers, credit
        # consumed and transfers out), so it never double-books the fee.
        open_fee = DriverLedger(driver).period_state(start, end).remaining_own
        fee_alloc_amount = min(open_fee, remaining)
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
        PaymentAllocation.objects.create(
            payment=payment,
            allocation_type=AllocationType.CREDIT,
            target_period_start=None,
            target_period_end=None,
            allocated_amount=remaining,
            effective_date=payment_date,
            allocated_by=user,
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
        _touch_driver(driver)
        _ensure_writable_driver(driver)
        # Idempotency: if key provided, check for an existing payment.
        if idempotency_key:
            existing = (
                Payment.objects.filter(idempotency_key=idempotency_key).first()
            )
            if existing is not None:
                # Verify it is the same logical payment operation.
                if (
                    existing.driver_id != driver.id
                    or existing.amount != amount
                    or existing.payment_date != payment_date
                ):
                    raise FinancialError(
                        "شناسه تکراری با پارامترهای متفاوت ثبت شده است.",
                        "idempotency_key_conflict",
                    )
                # Cross-check target financial period via the allocation.
                if target_period is not None:
                    alloc = existing.allocations.first()
                    if (
                        alloc is None
                        or alloc.allocation_type != AllocationType.FEE_PERIOD
                        or alloc.target_period_start != target_period[0]
                        or alloc.target_period_end != target_period[1]
                    ):
                        raise FinancialError(
                            "شناسه تکراری با پارامترهای متفاوت ثبت شده است.",
                            "idempotency_key_conflict",
                        )
                else:
                    alloc = existing.allocations.filter(
                        allocation_type=AllocationType.CREDIT
                    ).first()
                    if alloc is None:
                        raise FinancialError(
                            "شناسه تکراری با پارامترهای متفاوت ثبت شده است.",
                            "idempotency_key_conflict",
                        )
                return existing
        try:
            payment = Payment.objects.create(
                driver=driver,
                amount=amount,
                payment_date=payment_date,
                effective_date=payment_date,
                receipt_number=receipt_number or "",
                idempotency_key=idempotency_key or None,
                status=PaymentStatus.RECEIVED,
                created_by=user,
            )
        except IntegrityError:
            # Another request may have created this payment first; return it.
            if idempotency_key:
                existing = (
                    Payment.objects.filter(idempotency_key=idempotency_key).first()
                )
                if existing is not None:
                    return existing
            raise
        _split_into_allocations(
            payment, driver, _target_periods(driver, target_period, periods_count), user, payment_date
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
        payment = source_allocation.payment
        _touch_payment(payment)
        existing = AllocationConsumption.objects.filter(
            consumption_id=consumption_id
        ).first()
        if existing is not None:
            return existing
        driver = payment.driver
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
        return AllocationConsumption.objects.create(
            source_allocation=source_allocation,
            consumption_amount=amount,
            target_period_start=start,
            target_period_end=end,
            effective_date=timezone.localdate(),
            consumption_id=consumption_id,
            consumed_by=user,
            reason=reason or "",
        )


# ---------------------------------------------------------------------------
# W3 — void payment (cascade, one timestamp)
# ---------------------------------------------------------------------------
def void_payment(*, payment: Payment, user, reason: str) -> Payment:
    reason = _require_reason(reason)
    with transaction.atomic():
        _touch_payment(payment)
        payment.refresh_from_db()
        if payment.status != PaymentStatus.RECEIVED:
            raise FinancialError(
                "فقط پرداخت دریافت‌شده قابل ابطال است.", "already_invalid"
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
        return payment


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
    with transaction.atomic():
        _touch_payment(payment)
        payment.refresh_from_db()
        if payment.status != PaymentStatus.RECEIVED:
            raise FinancialError(
                "فقط پرداخت دریافت‌شده قابل اصلاح است.", "already_invalid"
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
        driver = new_driver or payment.driver
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
            correction_of=payment,
            status=PaymentStatus.RECEIVED,
            created_by=user,
        )
        _split_into_allocations(
            replacement,
            driver,
            _target_periods(driver, target_period, periods_count),
            user,
            today,
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
        payment = allocation.payment
        _touch_payment(payment)
        allocation.refresh_from_db()
        if allocation.reversed_at is not None:
            raise FinancialError("این تخصیص قبلاً بازگردانده شده است.", "already_reversed")
        if allocation.allocation_type != AllocationType.FEE_PERIOD:
            raise FinancialError(
                "برای تخصیص اعتباری با مصرف وابسته از گردش کار W5-ext استفاده کنید.",
                "use_credit_correction",
            )
        driver = payment.driver
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
        return PaymentAllocation.objects.create(
            payment=payment,
            allocation_type=AllocationType.FEE_PERIOD,
            target_period_start=start,
            target_period_end=end,
            allocated_amount=allocation.allocated_amount,
            effective_date=today,
            correction_of=allocation,
            allocated_by=user,
        )


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
        payment = allocation.payment
        _touch_payment(payment)
        allocation.refresh_from_db()
        if allocation.allocation_type != AllocationType.CREDIT:
            raise FinancialError("این تخصیص اعتباری نیست.", "invalid_source")
        if allocation.reversed_at is not None:
            raise FinancialError("این تخصیص قبلاً بازگردانده شده است.", "already_reversed")
        driver = payment.driver
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
        _touch_driver(driver)
        _ensure_writable_driver(driver)
        start, end = _validate_period(driver, *source_period)
        balance = DriverLedger(driver).period_state(start, end).balance
        if amount > balance:
            raise FinancialError(
                "مبلغ بخشش بیش از مانده دوره مبدأ است.", "waiver_exceeds_balance"
            )
        return Adjustment.objects.create(
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
        return Adjustment.objects.create(
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


def reverse_adjustment(*, adjustment: Adjustment, amount, user, reason: str) -> Adjustment:
    amount = _validate_amount(amount)
    reason = _require_reason(reason)
    if adjustment.adjustment_type not in (
        AdjustmentType.WAIVER,
        AdjustmentType.TRANSFER,
    ):
        raise FinancialError("بازگشت‌ها terminal هستند و قابل بازگشت نیستند.", "terminal_reversal")
    with transaction.atomic():
        driver = adjustment.driver
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
        return Adjustment.objects.create(
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


# ---------------------------------------------------------------------------
# W9 — un-settle destination then reversal (recovery when W8 capacity is zero)
# ---------------------------------------------------------------------------
def unsettle_and_reverse(*, adjustment: Adjustment, amount, user, reason: str) -> Adjustment:
    amount = _validate_amount(amount)
    reason = _require_reason(reason)
    if adjustment.adjustment_type != AdjustmentType.TRANSFER:
        raise FinancialError("W9 فقط برای بازگشت انتقال است.", "invalid_operation")
    with transaction.atomic():
        driver = adjustment.driver
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
            ).select_related("payment")
        )
        for alloc in fee_allocations:
            _reverse_allocation(alloc, now, user, reason)
        return reverse_adjustment(
            adjustment=adjustment, amount=amount, user=user, reason=reason
        )


# ---------------------------------------------------------------------------
# W10 — change fee_start_date (dedicated endpoint, reason required)
# ---------------------------------------------------------------------------
def change_fee_start_date(*, driver: Driver, requested: date, user, reason: str):
    reason = _require_reason(reason)
    with transaction.atomic():
        _touch_driver(driver)
        driver.refresh_from_db()
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
        return FeeSchedule.objects.create(
            amount=amount,
            effective_from=effective_from,
            reason=reason,
            created_by=user,
        )
