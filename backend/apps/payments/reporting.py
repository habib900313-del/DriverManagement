"""Reporting: three distinct aggregates, F1–F6 revenue, conservation checks (§6/§8)."""

from datetime import date
from decimal import Decimal

from django.utils import timezone

from .ledger import (
    DriverLedger,
    ZERO,
    payment_recorded_as_of,
    payment_valid_as_of,
)
from .models import AllocationType, Payment, PaymentRefund
from .periods import consecutive_periods, fee_for_period
from apps.drivers.models import Driver

# How many upcoming quarters the driver profile table shows beyond the
# quarters the driver already has records for.
FUTURE_PERIOD_LOOKAHEAD = 4
FINANCIAL_REPORT_ARCHIVE_STATUSES = ("active", "archived", "all")

__all__ = [
    "driver_financial_summary",
    "period_state_payload",
    "conservation_report",
    "cash_revenue_report",
    "driver_period_coverage",
    "financial_report",
]


def _money(value: Decimal) -> str:
    return format(value, "f")


def period_state_payload(state) -> dict:
    return {
        "start": state.start.isoformat(),
        "end": state.end.isoformat(),
        "due_date": state.end.isoformat(),
        "is_overdue": state.end < timezone.localdate(),
        "fee": _money(state.fee),
        "remaining_own": _money(state.remaining_own),
        "balance": _money(state.balance),
        "reductions": _money(state.reductions),
        "cash_settled": _money(state.cash_settled),
        "credit_settled": _money(state.credit_settled),
        "net_waiver": _money(state.net_waiver),
        "net_transfer_out": _money(state.net_transfer_out),
        "net_transfer_in": _money(state.net_transfer_in),
        "transfers": [
            {
                "adjustment_id": tr.adjustment.id,
                "effective_date": tr.adjustment.effective_date.isoformat(),
                "original_amount": _money(tr.adjustment.amount),
                "reversed_total": _money(tr.reversed_total),
                "net": _money(tr.net),
                "remaining": _money(tr.remaining),
            }
            for tr in state.transfers
        ],
    }


def driver_financial_summary(driver, as_of: date | None = None) -> dict:
    ledger = DriverLedger(driver, as_of)
    states = ledger.all_period_states()
    today = ledger.as_of
    current = next((s for s in states if s.start <= today <= s.end), None)
    current_obligation = current.balance if current else ZERO
    overdue_debt = sum((s.balance for s in states if s.end < today), ZERO)
    total_balance = sum((s.balance for s in states), ZERO)
    return {
        "driver_id": driver.id,
        "as_of": today.isoformat(),
        "current_obligation": _money(current_obligation),
        "overdue_debt": _money(overdue_debt),
        "driver_total_balance": _money(total_balance),
        "available_credit": _money(ledger.available_credit()),
        "cash_received": _money(ledger.cash_received()),
        "periods": [period_state_payload(s) for s in states],
    }


