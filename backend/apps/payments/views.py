"""Financial API views (§10). IsAuthenticated + CSRF; actors from request.user.

No DELETE endpoints exist. Status changes only via action endpoints with a
required reason. FinancialError → 400 {detail, code}; lock contention → 409.
"""

from django.db import IntegrityError, OperationalError, transaction, models
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated

from .permissions import IsManager
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.activity import log_activity
from apps.core.models import ActivityLog
from apps.drivers.models import Driver, DriverFeeHistory

from . import services
from .models import (
    Adjustment,
    FeeSchedule,
    OnlinePayment,
    OnlinePaymentStatus,
    Payment,
    PaymentAllocation,
)
from .periods import consecutive_periods, fee_for_period, reconstruct_periods
from .reporting import (
    FINANCIAL_REPORT_ARCHIVE_STATUSES,
    cash_revenue_report,
    conservation_report,
    driver_financial_summary,
    driver_period_coverage,
    financial_report,
)
from .serializers import (
    AdjustmentInput,
    AdjustmentSerializer,
    ConsumeCreditInput,
    CorrectAllocationInput,
    CorrectCreditInput,
    CorrectPaymentInput,
    DriverFeeHistorySerializer,
    FeeScheduleInput,
    FeeScheduleSerializer,
    FeeStartDateInput,
    OnlinePaymentCorrectInput,
    OnlinePaymentInput,
    OnlinePaymentSerializer,
    OnlinePaymentVoidInput,
    PaymentRefundInput,
    PaymentRefundSerializer,
    PaymentSerializer,
    ReasonInput,
    ReceivePaymentInput,
    ReverseAdjustmentInput,
)
from .services import FinancialError


def _parse_date_param(request, name):
    raw = request.query_params.get(name, "").strip()
    if not raw:
        return None
    from datetime import date

    try:
        return date.fromisoformat(raw)
    except ValueError:
        raise FinancialError(f"پارامتر تاریخ {name} معتبر نیست (YYYY-MM-DD).", "invalid_date")


def _money(value):
    return format(value, "f")


def _target_period(data, start_key="target_period_start", end_key="target_period_end"):
    start = data.get(start_key)
    end = data.get(end_key)
    if start is None and end is None:
        return None
    if start is None or end is None:
        raise FinancialError("تاریخ شروع و پایان دوره هدف باید با هم ارائه شوند.", "invalid_period")
    return start, end


class FinancialAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def call_service(self, fn, serializer_class=None, status_code=status.HTTP_200_OK):
        try:
            result = fn()
        except FinancialError as exc:
            return Response(
                {"detail": exc.detail, "code": exc.code},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except IntegrityError:
            return Response(
                {"detail": "نقض یکپارچگی داده‌ها؛ عملیات انجام نشد."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except OperationalError:
            return Response(
                {"detail": "دیتابیس موقتاً قفل است؛ لطفاً دوباره تلاش کنید."},
                status=status.HTTP_409_CONFLICT,
            )
        if serializer_class is None:
            return Response(result, status=status_code)
        return Response(serializer_class(result).data, status=status_code)


# ---------------------------------------------------------------------------
# Payments
# ---------------------------------------------------------------------------
class PaymentListCreateView(FinancialAPIView, generics.ListAPIView):
    serializer_class = PaymentSerializer

    def get_permissions(self):
        if self.request.method in ("POST", "PUT", "PATCH", "DELETE"):
            return [IsManager()]
        return [IsAuthenticated()]

    def get_queryset(self):
        queryset = (
            Payment.objects.select_related("driver")
            .prefetch_related("refunds")
            .order_by("-created_at", "-id")
        )
        driver_id = self.request.query_params.get("driver_id")
        if driver_id and driver_id.isdigit():
            queryset = queryset.filter(driver_id=int(driver_id))
        date_from = self.request.query_params.get("date_from")
        if date_from:
            queryset = queryset.filter(payment_date__gte=date_from)
        date_to = self.request.query_params.get("date_to")
        if date_to:
            queryset = queryset.filter(payment_date__lte=date_to)
        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(
                models.Q(driver__driver_code__icontains=search)
                | models.Q(driver__full_name__icontains=search)
                | models.Q(receipt_number__icontains=search)
            )
        return queryset

    def post(self, request):
        serializer = ReceivePaymentInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        def run():
            driver = get_object_or_404(Driver, pk=data["driver_id"])
            if driver.driver_type != "guaranteed":
                raise FinancialError(
                    "فقط برای راننده‌های تضمینی مجاز است.", "driver_not_guaranteed"
                )
            target = _target_period(data)
            return services.receive_payment(
                driver=driver,
                amount=data["amount"],
                payment_date=data["payment_date"],
                user=request.user,
                target_period=target,
                periods_count=data.get("periods_count") or 1,
                receipt_number=data.get("receipt_number", ""),
                description=data.get("description", ""),
                idempotency_key=data.get("idempotency_key") or None,
            )

        return self.call_service(run, PaymentSerializer, status.HTTP_201_CREATED)


class PaymentDetailView(FinancialAPIView, generics.RetrieveAPIView):
    serializer_class = PaymentSerializer
    queryset = Payment.objects.select_related("driver").prefetch_related("refunds")


class PaymentVoidView(FinancialAPIView):
    permission_classes = [IsManager]

    def post(self, request, pk):
        payment = get_object_or_404(Payment, pk=pk)
        serializer = ReasonInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        return self.call_service(
            lambda: services.void_payment(
                payment=payment, user=request.user, reason=serializer.validated_data["reason"]
            ),
            PaymentSerializer,
        )


class PaymentCorrectView(FinancialAPIView):
    permission_classes = [IsManager]

    def post(self, request, pk):
        payment = get_object_or_404(Payment, pk=pk)
        serializer = CorrectPaymentInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        new_driver = None
        if data.get("new_driver_id"):
            new_driver = get_object_or_404(Driver, pk=data["new_driver_id"])

        def run():
            return services.correct_payment(
                payment=payment,
                user=request.user,
                reason=data["reason"],
                new_amount=data.get("new_amount"),
                new_driver=new_driver,
                new_payment_date=data.get("new_payment_date"),
                target_period=_target_period(data),
            )

        return self.call_service(run, PaymentSerializer, status.HTTP_201_CREATED)


class PaymentRefundView(FinancialAPIView):
    permission_classes = [IsManager]

    def post(self, request, pk):
        payment = get_object_or_404(Payment, pk=pk)
        serializer = PaymentRefundInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        return self.call_service(
            lambda: services.refund_payment(
                payment=payment,
                amount=data["amount"],
                refund_date=data["refund_date"],
                user=request.user,
                reason=data["reason"],
            ),
            PaymentRefundSerializer,
            status.HTTP_201_CREATED,
        )


# ---------------------------------------------------------------------------
# Allocations
# ---------------------------------------------------------------------------
class AllocationCorrectView(FinancialAPIView):
    permission_classes = [IsManager]

    def post(self, request, pk):
        allocation = get_object_or_404(PaymentAllocation, pk=pk)
        serializer = CorrectAllocationInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        return self.call_service(
            lambda: services.correct_allocation(
                allocation=allocation,
                user=request.user,
                reason=data["reason"],
                new_target_period=(
                    data["new_target_period_start"],
                    data["new_target_period_end"],
                ),
            ),
        )


class AllocationCorrectCreditView(FinancialAPIView):
    permission_classes = [IsManager]

    def post(self, request, pk):
        allocation = get_object_or_404(PaymentAllocation, pk=pk)
        serializer = CorrectCreditInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        def run():
            result = services.correct_credit_allocation(
                allocation=allocation,
                user=request.user,
                reason=data["reason"],
                new_credit_amount=data["new_credit_amount"],
                fee_allocations=data.get("fee_allocations", []),
                consumptions=data.get("consumptions", []),
            )
            from .serializers import PaymentAllocationSerializer, AllocationConsumptionSerializer

            return {
                "reversed_allocation_id": result["reversed_allocation"].id,
                "new_credit_allocation": (
                    PaymentAllocationSerializer(result["new_credit_allocation"]).data
                    if result["new_credit_allocation"]
                    else None
                ),
                "new_fee_allocations": PaymentAllocationSerializer(
                    result["new_fee_allocations"], many=True
                ).data,
                "new_consumptions": AllocationConsumptionSerializer(
                    result["new_consumptions"], many=True
                ).data,
            }

        return self.call_service(run)


# ---------------------------------------------------------------------------
# Credit consumption
# ---------------------------------------------------------------------------
class CreditConsumeView(FinancialAPIView):
    permission_classes = [IsManager]

    def post(self, request):
        serializer = ConsumeCreditInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        source = get_object_or_404(PaymentAllocation, pk=data["source_allocation_id"])

        def run():
            return services.consume_credit(
                source_allocation=source,
                amount=data["amount"],
                target_period=(data["target_period_start"], data["target_period_end"]),
                user=request.user,
                consumption_id=data.get("consumption_id") or None,
                reason=data.get("reason", ""),
            )

        from .serializers import AllocationConsumptionSerializer

        return self.call_service(run, AllocationConsumptionSerializer, status.HTTP_201_CREATED)


# ---------------------------------------------------------------------------
# Adjustments
# ---------------------------------------------------------------------------
class AdjustmentListCreateView(FinancialAPIView, generics.ListAPIView):
    serializer_class = AdjustmentSerializer

    def get_permissions(self):
        if self.request.method in ("POST", "PUT", "PATCH", "DELETE"):
            return [IsManager()]
        return [IsAuthenticated()]

    def get_queryset(self):
        queryset = Adjustment.objects.order_by("-created_at", "-id")
        driver_id = self.request.query_params.get("driver_id")
        if driver_id and driver_id.isdigit():
            queryset = queryset.filter(driver_id=int(driver_id))
        return queryset

    def post(self, request):
        serializer = AdjustmentInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        driver = get_object_or_404(Driver, pk=data["driver_id"])

        def run():
            source = (data["source_period_start"], data["source_period_end"])
            if data["adjustment_type"] == "waiver":
                return services.create_waiver(
                    driver=driver,
                    amount=data["amount"],
                    source_period=source,
                    user=request.user,
                    reason=data["reason"],
                )
            destination = _target_period(
                data, "destination_period_start", "destination_period_end"
            )
            if destination is None:
                raise FinancialError("دوره مقصد انتقال الزامی است.", "invalid_period")
            return services.create_transfer(
                driver=driver,
                amount=data["amount"],
                source_period=source,
                destination_period=destination,
                user=request.user,
                reason=data["reason"],
            )

        return self.call_service(run, AdjustmentSerializer, status.HTTP_201_CREATED)


class AdjustmentReverseView(FinancialAPIView):
    permission_classes = [IsManager]

    def post(self, request, pk):
        adjustment = get_object_or_404(Adjustment, pk=pk)
        serializer = ReverseAdjustmentInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        return self.call_service(
            lambda: services.reverse_adjustment(
                adjustment=adjustment,
                amount=data["amount"],
                user=request.user,
                reason=data["reason"],
            ),
            AdjustmentSerializer,
            status.HTTP_201_CREATED,
        )


class AdjustmentUnsettleReverseView(FinancialAPIView):
    permission_classes = [IsManager]

    def post(self, request, pk):
        adjustment = get_object_or_404(Adjustment, pk=pk)
        serializer = ReverseAdjustmentInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        return self.call_service(
            lambda: services.unsettle_and_reverse(
                adjustment=adjustment,
                amount=data["amount"],
                user=request.user,
                reason=data["reason"],
            ),
            AdjustmentSerializer,
            status.HTTP_201_CREATED,
        )


# ---------------------------------------------------------------------------
# Fee schedule
# ---------------------------------------------------------------------------
class FeeScheduleListCreateView(FinancialAPIView, generics.ListAPIView):
    serializer_class = FeeScheduleSerializer
    queryset = FeeSchedule.objects.order_by("-effective_from")

    def get_permissions(self):
        if self.request.method in ("POST", "PUT", "PATCH", "DELETE"):
            return [IsManager()]
        return [IsAuthenticated()]

    def post(self, request):
        serializer = FeeScheduleInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        return self.call_service(
            lambda: services.change_fee_schedule(
                amount=data["amount"],
                effective_from=data["effective_from"],
                user=request.user,
                reason=data["reason"],
            ),
            FeeScheduleSerializer,
            status.HTTP_201_CREATED,
        )


# ---------------------------------------------------------------------------
# Driver-scoped reports and fee history
# ---------------------------------------------------------------------------
class DriverFinancialSummaryView(FinancialAPIView):
    def get(self, request, pk):
        driver = get_object_or_404(Driver, pk=pk)
        return self.call_service(
            lambda: driver_financial_summary(driver, as_of=_parse_date_param(request, "as_of"))
        )


class DriverPeriodsView(FinancialAPIView):
    """The driver's quarters, used to pick a payment target.

    ``?lookahead=N`` adds the next N quarters, so a manager can also prepay
    an upcoming quarter.
    """

    def get(self, request, pk):
        driver = get_object_or_404(Driver, pk=pk)

        def run():
            try:
                lookahead = int(request.query_params.get("lookahead", 0))
            except (TypeError, ValueError):
                raise FinancialError("lookahead باید یک عدد صحیح باشد.", "invalid_date")
            lookahead = max(0, min(lookahead, 12))
            periods = reconstruct_periods(driver)
            if lookahead and periods:
                periods = periods + consecutive_periods(
                    driver, periods[-1][0], lookahead + 1
                )[1:]
            return {
                "driver_id": driver.id,
                "fee_start_date": driver.fee_start_date.isoformat(),
                "periods": [
                    {
                        "start": s.isoformat(),
                        "end": e.isoformat(),
                        "fee": _money(fee_for_period(s)),
                    }
                    for s, e in periods
                ],
            }

        return self.call_service(run)


class DriverPeriodCoverageView(FinancialAPIView):
    """Paid / total / remaining for every quarter of a driver's era.

    Used by the driver profile table: past, current and upcoming quarters
    with the payments booked on each of them.
    """

    def get(self, request, pk):
        driver = get_object_or_404(Driver, pk=pk)
        return self.call_service(
            lambda: driver_period_coverage(
                driver, as_of=_parse_date_param(request, "as_of")
            )
        )


class DriverConservationView(FinancialAPIView):
    def get(self, request, pk):
        driver = get_object_or_404(Driver, pk=pk)
        return self.call_service(
            lambda: conservation_report(driver, as_of=_parse_date_param(request, "as_of"))
        )


class DriverFeeHistoryView(FinancialAPIView, generics.ListAPIView):
    serializer_class = DriverFeeHistorySerializer

    def get_queryset(self):
        return DriverFeeHistory.objects.filter(driver_id=self.kwargs["pk"]).order_by(
            "changed_at", "id"
        )


class DriverFeeStartDateView(FinancialAPIView):
    permission_classes = [IsManager]

    def post(self, request, pk):
        driver = get_object_or_404(Driver, pk=pk)
        serializer = FeeStartDateInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        return self.call_service(
            lambda: services.change_fee_start_date(
                driver=driver,
                requested=data["requested_fee_start_date"],
                user=request.user,
                reason=data["reason"],
            ),
            DriverFeeHistorySerializer,
            status.HTTP_201_CREATED,
        )


class CashRevenueReportView(FinancialAPIView):
    def get(self, request):
        def run():
            as_of = _parse_date_param(request, "as_of")
            date_from = _parse_date_param(request, "date_from")
            date_to = _parse_date_param(request, "date_to")
            if (date_from is None) != (date_to is None):
                raise FinancialError(
                    "date_from و date_to باید با هم ارائه شوند.", "invalid_date"
                )
            if date_from and date_to and date_from > date_to:
                raise FinancialError("date_from نباید بعد از date_to باشد.", "invalid_date")
            if date_to and as_of and date_to > as_of:
                raise FinancialError("date_to نباید بعد از as_of باشد (F4).", "invalid_date")
            return cash_revenue_report(as_of=as_of, date_from=date_from, date_to=date_to)

        return self.call_service(run)


class FinancialReportView(FinancialAPIView):
    """Consolidated financial report for a selected date range.

    Returns payments, revenue, debts, credits and the per-driver financial
    status. Payments and revenue are scoped to the range; debt and credit are
    as-of positions (a balance belongs to a moment, not to a range).
    """

    def get(self, request):
        def run():
            as_of = _parse_date_param(request, "as_of")
            date_from = _parse_date_param(request, "date_from")
            date_to = _parse_date_param(request, "date_to")
            if (date_from is None) != (date_to is None):
                raise FinancialError(
                    "date_from و date_to باید با هم ارائه شوند.", "invalid_date"
                )
            if date_from and date_to and date_from > date_to:
                raise FinancialError("date_from نباید بعد از date_to باشد.", "invalid_date")
            if date_to and as_of and date_to > as_of:
                raise FinancialError("date_to نباید بعد از as_of باشد (F4).", "invalid_date")
            archive_status = request.query_params.get("archive_status", "active").strip()
            if archive_status not in FINANCIAL_REPORT_ARCHIVE_STATUSES:
                raise FinancialError(
                    "archive_status معتبر نیست.",
                    "invalid_archive_status",
                )
            return financial_report(
                date_from=date_from,
                date_to=date_to,
                as_of=as_of,
                archive_status=archive_status,
            )

        return self.call_service(run)


# ---------------------------------------------------------------------------
# Online Payments (independent from guaranteed driver financial system)
# ---------------------------------------------------------------------------
class OnlinePaymentListCreateView(FinancialAPIView):
    """List online payments or create a new one."""

    def get_permissions(self):
        if self.request.method in ("POST", "PUT", "PATCH", "DELETE"):
            return [IsManager()]
        return [IsAuthenticated()]

    def get_queryset(self):
        queryset = OnlinePayment.objects.select_related("driver").order_by(
            "-created_at", "-id"
        )
        driver_id = self.request.query_params.get("driver_id")
        if driver_id and driver_id.isdigit():
            queryset = queryset.filter(driver_id=int(driver_id))
        purpose = self.request.query_params.get("purpose", "").strip()
        if purpose:
            queryset = queryset.filter(purpose__icontains=purpose)
        date_from = _parse_date_param(self.request, "date_from")
        date_to = _parse_date_param(self.request, "date_to")
        if date_from:
            queryset = queryset.filter(payment_date__gte=date_from)
        if date_to:
            queryset = queryset.filter(payment_date__lte=date_to)
        return queryset

    def get(self, request):
        serializer = OnlinePaymentSerializer(self.get_queryset(), many=True)
        return self.call_service(
            lambda: {
                "total_count": len(serializer.data),
                "results": serializer.data,
            }
        )

    def post(self, request):
        serializer = OnlinePaymentInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        def run():
            with transaction.atomic():
                driver = get_object_or_404(
                    Driver.objects.select_for_update(), pk=data["driver_id"]
                )
                if driver.driver_type != "online":
                    raise FinancialError(
                        "فقط برای راننده‌های آنلاین مجاز است.", "driver_not_online"
                    )
                payment = OnlinePayment.objects.create(
                    driver=driver,
                    amount=data["amount"],
                    payment_date=data["payment_date"],
                    purpose=data["purpose"],
                    description=data.get("description", ""),
                    recorded_by=request.user,
                    status=OnlinePaymentStatus.RECEIVED,
                )
                log_activity(
                    actor=request.user,
                    action="online_payment_create",
                    module=ActivityLog.Module.PAYMENTS,
                    description=f"ثبت پرداخت آنلاین برای راننده «{driver.full_name}».",
                    target_type="online_payment",
                    target_id=payment.pk,
                    target_label=f"{driver.driver_code} — {driver.full_name}",
                    after_data={
                        "payment_id": payment.pk,
                        "driver_id": driver.pk,
                        "amount": payment.amount,
                        "payment_date": payment.payment_date,
                        "purpose": payment.purpose,
                        "status": payment.status,
                    },
                    request=request,
                )
            return payment

        return self.call_service(run, OnlinePaymentSerializer, status.HTTP_201_CREATED)


class OnlinePaymentDetailView(FinancialAPIView, generics.RetrieveAPIView):
    serializer_class = OnlinePaymentSerializer
    queryset = OnlinePayment.objects.select_related("driver")


class OnlinePaymentVoidView(FinancialAPIView):
    """Void an online payment (append-only, requires reason)."""

    permission_classes = [IsManager]

    def post(self, request, pk):
        payment = get_object_or_404(OnlinePayment, pk=pk)
        payment_id = payment.pk
        driver_id = payment.driver_id
        serializer = ReasonInput(data=request.data)
        serializer.is_valid(raise_exception=True)

        def run():
            with transaction.atomic():
                driver = get_object_or_404(
                    Driver.objects.select_for_update(), pk=driver_id
                )
                payment = get_object_or_404(
                    OnlinePayment.objects.select_for_update().select_related("driver"),
                    pk=payment_id,
                    driver_id=driver.pk,
                )
                if payment.status == OnlinePaymentStatus.VOIDED:
                    raise FinancialError(
                        "این پرداخت قبلاً باطل شده است.", "already_voided"
                    )
                now = timezone.now()
                payment.status = OnlinePaymentStatus.VOIDED
                payment.voided_at = now
                payment.voided_by = request.user
                payment.void_reason = serializer.validated_data["reason"]
                payment.save(
                    update_fields=[
                        "status", "voided_at", "voided_by", "void_reason"
                    ]
                )
                log_activity(
                    actor=request.user,
                    action="online_payment_void",
                    module=ActivityLog.Module.PAYMENTS,
                    description=(
                        f"ابطال پرداخت آنلاین راننده «{payment.driver.full_name}»."
                    ),
                    target_type="online_payment",
                    target_id=payment.pk,
                    target_label=payment.driver.driver_code,
                    before_data={"status": OnlinePaymentStatus.RECEIVED},
                    after_data={
                        "payment_id": payment.pk,
                        "amount": payment.amount,
                        "status": payment.status,
                        "reason": payment.void_reason,
                    },
                    request=request,
                )
            return payment

        return self.call_service(run, OnlinePaymentSerializer)


class OnlinePaymentCorrectView(FinancialAPIView):
    """Correct an online payment (append-only: original is marked, new row created).

    Mirrors the guaranteed W4 workflow: the original row is never mutated in
    place — it is stamped with `corrected` status and a replacement row
    references it via `correction_of`.
    """

    permission_classes = [IsManager]

    def post(self, request, pk):
        payment = get_object_or_404(OnlinePayment, pk=pk)
        payment_id = payment.pk
        driver_id = payment.driver_id
        serializer = OnlinePaymentCorrectInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        def run():
            with transaction.atomic():
                driver = get_object_or_404(
                    Driver.objects.select_for_update(), pk=driver_id
                )
                payment = get_object_or_404(
                    OnlinePayment.objects.select_for_update().select_related("driver"),
                    pk=payment_id,
                    driver_id=driver.pk,
                )
                if payment.status != OnlinePaymentStatus.RECEIVED:
                    raise FinancialError(
                        "فقط پرداخت دریافت‌شده قابل اصلاح است.", "already_invalid"
                    )
                new_amount = data.get("new_amount")
                if new_amount is None:
                    new_amount = payment.amount
                new_date = data.get("new_payment_date") or payment.payment_date
                if new_date > timezone.localdate():
                    raise FinancialError(
                        "تاریخ پرداخت نمی‌تواند در آینده باشد.", "invalid_date"
                    )
                now = timezone.now()
                payment.status = OnlinePaymentStatus.CORRECTED
                payment.corrected_at = now
                payment.corrected_by = request.user
                payment.correction_reason = data["reason"]
                payment.save(
                    update_fields=[
                        "status", "corrected_at", "corrected_by", "correction_reason"
                    ]
                )
                replacement = OnlinePayment.objects.create(
                    driver=payment.driver,
                    amount=new_amount,
                    payment_date=new_date,
                    purpose=data.get("new_purpose") or payment.purpose,
                    description=data.get("new_description", payment.description),
                    recorded_by=request.user,
                    status=OnlinePaymentStatus.RECEIVED,
                    correction_of=payment,
                )
                log_activity(
                    actor=request.user,
                    action="online_payment_correct",
                    module=ActivityLog.Module.PAYMENTS,
                    description=(
                        f"اصلاح پرداخت آنلاین راننده «{payment.driver.full_name}»."
                    ),
                    target_type="online_payment",
                    target_id=replacement.pk,
                    target_label=payment.driver.driver_code,
                    before_data={
                        "payment_id": payment.pk,
                        "amount": payment.amount,
                        "payment_date": payment.payment_date,
                        "status": OnlinePaymentStatus.CORRECTED,
                    },
                    after_data={
                        "payment_id": replacement.pk,
                        "amount": replacement.amount,
                        "payment_date": replacement.payment_date,
                        "correction_of": payment.pk,
                        "reason": data["reason"],
                    },
                    request=request,
                )
            return replacement

        return self.call_service(run, OnlinePaymentSerializer, status.HTTP_201_CREATED)


class OnlinePaymentSummaryView(FinancialAPIView):
    """Summary of online payments — total per driver and grand total."""

    def get(self, request):
        def run():
            queryset = OnlinePayment.objects.filter(
                status=OnlinePaymentStatus.RECEIVED
            )
            driver_id = self.request.query_params.get("driver_id")
            if driver_id and driver_id.isdigit():
                queryset = queryset.filter(driver_id=int(driver_id))

            from django.db.models import Sum

            total = queryset.aggregate(total=Sum("amount"))["total"] or 0
            driver_count = queryset.values("driver").distinct().count()

            per_driver = list(
                queryset.values(
                    "driver__driver_code", "driver__full_name"
                ).annotate(total=Sum("amount"), count=models.Count("id")).order_by(
                    "driver__driver_code"
                )
            )
            for item in per_driver:
                item["total"] = format(item["total"], "f")

            total_str = format(total, ".2f") if total is not None else "0.00"
            return {
                "total_amount": total_str,
                "total_count": queryset.count(),
                "driver_count": driver_count,
                "per_driver": per_driver,
            }

        return self.call_service(run)