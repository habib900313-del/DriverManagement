"""Computed quarterly periods from the driver's era anchor (spec §8.2/§8.3, D3/D4).

There is no Period table. Periods are generated from the anchor:
    start_k = add_calendar_months(anchor, 3k)   (day-clamped)
    end_k   = start_{k+1} - 1 day
Every era change lands on the same grid (ceil_to_grid of the current grid), so
the original anchor reconstructs the union of all era period pairs by construction
— no overlap, no gap, no drift.
"""

import calendar
from datetime import date, timedelta, timedelta
from decimal import Decimal

from django.utils import timezone

from .models import FeeSchedule

DEFAULT_FEE = Decimal("600.00")


def add_calendar_months(value: date, months: int) -> date:
    """Calendar-month addition with day clamping (31 Jan + 3 months = 30 Apr)."""
    total = value.year * 12 + (value.month - 1) + months
    year, month = divmod(total, 12)
    month += 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def get_era_anchor(driver) -> date:
    """Original era anchor = first fee-history effective date (grid is invariant)."""
    first = driver.fee_history.order_by("changed_at", "id").first()
    if first is not None:
        return first.effective_fee_start_date
    return driver.fee_start_date


def iter_periods(anchor: date, until: date):
    """Yield (start, end) for every period with start <= until."""
    k = 0
    while True:
        start = add_calendar_months(anchor, 3 * k)
        if start > until:
            return
        next_start = add_calendar_months(anchor, 3 * (k + 1))
        yield start, next_start - timedelta(days=1)
        k += 1


def reconstruct_periods(driver, until: date | None = None) -> list[tuple[date, date]]:
    anchor = get_era_anchor(driver)
    if until is None:
        until = timezone.localdate()
    return list(iter_periods(anchor, until))


def period_containing(driver, on: date) -> tuple[date, date] | None:
    for start, end in reconstruct_periods(driver, until=on):
        if start <= on <= end:
            return start, end
    return None


def is_valid_period(driver, start: date, end: date) -> bool:
    """A target pair must be a reconstructed period of this driver (§8.2)."""
    horizon = max(start, timezone.localdate())
    return (start, end) in set(reconstruct_periods(driver, until=horizon))


def target_period_error(
    driver, start: date, end: date, *, allow_future: bool = False
) -> str | None:
    """Classify an allocation / consumption target period (spec §8.2).

    Returns ``None`` when the target is acceptable, otherwise a stable error
    code:

    * ``invalid_period`` — ``start`` is after ``end``.
    * ``unknown_period`` — the pair is not a period of this driver at all
      (not a member of the driver's reconstructed era grid).
    * ``future_period``  — the pair *is* a period of this driver but has not
      started yet.

    ``allow_future`` is used for the fee allocation path: paying for a quarter
    that has not started yet is a normal prepayment and is booked directly on
    that quarter, so the ledger can account for it. Credit *consumption* keeps
    the stricter rule, because consuming credit settles a debt that has
    already started.

    The membership test is performed against the driver's reconstructed period
    set, so a period that does not belong to the driver is reported
    separately from one that simply has not started yet.
    """
    if start > end:
        return "invalid_period"
    today = timezone.localdate()
    if (start, end) in set(reconstruct_periods(driver, until=today)):
        return None
    if (start, end) in set(reconstruct_periods(driver, until=max(start, today))):
        return None if allow_future else "future_period"
    return "unknown_period"


def consecutive_periods(driver, start: date, count: int) -> list[tuple[date, date]]:
    """`count` consecutive grid periods of `driver`, starting at `start`.

    `start` must already be one of the driver's reconstructed periods; the
    periods that follow it on the same era grid are returned in order. This
    is what lets a single payment cover several quarters.
    """
    if count < 1:
        return []
    anchor = get_era_anchor(driver)
    months = (start.year - anchor.year) * 12 + (start.month - anchor.month)
    if months < 0 or months % 3:
        return []
    k = months // 3
    periods = []
    for i in range(count):
        period_start = add_calendar_months(anchor, 3 * (k + i))
        period_end = add_calendar_months(anchor, 3 * (k + i + 1)) - timedelta(days=1)
        periods.append((period_start, period_end))
    return periods


def ceil_to_grid(anchor: date, value: date) -> date:
    """Smallest grid point (anchor + 3k months) >= value."""
    if value <= anchor:
        return anchor
    k = 0
    while add_calendar_months(anchor, 3 * k) < value:
        k += 1
    return add_calendar_months(anchor, 3 * k)


def compute_effective_anchor(driver, requested: date) -> date:
    """Era rule (D4): effective = ceil_to_grid(max(requested, current_period_end + 1))."""
    today = timezone.localdate()
    periods = reconstruct_periods(driver, until=today)
    anchor = get_era_anchor(driver)
    if periods:
        current_end = periods[-1][1]
        candidate = max(requested, current_end + timedelta(days=1))
    else:
        candidate = max(requested, anchor)
    return ceil_to_grid(anchor, candidate)


def fee_for_period(period_start: date) -> Decimal:
    """D5: amount of the latest FeeSchedule row with effective_from <= period.start."""
    row = (
        FeeSchedule.objects.filter(effective_from__lte=period_start)
        .order_by("-effective_from")
        .first()
    )
    if row is None:
        raise RuntimeError("FeeSchedule seed row missing — run payments migrations.")
    return row.amount