def conservation_report(driver, as_of: date | None = None) -> dict:
    """Verify (P)(CR)(O)(C)(S)(T)(R) for a driver at as_of (§6.3)."""
    ledger = DriverLedger(driver, as_of)
    states = ledger.all_period_states()

    total_fees = sum((s.fee for s in states), ZERO)
    outstanding = sum((s.balance for s in states), ZERO)
    waived = sum((s.net_waiver for s in states), ZERO)
    settled_cash = sum((s.cash_settled for s in states), ZERO)
    settled_credit = sum((s.credit_settled for s in states), ZERO)

    valid_payments = [p for p in ledger.payments if ledger.payment_valid(p)]
    cash_received = sum(
        (ledger.net_payment_amount(payment) for payment in valid_payments), ZERO
    )
    consumed = sum(
        (
            c.consumption_amount
            for c in ledger.consumptions
            if ledger.consumption_active(c)
            and ledger.allocation_active(c.source_allocation)
            and ledger.payment_valid(c.source_allocation.payment)
        ),
        ZERO,
    )
    available = ledger.available_credit()
    # Credit cash that was absorbed by transfer overflow is already counted in
    # settled_cash (via PeriodState.cash_settled); subtract it from available to
    # avoid double counting in equation C. Credit that was NOT absorbed (no
    # transfers to absorb it) remains in available and is correctly counted.
    total_credit_cash_absorbed = sum((s.credit_cash_absorbed for s in states), ZERO)
    available_for_eq_c = available - total_credit_cash_absorbed
    unallocated = sum((ledger.unallocated(p) for p in valid_payments), ZERO)

    # (P) per payment and (CR) per credit source
    payment_checks = []
    for p in valid_payments:
        net_amount = ledger.net_payment_amount(p)
        active_total = ledger.active_allocation_total(p)
        fee_alloc = sum(
            (
                a.allocated_amount
                for a in ledger.allocations
                if a.payment_id == p.id
                and a.allocation_type == AllocationType.FEE_PERIOD
                and ledger.allocation_active(a)
            ),
            ZERO,
        )
        credit_alloc = sum(
            (
                a.allocated_amount
                for a in ledger.allocations
                if a.payment_id == p.id
                and a.allocation_type == AllocationType.CREDIT
                and ledger.allocation_active(a)
            ),
            ZERO,
        )
        payment_checks.append(
            {
                "payment_id": p.id,
                "amount": _money(net_amount),
                "fee_allocated": _money(fee_alloc),
                "credit_allocated": _money(credit_alloc),
                "unallocated": _money(net_amount - active_total),
                "cap_ok": active_total <= net_amount,
                "partition_ok": net_amount == fee_alloc + credit_alloc + (net_amount - active_total),
            }
        )

    credit_checks = []
    for a in ledger.allocations:
        if a.allocation_type == AllocationType.CREDIT and ledger.allocation_active(a):
            avail = ledger.source_available(a)
            used = a.allocated_amount - avail
            credit_checks.append(
                {
                    "allocation_id": a.id,
                    "allocated": _money(a.allocated_amount),
                    "consumed": _money(used),
                    "available": _money(avail),
                    "ok": avail >= ZERO and used + avail == a.allocated_amount,
                }
            )

    # (R) cumulative reversal caps
    reversal_checks = []
    for original in ledger.adjustments:
        if original.reverses_adjustment_id is not None:
            continue
        reversed_total = sum(
            (
                r.amount
                for r in ledger.adjustments
                if r.reverses_adjustment_id == original.id
            ),
            ZERO,
        )
        reversal_checks.append(
            {
                "adjustment_id": original.id,
                "original_amount": _money(original.amount),
                "reversed_total": _money(reversed_total),
                "ok": reversed_total <= original.amount,
            }
        )

    net_out = sum((s.net_transfer_out for s in states), ZERO)
    net_in = sum((s.net_transfer_in for s in states), ZERO)

    equations = {
        "O": {
            "outstanding_debt": _money(outstanding),
            "waived": _money(waived),
            "settled_by_cash": _money(settled_cash),
            "settled_by_credit": _money(settled_credit),
            "total_fee_obligations": _money(total_fees),
            "ok": outstanding + waived + settled_cash + settled_credit == total_fees,
        },
        "C": {
            "cash_received": _money(cash_received),
            "settled_by_cash": _money(settled_cash),
            "consumed_credit": _money(consumed),
            "available_credit": _money(available),
            "unallocated_cash": _money(unallocated),
            "ok": cash_received == settled_cash + consumed + available_for_eq_c + unallocated,
        },
        "S": {
            "settled_by_credit": _money(settled_credit),
            "consumed_credit": _money(consumed),
            "ok": settled_credit == consumed,
        },
        "T": {
            "net_transfer_out": _money(net_out),
            "net_transfer_in": _money(net_in),
            "ok": net_out == net_in,
        },
    }
    all_ok = (
        all(eq["ok"] for eq in equations.values())
        and all(c["cap_ok"] and c["partition_ok"] for c in payment_checks)
        and all(c["ok"] for c in credit_checks)
        and all(c["ok"] for c in reversal_checks)
    )
    return {
        "driver_id": driver.id,
        "as_of": ledger.as_of.isoformat(),
        "all_ok": all_ok,
        "equations": equations,
        "payments": payment_checks,
        "credit_sources": credit_checks,
        "reversals": reversal_checks,
    }


