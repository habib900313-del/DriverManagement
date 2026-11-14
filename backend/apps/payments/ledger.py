"""Accounting core: as-of predicates and the Own-First obligation stack (spec §5/§6).

Everything is a pure function of immutable records, so any as-of date D
reproduces the economic state of that day. Data volume is a single offline
office, so rows are loaded once per driver and reduced in Python for exactness.
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from django.utils import timezone

from .models import (
    Adjustment,
    AdjustmentType,
    AllocationConsumption,
    AllocationType,
    PaymentAllocation,
    PaymentStatus,
)
from .periods import fee_for_period, reconstruct_periods

ZERO = Decimal("0.00")


def local_date(value) -> date:
    return timezone.localtime(value).date()


def clamp(value: Decimal, low: Decimal, high: Decimal) -> Decimal:
    return max(low, min(value, high))


def payment_valid_as_of(payment, d: date) -> bool:
    if payment.effective_date > d:
        return False
    if payment.voided_at and local_date(payment.voided_at) <= d:
        return False
    if payment.corrected_at and local_date(payment.corrected_at) <= d:
        return False
    return True


def payment_recorded_as_of(payment, d: date) -> bool:
    if local_date(payment.created_at) > d:
        return False
    if payment.voided_at and local_date(payment.voided_at) <= d:
        return False
    if payment.corrected_at and local_date(payment.corrected_at) <= d:
        return False
    return True


def record_active_as_of(record, d: date) -> bool:
    if record.effective_date > d:
        return False
    if record.reversed_at and local_date(record.reversed_at) <= d:
        return False
    return True


@dataclass
class TransferNet:
    adjustment: Adjustment
    net: Decimal
    reversed_total: Decimal
    remaining: Decimal = ZERO


@dataclass
class PeriodState:
    start: date
    end: date
    fee: Decimal
    remaining_own: Decimal
    balance: Decimal
    reductions: Decimal
    cash_settled: Decimal
    credit_settled: Decimal
    net_waiver: Decimal
    net_transfer_out: Decimal
    net_transfer_in: Decimal
    credit_cash_absorbed: Decimal = ZERO
    transfers: list[TransferNet] = field(default_factory=list)

    @property
    def is_overdue(self) -> bool:
        return self.end < timezone.localdate()


class DriverLedger:
    """Loads a driver's financial records once and computes as-of state."""

    def __init__(self, driver, as_of: date | None = None):
        self.driver = driver
        self.as_of = as_of or timezone.localdate()
        self.payments = list(driver.payments.all())
        self.allocations = list(
            PaymentAllocation.objects.filter(payment__driver=driver).select_related(
                "payment"
            )
        )
        self.consumptions = list(
            AllocationConsumption.objects.filter(
                source_allocation__payment__driver=driver
            ).select_related("source_allocation__payment")
        )
        self.adjustments = list(driver.adjustments.all())
        self.periods = reconstruct_periods(driver, until=self._coverage_horizon())

    def _coverage_horizon(self) -> date:
        """Latest period start this driver's records actually touch.

        The reporting horizon is `start <= as_of` (spec §8.2). A payment may
        however be allocated to a quarter that starts after `as_of` — paying
        for the upcoming quarter — so the horizon is extended to cover every
        period the driver has *active* records for.

        Without this the ledger would not see those allocations at all: the
        money would be in neither `settled_by_cash` nor `available_credit`,
        and the conservation equations (O)/(C)/(S) would not balance.

        Only records that are active as of `as_of` count, so a historical
        as-of report is not polluted by periods that had not started yet.
        """
        horizon = self.as_of
        for allocation in self.allocations:
            start = allocation.target_period_start
            if start and start > horizon and self.allocation_active(allocation):
                horizon = start
        for consumption in self.consumptions:
            start = consumption.target_period_start
            if start and start > horizon and self.consumption_active(consumption):
                horizon = start
        for adjustment in self.adjustments:
            if not self.adjustment_active(adjustment):
                continue
            for start in (
                adjustment.source_period_start,
                adjustment.destination_period_start,
            ):
                if start and start > horizon:
                    horizon = start
        return horizon

    # -- predicates (§6.1) -------------------------------------------------
    def payment_valid(self, payment) -> bool:
        return payment_valid_as_of(payment, self.as_of)

    def payment_recorded(self, payment) -> bool:
        """Audit predicate (F5b): created_at boundary, never mixed with F2."""
        return payment_recorded_as_of(payment, self.as_of)

    def allocation_active(self, allocation) -> bool:
        return record_active_as_of(allocation, self.as_of)

    def consumption_active(self, consumption) -> bool:
        return record_active_as_of(consumption, self.as_of)

    def adjustment_active(self, adjustment) -> bool:
        return adjustment.effective_date <= self.as_of

    # -- helpers -----------------------------------------------------------
    def _reversal_total(self, original_id: int) -> Decimal:
        return sum(
            (
                r.amount
                for r in self.adjustments
                if r.reverses_adjustment_id == original_id
                and self.adjustment_active(r)
            ),
            ZERO,
        )

    def cash_settled(self, start: date, end: date) -> Decimal:
        """FEE_PERIOD allocations settled in this period (used for overflow calc)."""
        return sum(
            (
                a.allocated_amount
                for a in self.allocations
                if a.allocation_type == AllocationType.FEE_PERIOD
                and a.target_period_start == start
                and a.target_period_end == end
                and self.allocation_active(a)
                and self.payment_valid(a.payment)
            ),
            ZERO,
        )


    def credit_settled(self, start: date, end: date) -> Decimal:
        return sum(
            (
                c.consumption_amount
                for c in self.consumptions
                if c.target_period_start == start
                and c.target_period_end == end
                and self.consumption_active(c)
                and self.allocation_active(c.source_allocation)
                and self.payment_valid(c.source_allocation.payment)
            ),
            ZERO,
        )

    def net_waiver(self, start: date, end: date) -> Decimal:
        waivers = [
            a
            for a in self.adjustments
            if a.adjustment_type == AdjustmentType.WAIVER
            and a.source_period_start == start
            and a.source_period_end == end
            and self.adjustment_active(a)
        ]
        gross = sum((w.amount for w in waivers), ZERO)
        ids = {w.id for w in waivers}
        reversed_total = sum(
            (
                r.amount
                for r in self.adjustments
                if r.adjustment_type == AdjustmentType.WAIVER_REVERSAL
                and r.reverses_adjustment_id in ids
                and self.adjustment_active(r)
            ),
            ZERO,
        )
        return gross - reversed_total

    def net_transfer_out(self, start: date, end: date) -> Decimal:
        outs = [
            a
            for a in self.adjustments
            if a.adjustment_type == AdjustmentType.TRANSFER
            and a.source_period_start == start
            and a.source_period_end == end
            and self.adjustment_active(a)
        ]
        gross = sum((t.amount for t in outs), ZERO)
        reversed_total = sum((self._reversal_total(t.id) for t in outs), ZERO)
        return gross - reversed_total

    # -- Own-First stack (§5) ---------------------------------------------
    def period_state(self, start: date, end: date) -> PeriodState:
        fee = fee_for_period(start)
        incoming = [
            a
            for a in self.adjustments
            if a.adjustment_type == AdjustmentType.TRANSFER
            and a.destination_period_start == start
            and a.destination_period_end == end
            and self.adjustment_active(a)
        ]
        transfers: list[TransferNet] = []
        for t in sorted(incoming, key=lambda a: (a.effective_date, a.id)):
            reversed_total = self._reversal_total(t.id)
            transfers.append(
                TransferNet(
                    adjustment=t,
                    net=t.amount - reversed_total,
                    reversed_total=reversed_total,
                )
            )

        cash = self.cash_settled(start, end)
        credit = self.credit_settled(start, end)
        waiver = self.net_waiver(start, end)
        xfer_out = self.net_transfer_out(start, end)
        xfer_in = sum((tr.net for tr in transfers), ZERO)
        # Credit allocations from payments that also settled a FEE_PERIOD in this
        # period count as cash coverage for the Own-First stack (§5): that cash
        # was received and is available to cover the period's fee obligation.
        credit_cash = sum(
            (
                self.source_available(a)
                for a in self.allocations
                if a.allocation_type == AllocationType.CREDIT
                and self.allocation_active(a)
                and self.payment_valid(a.payment)
                and any(
                    fa.allocation_type == AllocationType.FEE_PERIOD
                    and fa.target_period_start == start
                    and fa.target_period_end == end
                    and fa.payment_id == a.payment_id
                    and self.allocation_active(fa)
                    for fa in self.allocations
                )
            ),
            ZERO,
        )
        cash_available = cash + credit_cash
        reductions = waiver + cash_available + credit + xfer_out

        remaining_own = fee - min(reductions, fee)
        overflow = reductions - fee
        running = ZERO
        overflow_applied = ZERO
        for tr in transfers:
            applied = clamp(overflow - running, ZERO, tr.net)
            tr.remaining = tr.net - applied
            running += tr.net
            overflow_applied += applied
        balance = remaining_own + sum((tr.remaining for tr in transfers), ZERO)

        # cash_settled for conservation equation O: FEE_PERIOD allocations plus
        # credit_cash that was actually used to absorb transfer overflow.
        # Credit cash that created overflow but found no transfers to absorb it
        # has not settled any debt and must not be counted as settled cash.
        cash_from_fee = max(0, cash - fee)
        credit_cash_absorbed = min(
            credit_cash,
            max(0, overflow_applied - cash_from_fee),
        )
        cash_settled_for_state = cash + credit_cash_absorbed

        return PeriodState(
            start=start,
            end=end,
            fee=fee,
            remaining_own=remaining_own,
            balance=balance,
            reductions=reductions,
            cash_settled=cash_settled_for_state,
            credit_settled=credit,
            net_waiver=waiver,
            net_transfer_out=xfer_out,
            net_transfer_in=xfer_in,
            credit_cash_absorbed=credit_cash_absorbed,
            transfers=transfers,
        )

    def all_period_states(self) -> list[PeriodState]:
        return [self.period_state(start, end) for start, end in self.periods]

    # -- credit pool -------------------------------------------------------
    def source_available(self, allocation) -> Decimal:
        consumed = sum(
            (
                c.consumption_amount
                for c in self.consumptions
                if c.source_allocation_id == allocation.id
                and self.consumption_active(c)
            ),
            ZERO,
        )
        return allocation.allocated_amount - consumed

    def available_credit(self) -> Decimal:
        total = ZERO
        for a in self.allocations:
            if (
                a.allocation_type == AllocationType.CREDIT
                and self.allocation_active(a)
                and self.payment_valid(a.payment)
            ):
                total += self.source_available(a)
        return total

    def active_allocation_total(self, payment) -> Decimal:
        return sum(
            (
                a.allocated_amount
                for a in self.allocations
                if a.payment_id == payment.id and self.allocation_active(a)
            ),
            ZERO,
        )

    def unallocated(self, payment) -> Decimal:
        return payment.amount - self.active_allocation_total(payment)

    # -- revenue (F1–F6) ---------------------------------------------------
    def cash_received(self) -> Decimal:
        """F2 at self.as_of (F1 when as_of == today)."""
        return sum(
            (p.amount for p in self.payments if self.payment_valid(p)), ZERO
        )

    def cash_received_range(self, d1: date, d2: date) -> Decimal:
        """F4 at self.as_of (F3 when as_of == today)."""
        return sum(
            (
                p.amount
                for p in self.payments
                if self.payment_valid(p) and d1 <= p.payment_date <= d2
            ),
            ZERO,
        )

    def cash_recorded(self) -> Decimal:
        """F5b audit-only predicate."""
        return sum(
            (p.amount for p in self.payments if self.payment_recorded(p)), ZERO
        )