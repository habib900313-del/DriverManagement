"""Financial API routes mounted at /api/ (before the drivers include)."""

from django.urls import path

from . import views

urlpatterns = [
    path("payments/", views.PaymentListCreateView.as_view(), name="payment-list"),
    path("payments/<int:pk>/", views.PaymentDetailView.as_view(), name="payment-detail"),
    path("payments/<int:pk>/void/", views.PaymentVoidView.as_view(), name="payment-void"),
    path("payments/<int:pk>/correct/", views.PaymentCorrectView.as_view(), name="payment-correct"),
    path("allocations/<int:pk>/correct/", views.AllocationCorrectView.as_view(), name="allocation-correct"),
    path("allocations/<int:pk>/correct-credit/", views.AllocationCorrectCreditView.as_view(), name="allocation-correct-credit"),
    path("credits/consume/", views.CreditConsumeView.as_view(), name="credit-consume"),
    path("adjustments/", views.AdjustmentListCreateView.as_view(), name="adjustment-list"),
    path("adjustments/<int:pk>/reverse/", views.AdjustmentReverseView.as_view(), name="adjustment-reverse"),
    path("adjustments/<int:pk>/unsettle-and-reverse/", views.AdjustmentUnsettleReverseView.as_view(), name="adjustment-unsettle-reverse"),
    path("fee-schedule/", views.FeeScheduleListCreateView.as_view(), name="fee-schedule"),
    path("reports/cash-revenue/", views.CashRevenueReportView.as_view(), name="cash-revenue"),
    path("reports/financial/", views.FinancialReportView.as_view(), name="financial-report"),
    path("drivers/<int:pk>/financial-summary/", views.DriverFinancialSummaryView.as_view(), name="driver-financial-summary"),
    path("drivers/<int:pk>/periods/", views.DriverPeriodsView.as_view(), name="driver-periods"),
    path("drivers/<int:pk>/period-coverage/", views.DriverPeriodCoverageView.as_view(), name="driver-period-coverage"),
    path("drivers/<int:pk>/conservation/", views.DriverConservationView.as_view(), name="driver-conservation"),
    path("drivers/<int:pk>/fee-history/", views.DriverFeeHistoryView.as_view(), name="driver-fee-history"),
    path("drivers/<int:pk>/fee-start-date/", views.DriverFeeStartDateView.as_view(), name="driver-fee-start-date"),
    # Online Payments (independent from guaranteed driver financial system)
    path("online-payments/", views.OnlinePaymentListCreateView.as_view(), name="online-payment-list"),
    path("online-payments/<int:pk>/", views.OnlinePaymentDetailView.as_view(), name="online-payment-detail"),
    path("online-payments/<int:pk>/void/", views.OnlinePaymentVoidView.as_view(), name="online-payment-void"),
    path("online-payments/<int:pk>/correct/", views.OnlinePaymentCorrectView.as_view(), name="online-payment-correct"),
    path("online-payments/summary/", views.OnlinePaymentSummaryView.as_view(), name="online-payment-summary"),
]