def driver_period_coverage(
    driver,
    as_of: date | None = None,
    lookahead: int = FUTURE_PERIOD_LOOKAHEAD,
) -> dict:
    """Paid / total / remaining for every quarter of a driver's era.

    Covers the quarters the driver already has records for plus a look-ahead
    of upcoming quarters, so the manager sees past, current and future
    quarters in one table.

    * ``paid`` — the amount actually booked against the quarter: its fee
      allocations plus the credit consumed on it.
    * ``total`` — the quarter's fee.
    * ``remaining`` — what is still owed for that quarter.
    """
    d = as_of or timezone.localdate()
    ledger = DriverLedger(driver, d)

    periods = list(ledger.periods)
    if periods:
        periods += consecutive_periods(driver, periods[-1][0], lookahead + 1)[1:]

    fee_allocated: dict = {}
    for allocation in ledger.allocations:
        if allocation.allocation_type != AllocationType.FEE_PERIOD:
            continue
        if not ledger.allocation_active(allocation):
            continue
        if not ledger.payment_valid(allocation.payment):
            continue
        key = allocation.target_period_start
        fee_allocated[key] = fee_allocated.get(key, ZERO) + allocation.allocated_amount

    credit_paid: dict = {}
    for consumption in ledger.consumptions:
        if not ledger.consumption_active(consumption):
            continue
        if not ledger.allocation_active(consumption.source_allocation):
            continue
        if not ledger.payment_valid(consumption.source_allocation.payment):
            continue
        key = consumption.target_period_start
        credit_paid[key] = credit_paid.get(key, ZERO) + consumption.consumption_amount

    rows = []
    for start, end in periods:
        paid = fee_allocated.get(start, ZERO) + credit_paid.get(start, ZERO)
        fee = fee_for_period(start)
        remaining = max(ZERO, fee - paid)
        allocations = [
            {
                "id": a.id,
                "payment_id": a.payment_id,
                "amount": _money(a.allocated_amount),
                "effective_date": a.effective_date.isoformat(),
                "payment_date": a.payment.payment_date.isoformat(),
                "receipt_number": a.payment.receipt_number,
                "description": a.payment.description,
                "payment_amount": _money(a.payment.amount),
                "reversed_at": a.reversed_at.isoformat() if a.reversed_at else None,
                "reversal_reason": a.reversal_reason,
            }
            for a in ledger.allocations
            if a.allocation_type == AllocationType.FEE_PERIOD
            and a.target_period_start == start
        ]
        consumptions = [
            {
                "id": c.id,
                "amount": _money(c.consumption_amount),
                "effective_date": c.effective_date.isoformat(),
                "source_allocation_id": c.source_allocation_id,
                "reason": c.reason,
                "reversed_at": c.reversed_at.isoformat() if c.reversed_at else None,
            }
            for c in ledger.consumptions
            if c.target_period_start == start
        ]
        if fee <= 0:
            status = "unpaid"
        elif paid >= fee:
            status = "paid"
        elif paid > 0:
            status = "partial"
        else:
            status = "unpaid"
        rows.append(
            {
                "start": start.isoformat(),
                "end": end.isoformat(),
                "due_date": end.isoformat(),
                "total": _money(fee),
                "paid": _money(paid),
                "remaining": _money(remaining),
                "percent": int(min(100, (paid / fee * 100))) if fee > 0 else 0,
                "status": status,
                "is_overdue": end < d,
                "is_current": start <= d <= end,
                "is_future": start > d,
                "allocations": allocations,
                "consumptions": consumptions,
            }
        )

    return {
        "driver_id": driver.id,
        "as_of": d.isoformat(),
        "periods": rows,
    }


