from django.contrib import admin

from .models import DriverFeeHistory


@admin.register(DriverFeeHistory)
class DriverFeeHistoryAdmin(admin.ModelAdmin):
    """Append-only era log; view-only (changes go through W10)."""

    list_display = (
        "id",
        "driver",
        "old_fee_start_date",
        "requested_fee_start_date",
        "effective_fee_start_date",
        "changed_by",
        "changed_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False