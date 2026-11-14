"""Read serializers and validated input serializers for the financial API.

Business rules are enforced atomically in services; input serializers only
validate shape/types. Actor fields (created_by/allocated_by/...) always come
from request.user in the view, never from the client (§10.1).
"""

from rest_framework import serializers

from apps.drivers.models import DriverFeeHistory

from .models import (
    Adjustment,
    AllocationConsumption,
    FeeSchedule,
    OnlinePayment,
    Payment,
    PaymentAllocation,
    validate_not_future_date,
)


# ---------------------------------------------------------------------------
# read serializers
# ---------------------------------------------------------------------------
class AllocationConsumptionSerializer(serializers.ModelSerializer):
    is_reversed = serializers.BooleanField(read_only=True)
    consumed_by_name = serializers.SerializerMethodField()

    class Meta:
        model = AllocationConsumption
        fields = [
            "id",
            "source_allocation",
            "consumption_amount",
            "target_period_start",
            "target_period_end",
            "effective_date",
            "consumption_id",
            "consumed_by",
            "consumed_by_name",
            "reason",
            "reversed_at",
            "reversal_reason",
            "is_reversed",
            "consumed_at",
        ]
        read_only_fields = fields

    def get_consumed_by_name(self, obj):
        return obj.consumed_by.get_full_name() or obj.consumed_by.username


class PaymentAllocationSerializer(serializers.ModelSerializer):
    is_reversed = serializers.BooleanField(read_only=True)
    consumptions = AllocationConsumptionSerializer(many=True, read_only=True)

    class Meta:
        model = PaymentAllocation
        fields = [
            "id",
            "payment",
            "allocation_type",
            "target_period_start",
            "target_period_end",
            "allocated_amount",
            "effective_date",
            "correction_of",
            "reversed_at",
            "reversal_reason",
            "is_reversed",
            "allocated_by",
            "created_at",
            "consumptions",
        ]
        read_only_fields = fields


class PaymentSerializer(serializers.ModelSerializer):
    is_void = serializers.BooleanField(read_only=True)
    driver_code = serializers.CharField(source="driver.driver_code", read_only=True)
    driver_name = serializers.CharField(source="driver.full_name", read_only=True)
    allocations = PaymentAllocationSerializer(many=True, read_only=True)

    class Meta:
        model = Payment
        fields = [
            "id",
            "driver",
            "driver_code",
            "driver_name",
            "amount",
            "payment_date",
            "effective_date",
            "receipt_number",
            "idempotency_key",
            "status",
            "is_void",
            "correction_of",
            "void_reason",
            "correction_reason",
            "voided_at",
            "corrected_at",
            "created_by",
            "created_at",
            "updated_at",
            "allocations",
        ]
        read_only_fields = fields


class AdjustmentSerializer(serializers.ModelSerializer):
    type_label = serializers.CharField(source="get_adjustment_type_display", read_only=True)

    class Meta:
        model = Adjustment
        fields = [
            "id",
            "driver",
            "adjustment_type",
            "type_label",
            "amount",
            "source_period_start",
            "source_period_end",
            "destination_period_start",
            "destination_period_end",
            "reverses_adjustment",
            "reason",
            "effective_date",
            "created_by",
            "created_at",
        ]
        read_only_fields = fields


class FeeScheduleSerializer(serializers.ModelSerializer):
    class Meta:
        model = FeeSchedule
        fields = ["id", "amount", "effective_from", "reason", "created_by", "created_at"]
        read_only_fields = fields


class DriverFeeHistorySerializer(serializers.ModelSerializer):
    changed_by_name = serializers.SerializerMethodField()

    class Meta:
        model = DriverFeeHistory
        fields = [
            "id",
            "driver",
            "old_fee_start_date",
            "requested_fee_start_date",
            "effective_fee_start_date",
            "reason",
            "changed_by",
            "changed_by_name",
            "changed_at",
        ]
        read_only_fields = fields

    def get_changed_by_name(self, obj):
        return obj.changed_by.get_full_name() or obj.changed_by.username


# ---------------------------------------------------------------------------
# input serializers
# ---------------------------------------------------------------------------
class ReceivePaymentInput(serializers.Serializer):
    driver_id = serializers.IntegerField()
    amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    payment_date = serializers.DateField()
    target_period_start = serializers.DateField(required=False, allow_null=True)
    target_period_end = serializers.DateField(required=False, allow_null=True)
    periods_count = serializers.IntegerField(
        required=False,
        default=1,
        min_value=1,
        max_value=24,
        help_text="How many consecutive quarters the payment covers, starting at the target period.",
    )
    receipt_number = serializers.CharField(required=False, allow_blank=True, default="")
    idempotency_key = serializers.CharField(required=False, allow_blank=True, default="")