def cash_revenue_report(
    as_of: date | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    driver_ids: set[int] | None = None,
) -> dict:
    """Cash revenue, optionally scoped to drivers; no range => F2/F1, range => F4/F3."""
    d = as_of or timezone.localdate()
    payment_query = Payment.objects.all()
    refund_query = PaymentRefund.objects.select_related("payment").filter(
        effective_date__lte=d
    )
    if driver_ids is not None:
        payment_query = payment_query.filter(driver_id__in=driver_ids)
        refund_query = refund_query.filter(payment__driver_id__in=driver_ids)

    payments = list(payment_query)
    valid = [p for p in payments if payment_valid_as_of(p, d)]
    refunds = list(refund_query)
    valid_refunds = [
        refund
        for refund in refunds
        if payment_valid_as_of(refund.payment, d)
    ]
    if date_from is not None and date_to is not None:
        valid = [p for p in valid if date_from <= p.payment_date <= date_to]
        valid_refunds = [
            refund
            for refund in valid_refunds
            if date_from <= refund.refund_date <= date_to
        ]
    total = sum((p.amount for p in valid), ZERO) - sum(
        (refund.amount for refund in valid_refunds), ZERO
    )
    recorded = sum(
        (
            p.amount
            for p in payments
            if payment_recorded_as_of(p, d)
            and (
                date_from is None
                or date_to is None
                or date_from <= p.payment_date <= date_to
            )
        ),
        ZERO,
    )
    recorded_refunds = sum(
        (
            refund.amount
            for refund in valid_refunds
            if payment_recorded_as_of(refund.payment, d)
            and timezone.localtime(refund.created_at).date() <= d
        ),
        ZERO,
    )
    recorded -= recorded_refunds
    return {
        "as_of": d.isoformat(),
        "date_from": date_from.isoformat() if date_from else None,
        "date_to": date_to.isoformat() if date_to else None,
        "cash_revenue": _money(total),
        "recorded_as_of_audit": _money(recorded),
        "payment_count": len(valid),
        # Only the number of paying drivers — never their identities.
        "driver_count": len({p.driver_id for p in valid}),
        "by_month": _revenue_by_month(valid, valid_refunds),
    }


def _revenue_by_month(payments, refunds=()) -> list[dict]:
    """Net cash revenue grouped by payment and refund dates."""
    buckets: dict = {}
    for payment in payments:
        key = payment.payment_date.strftime("%Y-%m")
        entry = buckets.setdefault(key, {"month": key, "total": ZERO, "count": 0})
        entry["total"] += payment.amount
        entry["count"] += 1
    for refund in refunds:
        key = refund.refund_date.strftime("%Y-%m")
        entry = buckets.setdefault(key, {"month": key, "total": ZERO, "count": 0})
        entry["total"] -= refund.amount
    return [
        {
            "month": entry["month"],
            "total": _money(entry["total"]),
            "count": entry["count"],
        }
        for entry in sorted(buckets.values(), key=lambda item: item["month"])
    ]


