"""Read-only admin for financial records (§10.2).

Financial records are append-only and all mutations flow through the atomic
service workflows; the admin is view-only (no add/change/delete) so it cannot
bypass the business rules or the audit trail.
"""

from django.contrib import admin

from .models import (
    Adjustment,
    AllocationConsumption,
    FeeSchedule,
    Payment,
    PaymentAllocation,
    PaymentRefund,
)


class ReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Payment)
class PaymentAdmin(ReadOnlyAdmin):
    list_display = ("id", "driver", "amount", "payment_date", "status", "created_at")
    list_filter = ("status",)
    search_fields = ("driver__driver_code", "driver__full_name", "receipt_number")
    date_hierarchy = "payment_date"


@admin.register(PaymentAllocation)
class PaymentAllocationAdmin(ReadOnlyAdmin):
    list_display = (
        "id",
        "payment",
        "allocation_type",
        "allocated_amount",
        "target_period_start",
        "reversed_at",
    )
    list_filter = ("allocation_type",)


@admin.register(PaymentRefund)
class PaymentRefundAdmin(ReadOnlyAdmin):
    list_display = ("id", "payment", "amount", "refund_date", "refunded_by", "created_at")
    list_filter = ("refund_date",)


@admin.register(AllocationConsumption)
class AllocationConsumptionAdmin(ReadOnlyAdmin):
    list_display = (
        "id",
        "source_allocation",
        "consumption_amount",
        "target_period_start",
        "consumed_by",
        "reversed_at",
    )


@admin.register(Adjustment)
class AdjustmentAdmin(ReadOnlyAdmin):
    list_display = (
        "id",
        "driver",
        "adjustment_type",
        "amount",
        "source_period_start",
        "destination_period_start",
        "effective_date",
    )
    list_filter = ("adjustment_type",)


@admin.register(FeeSchedule)
class FeeScheduleAdmin(ReadOnlyAdmin):
    list_display = ("id", "amount", "effective_from", "created_by", "created_at")