class ReasonInput(serializers.Serializer):
    reason = serializers.CharField()


class CorrectPaymentInput(serializers.Serializer):
    reason = serializers.CharField()
    new_amount = serializers.DecimalField(
        max_digits=10, decimal_places=2, required=False, allow_null=True
    )
    new_driver_id = serializers.IntegerField(required=False, allow_null=True)
    new_payment_date = serializers.DateField(required=False, allow_null=True)
    target_period_start = serializers.DateField(required=False, allow_null=True)
    target_period_end = serializers.DateField(required=False, allow_null=True)


class CorrectAllocationInput(serializers.Serializer):
    reason = serializers.CharField()
    new_target_period_start = serializers.DateField()
    new_target_period_end = serializers.DateField()


class PeriodAmountInput(serializers.Serializer):
    start = serializers.DateField()
    end = serializers.DateField()
    amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    reason = serializers.CharField(required=False, allow_blank=True, default="")


class CorrectCreditInput(serializers.Serializer):
    reason = serializers.CharField()
    new_credit_amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    fee_allocations = PeriodAmountInput(many=True, required=False, default=list)
    consumptions = PeriodAmountInput(many=True, required=False, default=list)


class ConsumeCreditInput(serializers.Serializer):
    source_allocation_id = serializers.IntegerField()
    amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    target_period_start = serializers.DateField()
    target_period_end = serializers.DateField()
    consumption_id = serializers.CharField(required=False, allow_blank=True, default="")
    reason = serializers.CharField(required=False, allow_blank=True, default="")


class AdjustmentInput(serializers.Serializer):
    driver_id = serializers.IntegerField()
    adjustment_type = serializers.ChoiceField(choices=["waiver", "transfer"])
    amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    source_period_start = serializers.DateField()
    source_period_end = serializers.DateField()
    destination_period_start = serializers.DateField(required=False, allow_null=True)
    destination_period_end = serializers.DateField(required=False, allow_null=True)
    reason = serializers.CharField()


class ReverseAdjustmentInput(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    reason = serializers.CharField()


class FeeScheduleInput(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    effective_from = serializers.DateField()
    reason = serializers.CharField()


class FeeStartDateInput(serializers.Serializer):
    requested_fee_start_date = serializers.DateField()
    reason = serializers.CharField()


# ---------------------------------------------------------------------------
# Online Payment serializers
# ---------------------------------------------------------------------------
class OnlinePaymentSerializer(serializers.ModelSerializer):
    """Read serializer for OnlinePayment."""

    driver_code = serializers.CharField(source="driver.driver_code", read_only=True)
    driver_name = serializers.CharField(source="driver.full_name", read_only=True)
    recorded_by_name = serializers.SerializerMethodField()
    voided_by_name = serializers.SerializerMethodField()
    corrected_by_name = serializers.SerializerMethodField()

    class Meta:
        model = OnlinePayment
        fields = [
            "id",
            "driver",
            "driver_code",
            "driver_name",
            "amount",
            "payment_date",
            "purpose",
            "description",
            "recorded_by",
            "recorded_by_name",
            "status",
            "is_void",
            "void_reason",
            "voided_at",
            "voided_by",
            "voided_by_name",
            "correction_of",
            "correction_reason",
            "corrected_at",
            "corrected_by",
            "corrected_by_name",
            "created_at",
        ]
        read_only_fields = fields

    def get_recorded_by_name(self, obj):
        return obj.recorded_by.get_full_name() or obj.recorded_by.username

    def get_voided_by_name(self, obj):
        if obj.voided_by:
            return obj.voided_by.get_full_name() or obj.voided_by.username
        return None

    def get_corrected_by_name(self, obj):
        if obj.corrected_by:
            return obj.corrected_by.get_full_name() or obj.corrected_by.username
        return None


class OnlinePaymentInput(serializers.Serializer):
    """Input serializer for creating an online payment."""

    driver_id = serializers.IntegerField()
    amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    payment_date = serializers.DateField()
    purpose = serializers.CharField()
    description = serializers.CharField(required=False, allow_blank=True, default="")

    def validate_payment_date(self, value):
        validate_not_future_date(value)
        return value


class OnlinePaymentVoidInput(serializers.Serializer):
    """Input serializer for voiding an online payment."""

    reason = serializers.CharField()


class OnlinePaymentCorrectInput(serializers.Serializer):
    """Input serializer for correcting an online payment."""

    reason = serializers.CharField()
    new_amount = serializers.DecimalField(
        max_digits=10, decimal_places=2, required=False, allow_null=True
    )
    new_payment_date = serializers.DateField(required=False, allow_null=True)
    new_purpose = serializers.CharField(required=False, allow_blank=True, default="")
    new_description = serializers.CharField(required=False, allow_blank=True, default="")