def financial_report(
    date_from: date | None = None,
    date_to: date | None = None,
    as_of: date | None = None,
    archive_status: str = "active",
) -> dict:
    """Consolidated financial report over an optional date range.

    Range semantics
    ---------------
    * payments and revenue are range-scoped (F4): a payment counts when it is
      valid at ``as_of`` and its ``payment_date`` lies inside
      ``[date_from, date_to]``.
    * debt and credit are as-of positions — a balance belongs to a moment, not
      to a range, so they are reported at ``as_of``. The range additionally
      scopes ``fee_in_range``: the fee obligations of the periods that *start*
      inside the range.
    * every driver is listed with its as-of position next to the range-scoped
      payment totals, so the report shows both the period activity and the
      resulting financial status.

    ``archive_status`` controls which drivers contribute to every aggregate:
    active drivers, archived drivers, or all drivers. The report is read-only
    and reuses the existing ledger and conservation formulas.
    """
    d = as_of or timezone.localdate()
    if archive_status not in FINANCIAL_REPORT_ARCHIVE_STATUSES:
        raise ValueError(f"Unsupported archive_status: {archive_status}")

    driver_query = Driver.objects.order_by("id")
    if archive_status == "active":
        driver_query = driver_query.filter(is_deleted=False, status=True)
    elif archive_status == "archived":
        driver_query = driver_query.filter(is_deleted=True)
    report_drivers = list(driver_query)
    driver_ids = {driver.id for driver in report_drivers}

    def _in_range(payment):
        if date_from is not None and payment.payment_date < date_from:
            return False
        if date_to is not None and payment.payment_date > date_to:
            return False
        return True

    payments = list(
        Payment.objects.select_related("driver").filter(driver_id__in=driver_ids)
    )
    valid = [p for p in payments if payment_valid_as_of(p, d)]
    ranged = [p for p in valid if _in_range(p)]
    ranged_refunds = [
        refund
        for refund in PaymentRefund.objects.select_related("payment").filter(
            effective_date__lte=d,
            payment__driver_id__in=driver_ids,
        )
        if payment_valid_as_of(refund.payment, d)
        and (date_from is None or refund.refund_date >= date_from)
        and (date_to is None or refund.refund_date <= date_to)
    ]
    payments_total = sum((p.amount for p in ranged), ZERO) - sum(
        (refund.amount for refund in ranged_refunds), ZERO
    )

    revenue = cash_revenue_report(
        d, date_from, date_to, driver_ids=driver_ids
    )

    drivers = []
    total_balance = current_total = overdue_total = ZERO
    available_total = credit_allocated_total = fee_in_range_total = ZERO
    conserving = 0

    for driver in report_drivers:
        ledger = DriverLedger(driver, d)
        states = ledger.all_period_states()
        current = next((s for s in states if s.start <= d <= s.end), None)
        current_obligation = current.balance if current else ZERO
        overdue = sum((s.balance for s in states if s.end < d), ZERO)
        balance = sum((s.balance for s in states), ZERO)
        available = ledger.available_credit()
        credit_allocated = sum(
            (
                a.allocated_amount
                for a in ledger.allocations
                if a.allocation_type == AllocationType.CREDIT
                and ledger.allocation_active(a)
                and ledger.payment_valid(a.payment)
            ),
            ZERO,
        )
        fee_in_range = sum(
            (
                s.fee
                for s in states
                if (date_from is None or s.start >= date_from)
                and (date_to is None or s.start <= date_to)
            ),
            ZERO,
        )
        driver_payments = [p for p in ranged if p.driver_id == driver.id]
        driver_refunds = [
            refund for refund in ranged_refunds if refund.payment.driver_id == driver.id
        ]
        driver_total = sum((p.amount for p in driver_payments), ZERO) - sum(
            (refund.amount for refund in driver_refunds), ZERO
        )
        ok = bool(conservation_report(driver, d)["all_ok"])
        conserving += int(ok)

        drivers.append(
            {
                "driver_id": driver.id,
                "driver_code": driver.driver_code,
                "full_name": driver.full_name,
                "payments_count": len(driver_payments),
                "payments_total": _money(driver_total),
                "total_balance": _money(balance),
                "current_obligation": _money(current_obligation),
                "overdue_debt": _money(overdue),
                "available_credit": _money(available),
                "credit_allocated": _money(credit_allocated),
                "fee_in_range": _money(fee_in_range),
                "conservation_ok": ok,
            }
        )

        total_balance += balance
        current_total += current_obligation
        overdue_total += overdue
        available_total += available
        credit_allocated_total += credit_allocated
        fee_in_range_total += fee_in_range

    return {
        "as_of": d.isoformat(),
        "date_from": date_from.isoformat() if date_from else None,
        "date_to": date_to.isoformat() if date_to else None,
        "archive_status": archive_status,
        "payments": {
            "count": len(ranged),
            "total_amount": _money(payments_total),
        },
        "revenue": {
            "cash_revenue": revenue["cash_revenue"],
            "recorded_as_of_audit": revenue["recorded_as_of_audit"],
        },
        "debt": {
            "total_balance": _money(total_balance),
            "current_obligation": _money(current_total),
            "overdue_debt": _money(overdue_total),
            "fee_in_range": _money(fee_in_range_total),
        },
        "credit": {
            "available_total": _money(available_total),
            "allocated_total": _money(credit_allocated_total),
        },
        "drivers": drivers,
        "totals": {
            "driver_count": len(drivers),
            "drivers_conserving": conserving,
        },
    }