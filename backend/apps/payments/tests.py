"""Financial module tests: numerical appendix (§11), V1–V10 (§12), conservation,
as-of reporting, and API protection. Runs only on the isolated Django test DB.
"""

import sqlite3
import threading
import uuid
from datetime import date, datetime, timedelta
from datetime import timezone as dt_timezone
from decimal import Decimal
from unittest import mock

from django.contrib.auth.models import User
from django.db import connection, connections, transaction
from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from apps.drivers.models import Driver, DriverFeeHistory

from . import services
from .ledger import DriverLedger
from .models import (
    Adjustment,
    AdjustmentType,
    AllocationConsumption,
    AllocationType,
    FeeSchedule,
    OnlinePayment,
    OnlinePaymentStatus,
    Payment,
    PaymentAllocation,
    PaymentStatus,
)
from .periods import (
    add_calendar_months,
    compute_effective_anchor,
    fee_for_period,
    reconstruct_periods,
)
from .reporting import (
    cash_revenue_report,
    conservation_report,
    driver_financial_summary,
    financial_report,
)
from .services import FinancialError

FIXED_TODAY = date(2026, 11, 10)
FIXED_NOW = datetime(2026, 11, 10, 8, 0, tzinfo=dt_timezone.utc)
D = Decimal


class FinancialTestBase(TestCase):
    """Deterministic clock + a driver anchored at 2026-01-01 (four periods by today)."""

    def setUp(self):
        patch_now = mock.patch.object(timezone, "now", return_value=FIXED_NOW)
        patch_today = mock.patch.object(timezone, "localdate", return_value=FIXED_TODAY)
        patch_now.start()
        patch_today.start()
        self.addCleanup(patch_now.stop)
        self.addCleanup(patch_today.stop)

        self.user = User.objects.create_user(
            username="admin", password="pass", is_superuser=True, is_staff=True
        )
        self._counter = 0
        self.driver = self.make_driver(date(2026, 1, 1))
        self.P1 = (date(2026, 1, 1), date(2026, 3, 31))
        self.P2 = (date(2026, 4, 1), date(2026, 6, 30))
        self.P3 = (date(2026, 7, 1), date(2026, 9, 30))
        self.P4 = (date(2026, 10, 1), date(2026, 12, 31))

    def make_driver(self, anchor, fee_start=None):
        self._counter += 1
        driver = Driver.objects.create(
            driver_code=f"D{self._counter}",
            full_name=f"راننده {self._counter}",
            father_name="پدر",
            phone="0700000000",
            tazkira_number=f"T{self._counter}",
            plate_number=f"پ{self._counter}",
            address="کابل",
            registration_date=anchor,
            fee_start_date=fee_start or anchor,
        )
        DriverFeeHistory.objects.create(
            driver=driver,
            old_fee_start_date=None,
            requested_fee_start_date=fee_start or anchor,
            effective_fee_start_date=fee_start or anchor,
            reason="ردیف اولیه تست",
            changed_by=self.user,
        )
        return driver

    def state(self, period, driver=None, as_of=None):
        return DriverLedger(driver or self.driver, as_of).period_state(*period)

    def receive(self, amount, period=None, driver=None, payment_date=FIXED_TODAY):
        return services.receive_payment(
            driver=driver or self.driver,
            amount=D(amount),
            payment_date=payment_date,
            user=self.user,
            target_period=period,
        )

    def transfer(self, amount, source, dest, driver=None):
        return services.create_transfer(
            driver=driver or self.driver,
            amount=D(amount),
            source_period=source,
            destination_period=dest,
            user=self.user,
            reason="انتقال تست",
        )

    def assertConserved(self, driver=None, as_of=None):
        report = conservation_report(driver or self.driver, as_of)
        self.assertTrue(
            report["all_ok"],
            f"conservation failed: {report['equations']}",
        )
        return report


class PeriodMathTests(FinancialTestBase):
    def test_calendar_month_clamping(self):
        self.assertEqual(add_calendar_months(date(2026, 1, 31), 3), date(2026, 4, 30))
        self.assertEqual(add_calendar_months(date(2026, 1, 1), 3), date(2026, 4, 1))

    def test_reconstruction_contiguous(self):
        periods = reconstruct_periods(self.driver, until=FIXED_TODAY)
        self.assertEqual(periods[0], self.P1)
        self.assertEqual(periods[1], self.P2)
        self.assertEqual(periods[2], self.P3)
        self.assertEqual(periods[3], self.P4)
        for earlier, later in zip(periods, periods[1:]):
            self.assertEqual(earlier[1] + timedelta(days=1), later[0])

    def test_fee_lookup_seed(self):
        self.assertEqual(fee_for_period(self.P1[0]), D("600"))

    def test_era_rule_preserves_started_periods(self):
        # current period P4 ends 2026-12-31; requested mid-period snaps to next grid.
        effective = compute_effective_anchor(self.driver, date(2026, 11, 1))
        self.assertEqual(effective, date(2027, 1, 1))
        effective2 = compute_effective_anchor(self.driver, date(2026, 8, 1))
        self.assertEqual(effective2, date(2027, 1, 1))


class OwnFirstStackTests(FinancialTestBase):
    def test_t5_official_cash_750(self):
        t1 = self.transfer(300, self.P1, self.P4)  # older (smaller id)
        t2 = self.transfer(200, self.P2, self.P4)  # newer
        self.receive(750, self.P4)
        state = self.state(self.P4)
        self.assertEqual(state.remaining_own, D("0"))
        self.assertEqual(state.transfers[0].remaining, D("150"))
        self.assertEqual(state.transfers[1].remaining, D("200"))
        self.assertEqual(state.balance, D("350"))
        self.assertConserved()
        # R=150 ACCEPT
        services.reverse_adjustment(
            adjustment=t1, amount=D("150"), user=self.user, reason="بازگشت"
        )
        after = self.state(self.P4)
        self.assertEqual(after.transfers[0].remaining, D("0"))
        self.assertEqual(after.transfers[1].remaining, D("200"))
        self.assertEqual(after.balance, D("200"))
        self.assertConserved()
        # R=200 on T1 was REJECT before reversal (200 > 150)
        # reset scenario for the reject assertion
    def test_t5_reject_200(self):
        t1 = self.transfer(300, self.P1, self.P4)
        self.transfer(200, self.P2, self.P4)
        self.receive(750, self.P4)
        with self.assertRaises(FinancialError) as ctx:
            services.reverse_adjustment(
                adjustment=t1, amount=D("200"), user=self.user, reason="بازگشت"
            )
        self.assertEqual(ctx.exception.code, "reversal_exceeds_remaining_transfer")

    def test_t5_repeat_reversal_rejected(self):
        t1 = self.transfer(300, self.P1, self.P4)
        self.transfer(200, self.P2, self.P4)
        self.receive(750, self.P4)
        services.reverse_adjustment(
            adjustment=t1, amount=D("150"), user=self.user, reason="اول"
        )
        with self.assertRaises(FinancialError):
            services.reverse_adjustment(
                adjustment=t1, amount=D("150"), user=self.user, reason="دوم"
            )

    def test_t1_cash_300(self):
        t = self.transfer(300, self.P1, self.P2)
        self.receive(300, self.P2)
        s = self.state(self.P2)
        self.assertEqual(s.remaining_own, D("300"))
        self.assertEqual(s.transfers[0].remaining, D("300"))
        self.assertEqual(s.balance, D("600"))
        services.reverse_adjustment(adjustment=t, amount=D("300"), user=self.user, reason="b")
        self.assertEqual(self.state(self.P2).balance, D("300"))
        self.assertConserved()

    def test_t2_cash_600(self):
        t = self.transfer(300, self.P1, self.P2)
        self.receive(600, self.P2)
        s = self.state(self.P2)
        self.assertEqual(s.remaining_own, D("0"))
        self.assertEqual(s.transfers[0].remaining, D("300"))
        services.reverse_adjustment(adjustment=t, amount=D("300"), user=self.user, reason="b")
        self.assertEqual(self.state(self.P2).balance, D("0"))

    def test_t3_cash_900_reversal_rejected(self):
        t = self.transfer(300, self.P1, self.P2)
        self.receive(900, self.P2)
        self.assertEqual(self.state(self.P2).transfers[0].remaining, D("0"))
        with self.assertRaises(FinancialError):
            services.reverse_adjustment(adjustment=t, amount=D("100"), user=self.user, reason="b")

    def test_2a_mixed_reductions_capacity(self):
        self.transfer(200, self.P1, self.P2)
        self.receive(250, self.P2)  # cash
        # credit 150: receive 150 unallocated then consume into P2
        p = self.receive(150)  # all credit
        credit_alloc = p.allocations.get(allocation_type=AllocationType.CREDIT)
        services.consume_credit(
            source_allocation=credit_alloc,
            amount=D("150"),
            target_period=self.P2,
            user=self.user,
        )
        services.create_waiver(
            driver=self.driver, amount=D("100"), source_period=self.P2, user=self.user, reason="w"
        )
        self.receive(150, self.P2)
        s = self.state(self.P2)
        self.assertEqual(s.remaining_own, D("0"))
        self.assertEqual(s.transfers[0].remaining, D("150"))
        self.assertEqual(s.balance, D("150"))
        self.assertConserved()

    def test_2b_waiver_and_reversal(self):
        self.transfer(300, self.P1, self.P2)
        w = services.create_waiver(
            driver=self.driver, amount=D("700"), source_period=self.P2, user=self.user, reason="w"
        )
        self.assertEqual(self.state(self.P2).balance, D("200"))
        services.reverse_adjustment(adjustment=w, amount=D("700"), user=self.user, reason="rw")
        self.assertEqual(self.state(self.P2).balance, D("900"))
        self.assertConserved()


class CreditAndAdjustmentTests(FinancialTestBase):
    def test_partial_payment_becomes_credit(self):
        payment = self.receive(700, self.P1)
        fee = payment.allocations.get(allocation_type=AllocationType.FEE_PERIOD)
        credit = payment.allocations.get(allocation_type=AllocationType.CREDIT)
        self.assertEqual(fee.allocated_amount, D("600"))
        self.assertEqual(credit.allocated_amount, D("100"))
        self.assertEqual(self.state(self.P1).balance, D("0"))
        self.assertEqual(DriverLedger(self.driver).available_credit(), D("100"))
        self.assertConserved()

    def test_consumption_cap_n2(self):
        payment = self.receive(300)  # all credit (no target)
        credit = payment.allocations.get(allocation_type=AllocationType.CREDIT)
        # P2 need = 600; source available 300; request 300 ok
        services.consume_credit(
            source_allocation=credit, amount=D("300"), target_period=self.P2, user=self.user
        )
        self.assertEqual(DriverLedger(self.driver).available_credit(), D("0"))
        self.assertEqual(self.state(self.P2).balance, D("300"))
        self.assertConserved()

    def test_consumption_exceeds_source_rejected(self):
        payment = self.receive(300)
        credit = payment.allocations.get(allocation_type=AllocationType.CREDIT)
        with self.assertRaises(FinancialError) as ctx:
            services.consume_credit(
                source_allocation=credit, amount=D("400"), target_period=self.P2, user=self.user
            )
        self.assertEqual(ctx.exception.code, "consumption_exceeds_balance")

    def test_consumption_exceeds_target_need_rejected(self):
        payment = self.receive(1000)  # 1000 credit
        credit = payment.allocations.get(allocation_type=AllocationType.CREDIT)
        # P2 need 600; request 700 > min(1000,600)
        with self.assertRaises(FinancialError):
            services.consume_credit(
                source_allocation=credit, amount=D("700"), target_period=self.P2, user=self.user
            )

    def test_transfer_cap_and_partial_reversal_n3(self):
        t = self.transfer(300, self.P1, self.P2)
        self.assertEqual(self.state(self.P1).balance, D("300"))
        self.assertEqual(self.state(self.P2).balance, D("900"))
        services.reverse_adjustment(adjustment=t, amount=D("100"), user=self.user, reason="r1")
        self.assertEqual(self.state(self.P1).balance, D("400"))
        self.assertEqual(self.state(self.P2).balance, D("800"))
        with self.assertRaises(FinancialError):
            services.reverse_adjustment(adjustment=t, amount=D("250"), user=self.user, reason="r2")
        self.assertConserved()

    def test_transfer_exceeds_source_rejected(self):
        with self.assertRaises(FinancialError) as ctx:
            self.transfer(700, self.P1, self.P2)
        self.assertEqual(ctx.exception.code, "transfer_exceeds_balance")

    def test_waiver_exceeds_source_rejected(self):
        with self.assertRaises(FinancialError):
            services.create_waiver(
                driver=self.driver, amount=D("700"), source_period=self.P1, user=self.user, reason="w"
            )


class VoidCorrectTests(FinancialTestBase):
    def test_void_cascade_n1(self):
        payment = self.receive(700, self.P1)
        credit = payment.allocations.get(allocation_type=AllocationType.CREDIT)
        services.consume_credit(
            source_allocation=credit, amount=D("100"), target_period=self.P2, user=self.user
        )
        self.assertEqual(self.state(self.P1).balance, D("0"))
        self.assertEqual(self.state(self.P2).balance, D("500"))
        services.void_payment(payment=payment, user=self.user, reason="ابطال")
        payment.refresh_from_db()
        self.assertEqual(payment.status, PaymentStatus.VOIDED)
        self.assertEqual(self.state(self.P1).balance, D("600"))
        self.assertEqual(self.state(self.P2).balance, D("600"))
        self.assertEqual(DriverLedger(self.driver).available_credit(), D("0"))
        self.assertEqual(DriverLedger(self.driver).cash_received(), D("0"))
        self.assertConserved()
        # all children reversed with the same timestamp
        stamps = {payment.voided_at}
        for alloc in payment.allocations.all():
            stamps.add(alloc.reversed_at)
            for cons in alloc.consumptions.all():
                stamps.add(cons.reversed_at)
        self.assertEqual(len(stamps), 1)

    def test_correction_replaces_not_duplicates_r2(self):
        original = self.receive(400, self.P1)
        replacement = services.correct_payment(
            payment=original, user=self.user, reason="اصلاح مبلغ", new_amount=D("800"),
            target_period=self.P1,
        )
        original.refresh_from_db()
        self.assertEqual(original.status, PaymentStatus.CORRECTED)
        self.assertEqual(replacement.correction_of_id, original.id)
        self.assertEqual(replacement.effective_date, FIXED_TODAY)
        self.assertEqual(DriverLedger(self.driver).cash_received(), D("800"))
        self.assertEqual(self.state(self.P1).balance, D("0"))
        # credit 200 from the 800 correction
        self.assertEqual(DriverLedger(self.driver).available_credit(), D("200"))
        self.assertConserved()

    def test_allocation_correction_wrong_period_w5(self):
        payment = self.receive(600, self.P1)
        alloc = payment.allocations.get(allocation_type=AllocationType.FEE_PERIOD)
        new_alloc = services.correct_allocation(
            allocation=alloc, user=self.user, reason="دوره اشتباه", new_target_period=self.P2
        )
        self.assertEqual(new_alloc.correction_of_id, alloc.id)
        self.assertEqual(self.state(self.P1).balance, D("600"))
        self.assertEqual(self.state(self.P2).balance, D("0"))
        # zero new Payment rows; revenue unchanged
        self.assertEqual(Payment.objects.count(), 1)
        self.assertEqual(DriverLedger(self.driver).cash_received(), D("600"))
        self.assertConserved()

    def test_w5_ext_credit_correction_with_consumptions(self):
        # P=700 credit; C1=100->P2, C2=100->P3; correct source 700->300 and
        # re-approve only C1'=100->P2 (C2 stays reversed, P3 debt restored).
        payment = self.receive(700)  # all credit
        credit = payment.allocations.get(allocation_type=AllocationType.CREDIT)
        services.consume_credit(
            source_allocation=credit, amount=D("100"), target_period=self.P2, user=self.user
        )
        services.consume_credit(
            source_allocation=credit, amount=D("100"), target_period=self.P3, user=self.user
        )
        self.assertEqual(self.state(self.P2).balance, D("500"))
        self.assertEqual(self.state(self.P3).balance, D("500"))
        result = services.correct_credit_allocation(
            allocation=credit,
            user=self.user,
            reason="اصلاح اعتبار",
            new_credit_amount=D("300"),
            consumptions=[{"start": self.P2[0], "end": self.P2[1], "amount": D("100")}],
        )
        self.assertIsNotNone(result["new_credit_allocation"])
        self.assertEqual(len(result["new_consumptions"]), 1)
        self.assertEqual(self.state(self.P2).balance, D("500"))  # C1' re-approved
        self.assertEqual(self.state(self.P3).balance, D("600"))  # C2 reversed, not re-approved
        ledger = DriverLedger(self.driver)
        self.assertEqual(ledger.available_credit(), D("200"))  # 300 - 100
        self.assertEqual(ledger.unallocated(payment), D("400"))  # 700 - 300 active
        self.assertEqual(ledger.cash_received(), D("700"))  # revenue unchanged
        self.assertConserved()


class W9ChainTests(FinancialTestBase):
    def test_n4_unsettle_then_reverse(self):
        t = self.transfer(300, self.P1, self.P2)
        payment = self.receive(900, self.P2)  # settles P2 fully (own 600 + T 300)
        self.assertEqual(self.state(self.P2).balance, D("0"))
        self.assertEqual(self.state(self.P2).transfers[0].remaining, D("0"))
        with self.assertRaises(FinancialError):
            services.reverse_adjustment(adjustment=t, amount=D("300"), user=self.user, reason="r")
        services.unsettle_and_reverse(
            adjustment=t, amount=D("300"), user=self.user, reason="W9"
        )
        # destination own fee re-settled 600, transfer reversed 300 -> P2 balance 0 own + 0
        self.assertEqual(self.state(self.P1).balance, D("600"))
        self.assertEqual(DriverLedger(self.driver).cash_received(), D("900"))
        self.assertEqual(DriverLedger(self.driver).available_credit(), D("300"))
        self.assertConserved()

    def test_chain_downstream_first(self):
        ab = self.transfer(300, self.P1, self.P2)  # A->B
        self.receive(600, self.P2)  # B cash 600 -> own 0, T_AB_rem 300
        bc = self.transfer(200, self.P2, self.P3)  # B->C ; B reductions 800 -> T_AB_rem 100
        self.assertEqual(self.state(self.P2).transfers[0].remaining, D("100"))
        with self.assertRaises(FinancialError) as ctx:
            services.reverse_adjustment(adjustment=ab, amount=D("300"), user=self.user, reason="r")
        self.assertEqual(ctx.exception.code, "reversal_exceeds_remaining_transfer")
        # downstream first
        services.reverse_adjustment(adjustment=bc, amount=D("200"), user=self.user, reason="rev BC")
        self.assertEqual(self.state(self.P2).transfers[0].remaining, D("300"))
        services.reverse_adjustment(adjustment=ab, amount=D("300"), user=self.user, reason="rev AB")
        self.assertEqual(self.state(self.P1).balance, D("600"))
        self.assertEqual(self.state(self.P2).balance, D("0"))
        self.assertConserved()


class FeeScheduleEraTests(FinancialTestBase):
    def test_fee_change_applies_to_future_periods_n8(self):
        services.change_fee_schedule(
            amount=D("700"), effective_from=date(2027, 1, 1), user=self.user, reason="افزایش"
        )
        self.assertEqual(fee_for_period(self.P4[0]), D("600"))
        self.assertEqual(fee_for_period(date(2027, 1, 1)), D("700"))

    def test_fee_change_no_backdate(self):
        with self.assertRaises(FinancialError) as ctx:
            services.change_fee_schedule(
                amount=D("700"), effective_from=date(2020, 1, 1), user=self.user, reason="x"
            )
        self.assertEqual(ctx.exception.code, "no_backdate")

    def test_w10_fee_start_date_change_and_history(self):
        history = services.change_fee_start_date(
            driver=self.driver, requested=date(2026, 11, 1), user=self.user, reason="تغییر"
        )
        self.assertEqual(history.effective_fee_start_date, date(2027, 1, 1))
        self.driver.refresh_from_db()
        self.assertEqual(self.driver.fee_start_date, date(2026, 11, 1))  # mirror requested
        self.assertEqual(self.driver.fee_history.count(), 2)

    def test_w10_requires_reason(self):
        with self.assertRaises(FinancialError) as ctx:
            services.change_fee_start_date(
                driver=self.driver, requested=date(2027, 1, 1), user=self.user, reason="  "
            )
        self.assertEqual(ctx.exception.code, "reason_required")


class AggregateTests(FinancialTestBase):
    def test_three_distinct_aggregates(self):
        # P1,P2,P3 overdue (end < today); P4 current.
        self.receive(600, self.P1)  # settle P1
        summary = driver_financial_summary(self.driver)
        self.assertEqual(D(summary["current_obligation"]), D("600"))  # P4 untouched
        self.assertEqual(D(summary["overdue_debt"]), D("1200"))  # P2+P3
        self.assertEqual(D(summary["driver_total_balance"]), D("1800"))
        self.assertConserved()

    def test_current_period_never_overdue(self):
        summary = driver_financial_summary(self.driver)
        p4 = next(p for p in summary["periods"] if p["start"] == "2026-10-01")
        self.assertFalse(p4["is_overdue"])
        p1 = next(p for p in summary["periods"] if p["start"] == "2026-01-01")
        self.assertTrue(p1["is_overdue"])


class TriggerTests(FinancialTestBase):
    def _raw_execute(self, sql, params=()):
        with connection.cursor() as cursor:
            cursor.execute(sql, params)

    def _raw_execute_rejected(self, sql, params=()):
        """Execute a statement that a database trigger is expected to reject.

        The statement runs inside a nested atomic block (a SAVEPOINT on
        PostgreSQL) so the rejected write does not abort the enclosing
        transaction. PostgreSQL marks the whole transaction as failed after
        any error, while SQLite only rolls back the offending statement —
        without the savepoint the assertions that follow the rejection
        cannot run on PostgreSQL. The trigger must still reject the write.
        """
        with transaction.atomic():
            self._raw_execute(sql, params)

    def test_allocation_cap_trigger_raw_v4(self):
        payment = self.receive(600, self.P1)  # active alloc 600 == amount
        with self.assertRaises(Exception):
            self._raw_execute_rejected(
                """
                INSERT INTO payments_paymentallocation
                  (payment_id, allocation_type, target_period_start, target_period_end,
                   allocated_amount, effective_date, reversal_reason, allocated_by_id, created_at)
                VALUES (%s, 'credit', NULL, NULL, 100, %s, '', %s, %s)
                """,
                [payment.id, FIXED_TODAY.isoformat(), self.user.id, FIXED_NOW.isoformat()],
            )
        self.assertEqual(payment.allocations.count(), 1)

    def test_consumption_source_trigger_raw_v5(self):
        payment = self.receive(300)
        credit = payment.allocations.get(allocation_type=AllocationType.CREDIT)
        with self.assertRaises(Exception):
            self._raw_execute_rejected(
                """
                INSERT INTO payments_allocationconsumption
                  (source_allocation_id, consumption_amount, target_period_start, target_period_end,
                   effective_date, consumption_id, consumed_by_id, reason, reversal_reason, consumed_at)
                VALUES (%s, 400, %s, %s, %s, %s, %s, '', '', %s)
                """,
                [credit.id, self.P2[0].isoformat(), self.P2[1].isoformat(),
                 FIXED_TODAY.isoformat(), uuid.uuid4().hex, self.user.id, FIXED_NOW.isoformat()],
            )
        self.assertEqual(AllocationConsumption.objects.count(), 0)

    def test_consumption_source_must_be_credit_raw(self):
        payment = self.receive(600, self.P1)
        fee = payment.allocations.get(allocation_type=AllocationType.FEE_PERIOD)
        with self.assertRaises(Exception):
            self._raw_execute_rejected(
                """
                INSERT INTO payments_allocationconsumption
                  (source_allocation_id, consumption_amount, target_period_start, target_period_end,
                   effective_date, consumption_id, consumed_by_id, reason, reversal_reason, consumed_at)
                VALUES (%s, 100, %s, %s, %s, %s, %s, '', '', %s)
                """,
                [fee.id, self.P2[0].isoformat(), self.P2[1].isoformat(),
                 FIXED_TODAY.isoformat(), uuid.uuid4().hex, self.user.id, FIXED_NOW.isoformat()],
            )

    def test_cumulative_reversal_trigger_raw_v6(self):
        t = self.transfer(300, self.P1, self.P2)
        services.reverse_adjustment(adjustment=t, amount=D("200"), user=self.user, reason="r1")
        with self.assertRaises(Exception):
            self._raw_execute_rejected(
                """
                INSERT INTO payments_adjustment
                  (driver_id, adjustment_type, amount, source_period_start, source_period_end,
                   destination_period_start, destination_period_end, reverses_adjustment_id,
                   reason, effective_date, created_by_id, created_at)
                VALUES (%s, 'transfer_reversal', 200, %s, %s, %s, %s, %s, 'r2', %s, %s, %s)
                """,
                [self.driver.id, self.P1[0].isoformat(), self.P1[1].isoformat(),
                 self.P2[0].isoformat(), self.P2[1].isoformat(), t.id,
                 FIXED_TODAY.isoformat(), self.user.id, FIXED_NOW.isoformat()],
            )
        self.assertEqual(Adjustment.objects.filter(reverses_adjustment=t).count(), 1)

    def test_atomic_rollback_v1(self):
        before = PaymentAllocation.objects.count()
        payment = self.receive(600, self.P1)
        with self.assertRaises(Exception):
            with transaction.atomic():
                self._raw_execute(
                    """
                    INSERT INTO payments_paymentallocation
                      (payment_id, allocation_type, target_period_start, target_period_end,
                       allocated_amount, effective_date, reversal_reason, allocated_by_id, created_at)
                    VALUES (%s, 'credit', NULL, NULL, 100, %s, '', %s, %s)
                    """,
                    [payment.id, FIXED_TODAY.isoformat(), self.user.id, FIXED_NOW.isoformat()],
                )
        self.assertEqual(PaymentAllocation.objects.count(), before + 1)  # only the original 600 fee

    def test_service_trigger_parity_v10(self):
        payment = self.receive(600, self.P1)
        # service path: consuming from a fee allocation is rejected
        fee = payment.allocations.get(allocation_type=AllocationType.FEE_PERIOD)
        with self.assertRaises(FinancialError):
            services.consume_credit(
                source_allocation=fee, amount=D("100"), target_period=self.P2, user=self.user
            )
        # raw path: same invariant rejected by trigger
        with self.assertRaises(Exception):
            self._raw_execute(
                """
                INSERT INTO payments_allocationconsumption
                  (source_allocation_id, consumption_amount, target_period_start, target_period_end,
                   effective_date, consumption_id, consumed_by_id, reason, reversal_reason, consumed_at)
                VALUES (%s, 100, %s, %s, %s, %s, %s, '', '', %s)
                """,
                [fee.id, self.P2[0].isoformat(), self.P2[1].isoformat(),
                 FIXED_TODAY.isoformat(), uuid.uuid4().hex, self.user.id, FIXED_NOW.isoformat()],
            )

    def test_hard_delete_forbidden(self):
        payment = self.receive(600, self.P1)
        with self.assertRaises(PermissionError):
            payment.delete()
        alloc = payment.allocations.first()
        with self.assertRaises(PermissionError):
            alloc.delete()
        t = self.transfer(100, self.P2, self.P3)
        with self.assertRaises(PermissionError):
            t.delete()


class TargetPeriodValidationTests(FinancialTestBase):
    """§8.2 / C6 — allocation and consumption target period validation.

    The target of an allocation or a consumption must be one of the driver's
    reconstructed periods that has already started. A period that has not begun
    yet is a prepayment and belongs on the credit path (C6); a pair that is not
    a period of this driver at all is invalid.
    """

    # The driver's era anchor is 2026-01-01 (see FinancialTestBase), so the
    # grid continues 2026-01-01, 2026-04-01, 2026-07-01, 2026-10-01,
    # 2027-01-01, ... With the clock fixed at 2026-11-10 the next period
    # (2027-01-01) has not started yet.
    FUTURE = (date(2027, 1, 1), date(2027, 3, 31))
    # Not on the driver's era grid at all.
    NOT_A_PERIOD = (date(2026, 2, 1), date(2026, 2, 28))

    # ------------------------------------------------------------------
    # Valid targets
    # ------------------------------------------------------------------
    def test_started_period_target_is_accepted(self):
        """A period that has already started is a valid allocation target."""
        payment = self.receive(600, self.P1)
        alloc = payment.allocations.get(allocation_type=AllocationType.FEE_PERIOD)
        self.assertEqual(alloc.target_period_start, self.P1[0])
        self.assertEqual(alloc.target_period_end, self.P1[1])
        self.assertEqual(alloc.allocated_amount, D("600"))

    def test_last_started_period_target_is_accepted(self):
        """The rule is 'start <= today', not 'the current period only'."""
        self.assertLessEqual(self.P4[0], FIXED_TODAY)
        payment = self.receive(600, self.P4)
        alloc = payment.allocations.get(allocation_type=AllocationType.FEE_PERIOD)
        self.assertEqual(alloc.target_period_start, self.P4[0])

    # ------------------------------------------------------------------
    # Rejected targets
    # ------------------------------------------------------------------
    def test_future_period_target_is_accepted(self):
        """Paying for an upcoming quarter is a prepayment and is booked on it."""
        payment = self.receive(600, self.FUTURE)
        alloc = payment.allocations.get(allocation_type=AllocationType.FEE_PERIOD)
        self.assertEqual(alloc.target_period_start, self.FUTURE[0])
        self.assertEqual(alloc.allocated_amount, D("600"))

    def test_unknown_period_target_is_rejected(self):
        """A pair that is not a period of this driver is invalid."""
        with self.assertRaises(FinancialError) as ctx:
            self.receive(600, self.NOT_A_PERIOD)
        self.assertEqual(ctx.exception.code, "unknown_period")
        self.assertEqual(Payment.objects.count(), 0)

    def test_inverted_period_target_is_rejected(self):
        """start after end is invalid."""
        with self.assertRaises(FinancialError) as ctx:
            self.receive(600, (self.P2[1], self.P2[0]))
        self.assertEqual(ctx.exception.code, "invalid_period")

    def test_period_of_another_driver_is_rejected(self):
        """A valid period of a different driver's grid is not this driver's."""
        other = self.make_driver(date(2026, 2, 1))
        other_period = reconstruct_periods(other, until=FIXED_TODAY)[0]
        self.assertNotIn(other_period, set(reconstruct_periods(self.driver, until=FIXED_TODAY)))
        with self.assertRaises(FinancialError) as ctx:
            self.receive(600, other_period)
        self.assertEqual(ctx.exception.code, "unknown_period")

    # ------------------------------------------------------------------
    # C6 — future prepayment goes through the credit path
    # ------------------------------------------------------------------
    def test_prepayment_without_target_uses_credit_path(self):
        """No target period => the whole amount becomes traceable credit."""
        payment = self.receive(600)
        alloc = payment.allocations.get(allocation_type=AllocationType.CREDIT)
        self.assertEqual(alloc.allocated_amount, D("600"))
        self.assertIsNone(alloc.target_period_start)
        self.assertIsNone(alloc.target_period_end)
        self.assertEqual(payment.allocations.count(), 1)
        # The prepayment is money in the pool, not a settled future period:
        # the driver's own obligation for the started period is untouched.
        self.assertEqual(self.state(self.P1).balance, D("600"))
        self.assertEqual(DriverLedger(self.driver).source_available(alloc), D("600"))

    def test_prepayment_credit_can_later_settle_a_started_period(self):
        """Credit raised for a prepayment can be consumed against a started period."""
        payment = self.receive(600)  # prepayment -> credit 600
        credit = payment.allocations.get(allocation_type=AllocationType.CREDIT)
        services.consume_credit(
            source_allocation=credit, amount=D("100"), target_period=self.P1,
            user=self.user,
        )
        self.assertEqual(AllocationConsumption.objects.count(), 1)
        self.assertEqual(DriverLedger(self.driver).source_available(credit), D("500"))

    # ------------------------------------------------------------------
    # Consumption targets
    # ------------------------------------------------------------------
    def test_consumption_future_target_is_rejected(self):
        payment = self.receive(300)
        credit = payment.allocations.get(allocation_type=AllocationType.CREDIT)
        with self.assertRaises(FinancialError) as ctx:
            services.consume_credit(
                source_allocation=credit, amount=D("100"),
                target_period=self.FUTURE, user=self.user,
            )
        self.assertEqual(ctx.exception.code, "future_period")
        self.assertEqual(AllocationConsumption.objects.count(), 0)

    def test_consumption_unknown_target_is_rejected(self):
        payment = self.receive(300)
        credit = payment.allocations.get(allocation_type=AllocationType.CREDIT)
        with self.assertRaises(FinancialError) as ctx:
            services.consume_credit(
                source_allocation=credit, amount=D("100"),
                target_period=self.NOT_A_PERIOD, user=self.user,
            )
        self.assertEqual(ctx.exception.code, "unknown_period")
        self.assertEqual(AllocationConsumption.objects.count(), 0)

    # ------------------------------------------------------------------
    # Correction targets (W5)
    # ------------------------------------------------------------------
    def test_allocation_correction_future_target_is_accepted(self):
        """A correction may move an allocation onto an upcoming quarter."""
        payment = self.receive(600, self.P1)
        alloc = payment.allocations.get(allocation_type=AllocationType.FEE_PERIOD)
        services.correct_allocation(
            allocation=alloc, user=self.user, reason="دوره اشتباه",
            new_target_period=self.FUTURE,
        )
        replacement = PaymentAllocation.objects.filter(correction_of=alloc).first()
        self.assertIsNotNone(replacement)
        self.assertEqual(replacement.target_period_start, self.FUTURE[0])
        alloc.refresh_from_db()
        self.assertIsNotNone(alloc.reversed_at)

    # ------------------------------------------------------------------
    # API surface — clear 400 with a stable code
    # ------------------------------------------------------------------
    def _api_payment(self, **overrides):
        payload = {
            "driver_id": self.driver.id,
            "amount": "600",
            "payment_date": FIXED_TODAY.isoformat(),
        }
        payload.update(overrides)
        client = APIClient()
        client.force_authenticate(user=self.user)
        return client.post("/api/payments/", payload, format="json")

    def test_api_accepts_future_target_period(self):
        response = self._api_payment(
            target_period_start=self.FUTURE[0].isoformat(),
            target_period_end=self.FUTURE[1].isoformat(),
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Payment.objects.count(), 1)

    def test_api_rejects_unknown_target_period_with_400(self):
        response = self._api_payment(
            target_period_start=self.NOT_A_PERIOD[0].isoformat(),
            target_period_end=self.NOT_A_PERIOD[1].isoformat(),
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["code"], "unknown_period")
        self.assertEqual(Payment.objects.count(), 0)

    def test_api_accepts_started_target_period(self):
        response = self._api_payment(
            target_period_start=self.P1[0].isoformat(),
            target_period_end=self.P1[1].isoformat(),
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Payment.objects.count(), 1)

    def test_api_prepayment_without_target_creates_credit(self):
        response = self._api_payment()
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        payment = Payment.objects.get(pk=response.data["id"])
        alloc = payment.allocations.get(allocation_type=AllocationType.CREDIT)
        self.assertEqual(alloc.allocated_amount, D("600"))


class FinancialReportTests(FinancialTestBase):
    """Consolidated financial report with a date range (payments/revenue/debt/credit)."""

    def _api_report(self, **params):
        client = APIClient()
        client.force_authenticate(user=self.user)
        query = "&".join(f"{k}={v}" for k, v in params.items())
        url = "/api/reports/financial/" + (f"?{query}" if query else "")
        return client.get(url)

    # ------------------------------------------------------------------
    # Shape
    # ------------------------------------------------------------------
    def test_report_has_all_sections(self):
        report = financial_report(as_of=FIXED_TODAY)
        for key in ("as_of", "date_from", "date_to", "payments", "revenue",
                    "debt", "credit", "drivers", "totals"):
            self.assertIn(key, report)
        self.assertEqual(report["as_of"], FIXED_TODAY.isoformat())
        self.assertIsNone(report["date_from"])
        self.assertIsNone(report["date_to"])

    def test_report_without_payments_has_no_revenue(self):
        report = financial_report(as_of=FIXED_TODAY)
        self.assertEqual(report["payments"]["count"], 0)
        self.assertEqual(report["payments"]["total_amount"], "0.00")
        self.assertEqual(report["revenue"]["cash_revenue"], "0.00")
        self.assertEqual(report["credit"]["available_total"], "0.00")
        # The fee obligations exist whether or not a payment was made:
        # 4 periods x 600 = 2400.
        self.assertEqual(report["debt"]["total_balance"], "2400.00")
        self.assertEqual(report["totals"]["driver_count"], 1)

    # ------------------------------------------------------------------
    # Range scoping
    # ------------------------------------------------------------------
    def test_range_scopes_payments_and_revenue(self):
        self.receive(600, self.P1)          # payment_date = FIXED_TODAY
        self.receive(300, self.P1, payment_date=date(2026, 2, 1))

        full = financial_report(as_of=FIXED_TODAY)
        self.assertEqual(full["payments"]["count"], 2)
        self.assertEqual(full["payments"]["total_amount"], "900.00")
        self.assertEqual(full["revenue"]["cash_revenue"], "900.00")

        ranged = financial_report(
            date_from=date(2026, 3, 1), date_to=date(2026, 12, 31), as_of=FIXED_TODAY
        )
        self.assertEqual(ranged["payments"]["count"], 1)
        self.assertEqual(ranged["payments"]["total_amount"], "600.00")
        self.assertEqual(ranged["revenue"]["cash_revenue"], "600.00")
        self.assertEqual(ranged["date_from"], "2026-03-01")
        self.assertEqual(ranged["date_to"], "2026-12-31")

    def test_range_excludes_payments_outside_it(self):
        self.receive(600, self.P1)
        self.receive(300, self.P1, payment_date=date(2026, 2, 1))
        ranged = financial_report(
            date_from=date(2026, 1, 1), date_to=date(2026, 2, 28), as_of=FIXED_TODAY
        )
        self.assertEqual(ranged["payments"]["count"], 1)
        self.assertEqual(ranged["payments"]["total_amount"], "300.00")

    # ------------------------------------------------------------------
    # Debt & credit are as-of positions
    # ------------------------------------------------------------------
    def test_debt_and_credit_are_as_of_positions(self):
        # Nothing settled: 4 periods x 600 = 2400 owed, P4 is the current one,
        # P1..P3 are overdue.
        report = financial_report(as_of=FIXED_TODAY)
        driver_row = next(r for r in report["drivers"] if r["driver_id"] == self.driver.id)
        self.assertEqual(driver_row["total_balance"], "2400.00")
        self.assertEqual(driver_row["current_obligation"], "600.00")
        self.assertEqual(driver_row["overdue_debt"], "1800.00")
        self.assertEqual(report["debt"]["total_balance"], "2400.00")
        self.assertEqual(report["debt"]["current_obligation"], "600.00")
        self.assertEqual(report["debt"]["overdue_debt"], "1800.00")
        self.assertEqual(report["credit"]["available_total"], "0.00")

    def test_credit_is_reported_after_a_prepayment(self):
        payment = self.receive(600)  # no target period -> credit allocation
        report = financial_report(as_of=FIXED_TODAY)
        driver_row = next(r for r in report["drivers"] if r["driver_id"] == self.driver.id)
        self.assertEqual(driver_row["available_credit"], "600.00")
        self.assertEqual(driver_row["credit_allocated"], "600.00")
        self.assertEqual(report["credit"]["available_total"], "600.00")
        self.assertEqual(report["credit"]["allocated_total"], "600.00")
        # The prepayment is not a settlement: the obligation is untouched
        # until a manager consumes the credit against a period.
        self.assertEqual(driver_row["total_balance"], "2400.00")

    def test_totals_equal_the_sum_of_driver_rows(self):
        self.receive(600, self.P1)
        self.receive(300, self.P1)
        report = financial_report(as_of=FIXED_TODAY)
        self.assertEqual(
            report["debt"]["total_balance"],
            str(sum(D(r["total_balance"]) for r in report["drivers"])),
        )
        self.assertEqual(
            report["credit"]["available_total"],
            str(sum(D(r["available_credit"]) for r in report["drivers"])),
        )
        self.assertEqual(
            report["payments"]["total_amount"],
            str(sum(D(r["payments_total"]) for r in report["drivers"])),
        )
        self.assertEqual(report["totals"]["driver_count"], len(report["drivers"]))

    def test_driver_row_carries_payments_and_status(self):
        self.receive(600, self.P1)
        report = financial_report(
            date_from=date(2026, 1, 1), date_to=FIXED_TODAY, as_of=FIXED_TODAY
        )
        row = next(r for r in report["drivers"] if r["driver_id"] == self.driver.id)
        self.assertEqual(row["driver_code"], self.driver.driver_code)
        self.assertEqual(row["payments_count"], 1)
        self.assertEqual(row["payments_total"], "600.00")
        self.assertIn("conservation_ok", row)

    # ------------------------------------------------------------------
    # API surface
    # ------------------------------------------------------------------
    def test_api_returns_report(self):
        self.receive(600, self.P1)
        response = self._api_report(date_from="2026-01-01", date_to="2026-12-31")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["payments"]["count"], 1)
        self.assertEqual(response.data["payments"]["total_amount"], "600.00")
        self.assertEqual(len(response.data["drivers"]), 1)

    def test_api_requires_both_range_bounds(self):
        response = self._api_report(date_from="2026-01-01")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["code"], "invalid_date")

    def test_api_rejects_inverted_range(self):
        response = self._api_report(date_from="2026-12-01", date_to="2026-01-01")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["code"], "invalid_date")

    def test_api_rejects_date_to_after_as_of(self):
        response = self._api_report(
            date_from="2026-01-01", date_to="2026-12-31", as_of="2026-06-30"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["code"], "invalid_date")

    def test_api_rejects_invalid_date_format(self):
        response = self._api_report(date_from="not-a-date", date_to="2026-12-31")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["code"], "invalid_date")


class MultiPeriodAllocationTests(FinancialTestBase):
    """A payment can be spread over several quarters (§ period allocation).

    The driver's era anchor is 2026-01-01, so the quarters are
    P1 2026-01-01, P2 2026-04-01, P3 2026-07-01, P4 2026-10-01 (started)
    and P5 2027-01-01 (not started yet at FIXED_TODAY = 2026-11-10).
    """

    P5 = (date(2027, 1, 1), date(2027, 3, 31))

    def _fee_allocs(self, payment):
        return list(
            PaymentAllocation.objects.filter(
                payment=payment, allocation_type=AllocationType.FEE_PERIOD
            ).order_by("target_period_start")
        )

    def _credit_alloc(self, payment):
        return PaymentAllocation.objects.filter(
            payment=payment, allocation_type=AllocationType.CREDIT
        ).first()

    # ------------------------------------------------------------------
    # Splitting
    # ------------------------------------------------------------------
    def test_full_payment_covers_the_period(self):
        payment = self.receive(600, self.P1)
        alloc = self._fee_allocs(payment)[0]
        self.assertEqual(alloc.allocated_amount, D("600"))
        self.assertEqual(alloc.target_period_start, self.P1[0])
        self.assertIsNone(self._credit_alloc(payment))

    def test_partial_payment_stays_on_one_period(self):
        """200 out of 600 is booked on that period, the rest is not invented."""
        payment = self.receive(200, self.P1)
        alloc = self._fee_allocs(payment)[0]
        self.assertEqual(alloc.allocated_amount, D("200"))
        self.assertEqual(alloc.target_period_start, self.P1[0])
        self.assertIsNone(self._credit_alloc(payment))

    def test_payment_splits_across_consecutive_periods(self):
        """800 covers 600 of P1 and 200 of P2."""
        services.receive_payment(
            driver=self.driver, amount=D("800"), payment_date=FIXED_TODAY,
            user=self.user, target_period=self.P1, periods_count=2,
        )
        payment = Payment.objects.filter(driver=self.driver).order_by("-id").first()
        allocs = self._fee_allocs(payment)
        self.assertEqual(len(allocs), 2)
        self.assertEqual(allocs[0].target_period_start, self.P1[0])
        self.assertEqual(allocs[0].allocated_amount, D("600"))
        self.assertEqual(allocs[1].target_period_start, self.P2[0])
        self.assertEqual(allocs[1].allocated_amount, D("200"))
        self.assertIsNone(self._credit_alloc(payment))

    def test_payment_covers_past_and_future_periods(self):
        """Three quarters, the last one not started yet."""
        services.receive_payment(
            driver=self.driver, amount=D("1800"), payment_date=FIXED_TODAY,
            user=self.user, target_period=self.P1, periods_count=3,
        )
        payment = Payment.objects.filter(driver=self.driver).order_by("-id").first()
        allocs = self._fee_allocs(payment)
        self.assertEqual(len(allocs), 3)
        self.assertEqual(
            [a.target_period_start for a in allocs],
            [self.P1[0], self.P2[0], self.P3[0]],
        )
        self.assertEqual([a.allocated_amount for a in allocs], [D("600"), D("600"), D("600")])

    def test_remainder_beyond_the_covered_periods_goes_to_credit(self):
        """2000 for two quarters: 1200 on the quarters, 800 stays as credit."""
        services.receive_payment(
            driver=self.driver, amount=D("2000"), payment_date=FIXED_TODAY,
            user=self.user, target_period=self.P1, periods_count=2,
        )
        payment = Payment.objects.filter(driver=self.driver).order_by("-id").first()
        allocs = self._fee_allocs(payment)
        self.assertEqual(sum(a.allocated_amount for a in allocs), D("1200"))
        credit = self._credit_alloc(payment)
        self.assertIsNotNone(credit)
        self.assertEqual(credit.allocated_amount, D("800"))
        self.assertIsNone(credit.target_period_start)

    def test_allocations_never_exceed_the_payment_amount(self):
        services.receive_payment(
            driver=self.driver, amount=D("800"), payment_date=FIXED_TODAY,
            user=self.user, target_period=self.P1, periods_count=3,
        )
        payment = Payment.objects.filter(driver=self.driver).order_by("-id").first()
        total = sum(
            a.allocated_amount for a in payment.allocations.filter(reversed_at__isnull=True)
        )
        self.assertLessEqual(total, payment.amount)
        self.assertEqual(total, D("800"))

    def test_a_period_is_never_over_allocated(self):
        """A second payment on a partly paid period fills the rest of the fee.

        200 already paid on P1 (fee 600) leaves 400 open. A payment of 800
        over P1+P2 must book 400 on P1 — not 600 — otherwise the period would
        be over-allocated and equation (O) would break.
        """
        self.receive(200, self.P1)
        services.receive_payment(
            driver=self.driver, amount=D("800"), payment_date=FIXED_TODAY,
            user=self.user, target_period=self.P1, periods_count=2,
        )
        payment = Payment.objects.filter(driver=self.driver).order_by("-id").first()
        allocs = self._fee_allocs(payment)
        self.assertEqual(len(allocs), 2)
        self.assertEqual(allocs[0].allocated_amount, D("400"))
        self.assertEqual(allocs[1].allocated_amount, D("400"))
        # P1 now carries exactly its fee and no more
        paid_on_p1 = sum(
            a.allocated_amount
            for a in PaymentAllocation.objects.filter(
                payment__driver=self.driver,
                allocation_type=AllocationType.FEE_PERIOD,
                target_period_start=self.P1[0],
                reversed_at__isnull=True,
            )
        )
        self.assertEqual(paid_on_p1, D("600"))
        report = conservation_report(self.driver, FIXED_TODAY)
        self.assertTrue(report["all_ok"], report["equations"])

    # ------------------------------------------------------------------
    # The ledger must see the future period
    # ------------------------------------------------------------------
    def test_ledger_sees_the_future_period(self):
        services.receive_payment(
            driver=self.driver, amount=D("600"), payment_date=FIXED_TODAY,
            user=self.user, target_period=self.P5,
        )
        summary = driver_financial_summary(self.driver, FIXED_TODAY)
        starts = [p["start"] for p in summary["periods"]]
        self.assertIn(self.P5[0].isoformat(), starts)

    def test_conservation_holds_with_a_future_allocation(self):
        services.receive_payment(
            driver=self.driver, amount=D("600"), payment_date=FIXED_TODAY,
            user=self.user, target_period=self.P5,
        )
        report = conservation_report(self.driver, FIXED_TODAY)
        self.assertTrue(report["all_ok"], report["equations"])
        for key in ("O", "C", "S", "T"):
            self.assertTrue(report["equations"][key]["ok"], f"{key}: {report['equations'][key]}")

    def test_historical_as_of_is_not_polluted_by_a_future_allocation(self):
        """An as-of report before the allocation's effective date stays clean."""
        services.receive_payment(
            driver=self.driver, amount=D("600"), payment_date=FIXED_TODAY,
            user=self.user, target_period=self.P5,
        )
        earlier = conservation_report(self.driver, date(2026, 6, 1))
        self.assertTrue(earlier["all_ok"], earlier["equations"])
        self.assertNotIn(
            self.P5[0].isoformat(),
            [p["start"] for p in driver_financial_summary(self.driver, date(2026, 6, 1))["periods"]],
        )

    # ------------------------------------------------------------------
    # The payment always belongs to an existing driver
    # ------------------------------------------------------------------
    def test_payment_never_creates_a_driver(self):
        before = Driver.objects.count()
        self.receive(600, self.P1)
        self.assertEqual(Driver.objects.count(), before)

    def test_api_payment_requires_an_existing_driver(self):
        client = APIClient()
        client.force_authenticate(user=self.user)
        response = client.post(
            "/api/payments/",
            {"driver_id": 999999, "amount": "600", "payment_date": FIXED_TODAY.isoformat()},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(Driver.objects.count(), 1)


class PeriodCoverageTests(FinancialTestBase):
    """The driver profile period table (paid / total / remaining per quarter)."""

    P5 = (date(2027, 1, 1), date(2027, 3, 31))

    def _coverage(self):
        client = APIClient()
        client.force_authenticate(user=self.user)
        response = client.get(
            f"/api/drivers/{self.driver.id}/period-coverage/?as_of={FIXED_TODAY.isoformat()}"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return response.json()

    def _row(self, coverage, start):
        return next(r for r in coverage["periods"] if r["start"] == start.isoformat())

    def test_coverage_lists_past_and_future_quarters(self):
        coverage = self._coverage()
        starts = [r["start"] for r in coverage["periods"]]
        self.assertIn(self.P1[0].isoformat(), starts)
        self.assertIn(self.P4[0].isoformat(), starts)
        # upcoming quarters are visible too
        self.assertGreater(len(starts), 4)
        self.assertTrue(any(r["is_future"] for r in coverage["periods"]))

    def test_unpaid_quarter_is_neutral(self):
        coverage = self._coverage()
        row = self._row(coverage, self.P1[0])
        self.assertEqual(row["status"], "unpaid")
        self.assertEqual(row["paid"], "0.00")
        self.assertEqual(row["total"], "600.00")
        self.assertEqual(row["remaining"], "600.00")
        self.assertEqual(row["percent"], 0)

    def test_fully_paid_quarter_is_paid(self):
        self.receive(600, self.P1)
        coverage = self._coverage()
        row = self._row(coverage, self.P1[0])
        self.assertEqual(row["status"], "paid")
        self.assertEqual(row["paid"], "600.00")
        self.assertEqual(row["remaining"], "0.00")
        self.assertEqual(row["percent"], 100)

    def test_partial_quarter_shows_the_paid_share(self):
        self.receive(200, self.P1)
        coverage = self._coverage()
        row = self._row(coverage, self.P1[0])
        self.assertEqual(row["status"], "partial")
        self.assertEqual(row["paid"], "200.00")
        self.assertEqual(row["total"], "600.00")
        self.assertEqual(row["remaining"], "400.00")
        self.assertEqual(row["percent"], 33)

    def test_quarter_lists_its_payment_details(self):
        self.receive(600, self.P1)
        coverage = self._coverage()
        row = self._row(coverage, self.P1[0])
        self.assertEqual(len(row["allocations"]), 1)
        detail = row["allocations"][0]
        self.assertEqual(detail["amount"], "600.00")
        self.assertEqual(detail["payment_date"], FIXED_TODAY.isoformat())
        self.assertIsNone(detail["reversed_at"])

    def test_quarter_shows_the_credit_consumed_on_it(self):
        payment = self.receive(600)  # credit only
        credit = payment.allocations.get(allocation_type=AllocationType.CREDIT)
        services.consume_credit(
            source_allocation=credit, amount=D("100"), target_period=self.P1,
            user=self.user,
        )
        coverage = self._coverage()
        row = self._row(coverage, self.P1[0])
        self.assertEqual(row["paid"], "100.00")
        self.assertEqual(row["status"], "partial")
        self.assertEqual(len(row["consumptions"]), 1)

    def test_cash_revenue_reports_driver_count_without_names(self):
        self.receive(600, self.P1)
        report = cash_revenue_report(FIXED_TODAY)
        self.assertEqual(report["payment_count"], 1)
        self.assertEqual(report["driver_count"], 1)
        self.assertNotIn("driver_code", str(report))
        self.assertNotIn(self.driver.driver_code, str(report))
        self.assertNotIn(self.driver.full_name, str(report))

    def test_cash_revenue_groups_by_month(self):
        self.receive(600, self.P1, payment_date=date(2026, 5, 20))
        self.receive(300, self.P2, payment_date=date(2026, 6, 20))
        report = cash_revenue_report(FIXED_TODAY)
        months = {row["month"]: row for row in report["by_month"]}
        self.assertEqual(months["2026-05"]["total"], "600.00")
        self.assertEqual(months["2026-05"]["count"], 1)
        self.assertEqual(months["2026-06"]["total"], "300.00")
        self.assertEqual(report["driver_count"], 1)


class AsOfTests(FinancialTestBase):
    def _set_voided_at(self, payment, when):
        Payment.objects.filter(pk=payment.pk).update(voided_at=when)

    def test_revenue_as_of_void_n6_r1(self):
        payment = self.receive(800, self.P1, payment_date=date(2026, 2, 20))
        # void on 2026-03-16
        void_time = datetime(2026, 3, 16, 8, 0, tzinfo=dt_timezone.utc)
        services.void_payment(payment=payment, user=self.user, reason="ابطال")
        self._set_voided_at(payment, void_time)
        self.assertEqual(DriverLedger(self.driver, date(2026, 2, 28)).cash_received(), D("800"))
        self.assertEqual(DriverLedger(self.driver, date(2026, 3, 16)).cash_received(), D("0"))
        self.assertEqual(DriverLedger(self.driver, FIXED_TODAY).cash_received(), D("0"))

    def test_correction_as_of_r2(self):
        original = self.receive(400, self.P1, payment_date=date(2026, 2, 20))
        replacement = services.correct_payment(
            payment=original, user=self.user, reason="اصلاح", new_amount=D("800"), target_period=self.P1
        )
        corrected_time = datetime(2026, 3, 10, 8, 0, tzinfo=dt_timezone.utc)
        Payment.objects.filter(pk=original.pk).update(corrected_at=corrected_time)
        Payment.objects.filter(pk=replacement.pk).update(
            effective_date=date(2026, 3, 10), created_at=corrected_time
        )
        self.assertEqual(DriverLedger(self.driver, date(2026, 2, 28)).cash_received(), D("400"))
        self.assertEqual(DriverLedger(self.driver, date(2026, 3, 15)).cash_received(), D("800"))
        self.assertEqual(DriverLedger(self.driver, FIXED_TODAY).cash_received(), D("800"))
        # no as-of date ever sees 1200
        for d in [date(2026, 2, 28), date(2026, 3, 10), date(2026, 3, 15), FIXED_TODAY]:
            self.assertNotEqual(DriverLedger(self.driver, d).cash_received(), D("1200"))

    def test_late_registration_economic_vs_audit_r3(self):
        # cash genuinely received 2026-01-18 but recorded today
        self.receive(700, self.P1, payment_date=date(2026, 1, 18))
        ledger_econ = DriverLedger(self.driver, date(2026, 1, 18))
        self.assertEqual(ledger_econ.cash_received(), D("700"))  # F2 economic
        self.assertEqual(ledger_econ.cash_recorded(), D("0"))  # F5b audit (created today)

    def test_adjustment_partial_as_of_n7(self):
        t = self.transfer(300, self.P1, self.P2)
        Adjustment.objects.filter(pk=t.pk).update(effective_date=date(2026, 3, 1))
        rev = services.reverse_adjustment(adjustment=t, amount=D("100"), user=self.user, reason="r")
        Adjustment.objects.filter(pk=rev.pk).update(effective_date=date(2026, 3, 10))
        ledger = DriverLedger(self.driver, date(2026, 3, 15))
        self.assertEqual(ledger.net_transfer_out(*self.P1), D("200"))

    def test_as_of_stack_t5(self):
        t1 = self.transfer(300, self.P1, self.P4)
        self.transfer(200, self.P2, self.P4)
        self.receive(750, self.P4)
        ledger = DriverLedger(self.driver, FIXED_TODAY)
        state = ledger.period_state(*self.P4)
        self.assertEqual(state.balance, D("350"))
        self.assertEqual(state.transfers[0].remaining, D("150"))


class APITests(FinancialTestBase):
    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_auth_required(self):
        anon = APIClient()
        response = anon.get("/api/payments/")
        self.assertIn(response.status_code, (401, 403))

    def test_receive_payment_api(self):
        response = self.client.post(
            "/api/payments/",
            {
                "driver_id": self.driver.id,
                "amount": "700",
                "payment_date": FIXED_TODAY.isoformat(),
                "target_period_start": self.P1[0].isoformat(),
                "target_period_end": self.P1[1].isoformat(),
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(len(response.data["allocations"]), 2)
        self.assertConserved()

    def test_idempotency_key(self):
        payload = {
            "driver_id": self.driver.id,
            "amount": "600",
            "payment_date": FIXED_TODAY.isoformat(),
            "target_period_start": self.P1[0].isoformat(),
            "target_period_end": self.P1[1].isoformat(),
            "idempotency_key": "unique-key-1",
        }
        r1 = self.client.post("/api/payments/", payload, format="json")
        r2 = self.client.post("/api/payments/", payload, format="json")
        self.assertEqual(r1.status_code, 201)
        self.assertEqual(r1.data["id"], r2.data["id"])
        self.assertEqual(Payment.objects.count(), 1)

    def test_fee_start_date_readonly_on_update(self):
        response = self.client.patch(
            f"/api/drivers/{self.driver.id}/",
            {"fee_start_date": "2027-01-01"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.driver.refresh_from_db()
        self.assertEqual(self.driver.fee_start_date, date(2026, 1, 1))  # unchanged

    def test_fee_start_date_endpoint_w10(self):
        response = self.client.post(
            f"/api/drivers/{self.driver.id}/fee-start-date/",
            {"requested_fee_start_date": "2026-11-01", "reason": "تغییر era"},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["effective_fee_start_date"], "2027-01-01")

    def test_void_requires_reason(self):
        payment = self.receive(600, self.P1)
        response = self.client.post(f"/api/payments/{payment.id}/void/", {}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_no_delete_endpoint(self):
        payment = self.receive(600, self.P1)
        response = self.client.delete(f"/api/payments/{payment.id}/")
        self.assertEqual(response.status_code, 405)

    def test_reversal_error_code_w9_hint(self):
        t = self.transfer(300, self.P1, self.P2)
        self.receive(900, self.P2)
        response = self.client.post(
            f"/api/adjustments/{t.id}/reverse/",
            {"amount": "300", "reason": "بازگشت"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "reversal_exceeds_remaining_transfer")

    def test_financial_summary_endpoint(self):
        self.receive(600, self.P1)
        response = self.client.get(f"/api/drivers/{self.driver.id}/financial-summary/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["overdue_debt"], "1200.00")

    def test_cash_revenue_endpoint(self):
        self.receive(500, self.P1, payment_date=date(2026, 2, 20))
        response = self.client.get(
            "/api/reports/cash-revenue/",
            {"date_from": "2026-02-01", "date_to": "2026-02-28"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["cash_revenue"], "500.00")


class ConcurrencyTests(TransactionTestCase):
    """V2/V3a/V3b/V7/V8 — file-based test DB shared across connections."""

    databases = {"default"}

    def setUp(self):
        patch_now = mock.patch.object(timezone, "now", return_value=FIXED_NOW)
        patch_today = mock.patch.object(timezone, "localdate", return_value=FIXED_TODAY)
        patch_now.start()
        patch_today.start()
        self.addCleanup(patch_now.stop)
        self.addCleanup(patch_today.stop)
        # TransactionTestCase flushes tables between tests, removing the
        # migration-seeded FeeSchedule row; re-seed it here.
        FeeSchedule.objects.get_or_create(
            effective_from=date(1900, 1, 1),
            defaults={"amount": D("600"), "reason": "seed", "created_by": None},
        )
        self.user = User.objects.create_user(username="admin", password="pass", is_superuser=True)
        self.driver = Driver.objects.create(
            driver_code="C1", full_name="تست", father_name="پ", phone="0700000000",
            tazkira_number="T1", plate_number="پ۱", address="کابل",
            registration_date=date(2026, 1, 1), fee_start_date=date(2026, 1, 1),
        )
        DriverFeeHistory.objects.create(
            driver=self.driver, requested_fee_start_date=date(2026, 1, 1),
            effective_fee_start_date=date(2026, 1, 1), reason="init", changed_by=self.user,
        )
        self.P2 = (date(2026, 4, 1), date(2026, 6, 30))

    def _make_credit(self, amount):
        payment = services.receive_payment(
            driver=self.driver, amount=D(amount), payment_date=FIXED_TODAY, user=self.user
        )
        return payment.allocations.get(allocation_type=AllocationType.CREDIT)

    def test_concurrent_consumption_v3a(self):
        credit = self._make_credit(300)
        results = []
        barrier = threading.Barrier(2)

        def worker():
            from django.db import connection as thread_conn

            try:
                barrier.wait(timeout=5)
                services.consume_credit(
                    source_allocation=credit, amount=D("200"),
                    target_period=self.P2, user=self.user,
                    consumption_id=uuid.uuid4().hex,
                )
                results.append("ok")
            except FinancialError:
                results.append("rejected")
            except Exception as exc:  # lock errors also acceptable as failure
                results.append(f"error:{type(exc).__name__}")
            finally:
                thread_conn.close()

        threads = [threading.Thread(target=worker) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15)
        self.assertEqual(results.count("ok"), 1, results)
        credit.refresh_from_db()
        consumed = sum(c.consumption_amount for c in credit.consumptions.filter(reversed_at__isnull=True))
        self.assertEqual(consumed, D("200"))
        self.assertEqual(DriverLedger(self.driver).source_available(credit), D("100"))

    def test_duplicate_consumption_idempotency_v3b(self):
        credit = self._make_credit(300)
        cid = "fixed-consumption-id"
        c1 = services.consume_credit(
            source_allocation=credit, amount=D("200"), target_period=self.P2,
            user=self.user, consumption_id=cid,
        )
        c2 = services.consume_credit(
            source_allocation=credit, amount=D("200"), target_period=self.P2,
            user=self.user, consumption_id=cid,
        )
        self.assertEqual(c1.id, c2.id)
        self.assertEqual(AllocationConsumption.objects.filter(consumption_id=cid).count(), 1)
        # a fresh attempt now sees updated balance and is rejected
        with self.assertRaises(FinancialError):
            services.consume_credit(
                source_allocation=credit, amount=D("200"), target_period=self.P2,
                user=self.user, consumption_id=uuid.uuid4().hex,
            )

    def test_rollback_after_failure_v7(self):
        credit = self._make_credit(300)
        before_alloc = PaymentAllocation.objects.count()
        before_cons = AllocationConsumption.objects.count()
        with self.assertRaises(FinancialError):
            services.consume_credit(
                source_allocation=credit, amount=D("500"), target_period=self.P2, user=self.user
            )
        self.assertEqual(PaymentAllocation.objects.count(), before_alloc)
        self.assertEqual(AllocationConsumption.objects.count(), before_cons)

    def test_write_lock_and_timeout_v2_v8(self):
        """A concurrent writer must block the consuming write; nothing partial survives.

        SQLite: an external connection holds a write lock with BEGIN IMMEDIATE
        and the Django connection hits its lock timeout.

        PostgreSQL: an external connection holds an uncommitted INSERT on the
        unique `consumption_id` index, so the Django connection blocks on that
        index and hits its `lock_timeout`. PostgreSQL has no database-level
        write lock, so the unique index is the lock that is contended here.
        """
        if connection.vendor == "sqlite":
            self._write_lock_and_timeout_sqlite()
        else:
            self._write_lock_and_timeout_postgresql()

    def _write_lock_and_timeout_sqlite(self):
        credit = self._make_credit(300)
        db_path = connection.settings_dict["NAME"]
        external = sqlite3.connect(db_path, timeout=5, uri=True)
        external.execute("BEGIN IMMEDIATE")
        try:
            # shrink the Django connection timeout and reconnect
            connections.close_all()
            old_timeout = connection.settings_dict["OPTIONS"].get("timeout", 20)
            connection.settings_dict["OPTIONS"]["timeout"] = 0.3
            try:
                with self.assertRaises(Exception):
                    services.consume_credit(
                        source_allocation=credit, amount=D("100"),
                        target_period=self.P2, user=self.user,
                    )
            finally:
                connection.settings_dict["OPTIONS"]["timeout"] = old_timeout
                connections.close_all()
        finally:
            external.rollback()
            external.close()
        # no partial write survived
        self.assertEqual(AllocationConsumption.objects.count(), 0)
        # after lock release a retry with a fresh id succeeds exactly once
        services.consume_credit(
            source_allocation=credit, amount=D("100"), target_period=self.P2,
            user=self.user, consumption_id="after-lock",
        )
        self.assertEqual(AllocationConsumption.objects.count(), 1)

    def _write_lock_and_timeout_postgresql(self):
        import psycopg2

        credit = self._make_credit(300)
        cfg = connection.settings_dict
        external = psycopg2.connect(
            dbname=cfg["NAME"],
            user=cfg["USER"],
            password=cfg["PASSWORD"],
            host=cfg["HOST"],
            port=cfg["PORT"],
        )
        external.autocommit = False
        try:
            # An uncommitted INSERT on the unique consumption_id index holds
            # the index entry, so any writer using the same id must wait.
            with external.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO payments_allocationconsumption
                      (source_allocation_id, consumption_amount, target_period_start,
                       target_period_end, effective_date, consumption_id, consumed_by_id,
                       reason, reversal_reason, consumed_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, '', '', %s)
                    """,
                    [
                        credit.id,
                        D("100"),
                        self.P2[0],
                        self.P2[1],
                        FIXED_TODAY,
                        "locked-consumption",
                        self.user.id,
                        FIXED_NOW,
                    ],
                )
            # The Django connection must give up waiting for that lock.
            with connection.cursor() as cur:
                cur.execute("SET lock_timeout = '300ms'")
            try:
                with self.assertRaises(Exception):
                    services.consume_credit(
                        source_allocation=credit,
                        amount=D("100"),
                        target_period=self.P2,
                        user=self.user,
                        consumption_id="locked-consumption",
                    )
            finally:
                with connection.cursor() as cur:
                    cur.execute("SET lock_timeout = DEFAULT")
        finally:
            external.rollback()
            external.close()
        # no partial write survived
        self.assertEqual(AllocationConsumption.objects.count(), 0)
        # after lock release a retry with a fresh id succeeds exactly once
        services.consume_credit(
            source_allocation=credit, amount=D("100"), target_period=self.P2,
            user=self.user, consumption_id="after-lock",
        )
        self.assertEqual(AllocationConsumption.objects.count(), 1)


class OnlinePaymentTests(APITestCase):
    """Online payment tests — independent from guaranteed driver financial system."""

    def setUp(self):
        self.user = User.objects.create_superuser(
            username="admin_online", password="StrongPass-2026!"
        )
        self.client.force_authenticate(user=self.user)

        self.online_driver = Driver.objects.create(
            driver_code="D-ONLINE01",
            full_name="رانندهٔ آنلاین یک",
            father_name="پدر تستی",
            phone="0700000001",
            tazkira_number="T123461",
            plate_number="پ 12361",
            address="کابل، افغانستان",
            registration_date=date(2026, 11, 9),
            fee_start_date=date(2026, 11, 9),
            status=True,
            driver_type="online",
        )
        self.guaranteed_driver = Driver.objects.create(
            driver_code="D-GUA01",
            full_name="رانندهٔ تضمینی یک",
            father_name="پدر تستی",
            phone="0700000002",
            tazkira_number="T123462",
            plate_number="پ 12362",
            address="کابل، افغانستان",
            registration_date=date(2026, 11, 9),
            fee_start_date=date(2026, 11, 9),
            status=True,
            driver_type="guaranteed",
        )

    # ------------------------------------------------------------------
    # Create online payment
    # ------------------------------------------------------------------
    def test_create_online_payment_success(self):
        """Successful online payment creation."""
        response = self.client.post(
            "/api/online-payments/",
            {
                "driver_id": self.online_driver.id,
                "amount": "600",
                "payment_date": "2026-11-09",
                "purpose": "تست پرداخت آنلاین",
                "description": "توضیحات تست",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["driver_code"], "D-ONLINE01")
        self.assertEqual(response.data["amount"], "600.00")
        self.assertEqual(response.data["status"], "received")
        self.assertEqual(OnlinePayment.objects.count(), 1)

    def test_create_online_payment_rejects_guaranteed_driver(self):
        """Online payment API rejects guaranteed drivers."""
        response = self.client.post(
            "/api/online-payments/",
            {
                "driver_id": self.guaranteed_driver.id,
                "amount": "600",
                "payment_date": "2026-11-09",
                "purpose": "تست",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(OnlinePayment.objects.count(), 0)

    def test_create_online_payment_zero_amount_rejected(self):
        """Zero amount is rejected."""
        response = self.client.post(
            "/api/online-payments/",
            {
                "driver_id": self.online_driver.id,
                "amount": "0",
                "payment_date": "2026-11-09",
                "purpose": "تست",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_online_payment_negative_amount_rejected(self):
        """Negative amount is rejected."""
        response = self.client.post(
            "/api/online-payments/",
            {
                "driver_id": self.online_driver.id,
                "amount": "-100",
                "payment_date": "2026-11-09",
                "purpose": "تست",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_online_payment_future_date_rejected(self):
        """Future payment date is rejected."""
        response = self.client.post(
            "/api/online-payments/",
            {
                "driver_id": self.online_driver.id,
                "amount": "600",
                "payment_date": "2027-12-31",
                "purpose": "تست",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_online_payment_missing_purpose_rejected(self):
        """Purpose is required."""
        response = self.client.post(
            "/api/online-payments/",
            {
                "driver_id": self.online_driver.id,
                "amount": "600",
                "payment_date": "2026-11-09",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_online_payment_guaranteed_driver_api(self):
        """Guaranteed payment API rejects online driver (and vice versa isolation)."""
        # Guaranteed payment API should reject online driver
        response = self.client.post(
            "/api/payments/",
            {
                "driver_id": self.online_driver.id,
                "amount": "600",
                "payment_date": "2026-11-09",
                "target_period_start": "2026-11-09",
                "target_period_end": "2027-02-08",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # ------------------------------------------------------------------
    # Online payment detail
    # ------------------------------------------------------------------
    def test_online_payment_detail(self):
        """Retrieve online payment detail."""
        op = OnlinePayment.objects.create(
            driver=self.online_driver,
            amount=D("600"),
            payment_date=date(2026, 11, 9),
            purpose="تست",
            description="توضیحات",
            recorded_by=self.user,
        )
        response = self.client.get(f"/api/online-payments/{op.pk}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], op.id)
        self.assertEqual(response.data["driver_code"], "D-ONLINE01")
        self.assertEqual(response.data["amount"], "600.00")

    # ------------------------------------------------------------------
    # Online payment summary
    # ------------------------------------------------------------------
    def test_online_payment_summary(self):
        """Online payment summary returns totals per driver and grand total."""
        OnlinePayment.objects.create(
            driver=self.online_driver,
            amount=D("600"),
            payment_date=date(2026, 11, 9),
            purpose="تست 1",
            recorded_by=self.user,
        )
        OnlinePayment.objects.create(
            driver=self.online_driver,
            amount=D("400"),
            payment_date=date(2026, 11, 10),
            purpose="تست 2",
            recorded_by=self.user,
        )
        response = self.client.get("/api/online-payments/summary/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["total_amount"], "1000.00")
        self.assertEqual(response.data["total_count"], 2)
        self.assertEqual(response.data["driver_count"], 1)

    # ------------------------------------------------------------------
    # Online payment date filter
    # ------------------------------------------------------------------
    def test_online_payment_date_filter(self):
        """Filter online payments by date range."""
        OnlinePayment.objects.create(
            driver=self.online_driver,
            amount=D("600"),
            payment_date=date(2026, 11, 9),
            purpose="تست 1",
            recorded_by=self.user,
        )
        OnlinePayment.objects.create(
            driver=self.online_driver,
            amount=D("400"),
            payment_date=date(2026, 11, 10),
            purpose="تست 2",
            recorded_by=self.user,
        )
        response = self.client.get(
            "/api/online-payments/?date_from=2026-11-10&date_to=2026-11-10"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["total_count"], 1)

    # ------------------------------------------------------------------
    # Online payment void
    # ------------------------------------------------------------------
    def test_void_online_payment(self):
        """Void an online payment."""
        op = OnlinePayment.objects.create(
            driver=self.online_driver,
            amount=D("600"),
            payment_date=date(2026, 11, 9),
            purpose="تست",
            recorded_by=self.user,
        )
        response = self.client.post(
            f"/api/online-payments/{op.pk}/void/",
            {"reason": "تست ابطال"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        op.refresh_from_db()
        self.assertEqual(op.status, "voided")
        self.assertIsNotNone(op.voided_at)
        self.assertEqual(op.voided_by, self.user)
        self.assertEqual(op.void_reason, "تست ابطال")

    def test_void_already_voided_payment_rejected(self):
        """Voiding an already voided payment is rejected."""
        op = OnlinePayment.objects.create(
            driver=self.online_driver,
            amount=D("600"),
            payment_date=date(2026, 11, 9),
            purpose="تست",
            recorded_by=self.user,
            status=OnlinePaymentStatus.VOIDED,
            voided_at=timezone.now(),
            voided_by=self.user,
            void_reason="تست قبلی",
        )
        response = self.client.post(
            f"/api/online-payments/{op.pk}/void/",
            {"reason": "تست دوباره"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # ------------------------------------------------------------------
    # Financial isolation: guaranteed driver cannot use online payment API
    # ------------------------------------------------------------------
    def test_guaranteed_driver_cannot_use_online_payment_api(self):
        """Guaranteed driver cannot create online payment."""
        response = self.client.post(
            "/api/online-payments/",
            {
                "driver_id": self.guaranteed_driver.id,
                "amount": "600",
                "payment_date": "2026-11-09",
                "purpose": "تست",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(OnlinePayment.objects.count(), 0)

    # ------------------------------------------------------------------
    # Conservation: guaranteed payment calculations unaffected
    # ------------------------------------------------------------------
    def test_guaranteed_payments_unaffected_by_online(self):
        """Creating online payments does not affect guaranteed driver calculations."""
        initial_payments = Payment.objects.count()
        initial_allocations = PaymentAllocation.objects.count()

        # Create an online payment
        response = self.client.post(
            "/api/online-payments/",
            {
                "driver_id": self.online_driver.id,
                "amount": "600",
                "payment_date": "2026-11-09",
                "purpose": "تست",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # Guaranteed payment calculations unaffected
        self.assertEqual(Payment.objects.count(), initial_payments)
        self.assertEqual(PaymentAllocation.objects.count(), initial_allocations)

    # ------------------------------------------------------------------
    # Purpose filter and per-driver totals
    # ------------------------------------------------------------------
    def test_online_payment_purpose_filter(self):
        """Filter online payments by purpose (بابت پرداخت)."""
        OnlinePayment.objects.create(
            driver=self.online_driver,
            amount=D("600"),
            payment_date=date(2026, 11, 9),
            purpose="عمرانی",
            recorded_by=self.user,
        )
        OnlinePayment.objects.create(
            driver=self.online_driver,
            amount=D("400"),
            payment_date=date(2026, 11, 10),
            purpose="ایمنی",
            recorded_by=self.user,
        )
        response = self.client.get("/api/online-payments/?purpose=عمرانی")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["total_count"], 1)
        self.assertEqual(response.data["results"][0]["purpose"], "عمرانی")

    def test_online_payment_summary_for_single_driver(self):
        """Summary filtered by driver returns only that driver's total."""
        OnlinePayment.objects.create(
            driver=self.online_driver,
            amount=D("600"),
            payment_date=date(2026, 11, 9),
            purpose="تست 1",
            recorded_by=self.user,
        )
        other_online = Driver.objects.create(
            driver_code="D-ONLINE02",
            full_name="رانندهٔ آنلاین دو",
            father_name="پدر تستی",
            phone="0700000003",
            tazkira_number="T123463",
            plate_number="پ 12363",
            address="کابل، افغانستان",
            registration_date=date(2026, 11, 9),
            fee_start_date=date(2026, 11, 9),
            status=True,
            driver_type="online",
        )
        OnlinePayment.objects.create(
            driver=other_online,
            amount=D("250"),
            payment_date=date(2026, 11, 10),
            purpose="تست 2",
            recorded_by=self.user,
        )

        all_drivers = self.client.get("/api/online-payments/summary/")
        self.assertEqual(all_drivers.data["total_amount"], "850.00")
        self.assertEqual(all_drivers.data["driver_count"], 2)

        one_driver = self.client.get(
            f"/api/online-payments/summary/?driver_id={self.online_driver.id}"
        )
        self.assertEqual(one_driver.data["total_amount"], "600.00")
        self.assertEqual(one_driver.data["driver_count"], 1)

    def test_online_payment_history_for_driver(self):
        """Payment history for a single driver."""
        OnlinePayment.objects.create(
            driver=self.online_driver,
            amount=D("600"),
            payment_date=date(2026, 11, 9),
            purpose="عمرانی",
            recorded_by=self.user,
        )
        OnlinePayment.objects.create(
            driver=self.online_driver,
            amount=D("400"),
            payment_date=date(2026, 11, 10),
            purpose="ایمنی",
            recorded_by=self.user,
        )
        response = self.client.get(
            f"/api/online-payments/?driver_id={self.online_driver.id}"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["total_count"], 2)
        for item in response.data["results"]:
            self.assertEqual(item["driver_code"], "D-ONLINE01")

    # ------------------------------------------------------------------
    # Append-only: hard delete forbidden
    # ------------------------------------------------------------------
    def test_online_payment_hard_delete_forbidden(self):
        """Online payments are append-only — hard delete raises PermissionError."""
        op = OnlinePayment.objects.create(
            driver=self.online_driver,
            amount=D("600"),
            payment_date=date(2026, 11, 9),
            purpose="تست",
            recorded_by=self.user,
        )
        with self.assertRaises(PermissionError):
            op.delete()
        self.assertTrue(OnlinePayment.objects.filter(pk=op.pk).exists())

    # ------------------------------------------------------------------
    # Report isolation: guaranteed payments never appear in online reports
    # ------------------------------------------------------------------
    def test_guaranteed_payment_not_in_online_report(self):
        """Guaranteed Payment rows never appear in online payment reports."""
        OnlinePayment.objects.create(
            driver=self.online_driver,
            amount=D("600"),
            payment_date=date(2026, 11, 9),
            purpose="آنلاین",
            recorded_by=self.user,
        )
        # Create a guaranteed payment for the guaranteed driver
        services.receive_payment(
            driver=self.guaranteed_driver,
            amount=D("600"),
            payment_date=date(2026, 11, 9),
            user=self.user,
            target_period=(date(2026, 11, 9), date(2027, 2, 8)),
        )
        response = self.client.get("/api/online-payments/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["total_count"], 1)
        self.assertEqual(response.data["results"][0]["driver_code"], "D-ONLINE01")

        # The guaranteed payment is still tracked in the guaranteed ledger only
        self.assertEqual(Payment.objects.filter(driver=self.guaranteed_driver).count(), 1)
        self.assertEqual(
            OnlinePayment.objects.filter(driver=self.online_driver).count(), 1
        )

    def test_guaranteed_cash_revenue_report_excludes_online(self):
        """Guaranteed cash revenue report excludes online payments."""
        from .reporting import cash_revenue_report

        before = cash_revenue_report()["cash_revenue"]
        OnlinePayment.objects.create(
            driver=self.online_driver,
            amount=D("600"),
            payment_date=date(2026, 11, 9),
            purpose="آنلاین",
            recorded_by=self.user,
        )
        after = cash_revenue_report()["cash_revenue"]
        self.assertEqual(before, after)
        self.assertEqual(after, "0.00")

    # ------------------------------------------------------------------
    # Database-level enforcement (raw SQL bypass attempt)
    # ------------------------------------------------------------------
    def test_database_rejects_online_payment_for_guaranteed_driver(self):
        """Raw SQL insert of an online payment for a guaranteed driver is rejected."""
        from django.db import connection

        with self.assertRaises(Exception):
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO payments_onlinepayment
                        (amount, payment_date, purpose, description, status,
                         driver_id, recorded_by_id, created_at)
                    VALUES (500, '2026-11-09', 'تست', '', 'received', %s, %s, '2026-11-10 08:00:00')
                    """,
                    [self.guaranteed_driver.id, self.user.id],
                )

    def test_database_rejects_guaranteed_payment_for_online_driver(self):
        """Raw SQL insert of a guaranteed payment for an online driver is rejected."""
        from django.db import connection

        with self.assertRaises(Exception):
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO payments_payment
                        (amount, payment_date, effective_date, receipt_number,
                         idempotency_key, status, void_reason, correction_reason,
                         driver_id, created_by_id, created_at, updated_at)
                    VALUES (500, '2026-11-09', '2026-11-09', '', NULL, 'received',
                            '', '', %s, %s, '2026-11-10 08:00:00', '2026-11-10 08:00:00')
                    """,
                    [self.online_driver.id, self.user.id],
                )

    # ------------------------------------------------------------------
    # Permissions: write operations require IsManager
    # ------------------------------------------------------------------
    def test_non_manager_cannot_create_online_payment(self):
        """Non-manager authenticated user cannot create an online payment."""
        non_manager = User.objects.create_user(
            username="clerk_online", password="pass123"
        )
        self.client.force_authenticate(user=non_manager)
        response = self.client.post(
            "/api/online-payments/",
            {
                "driver_id": self.online_driver.id,
                "amount": "600",
                "payment_date": "2026-11-09",
                "purpose": "تست",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(OnlinePayment.objects.count(), 0)

    def test_non_manager_cannot_void_online_payment(self):
        """Non-manager authenticated user cannot void an online payment."""
        op = OnlinePayment.objects.create(
            driver=self.online_driver,
            amount=D("600"),
            payment_date=date(2026, 11, 9),
            purpose="تست",
            recorded_by=self.user,
        )
        non_manager = User.objects.create_user(
            username="clerk_online2", password="pass123"
        )
        self.client.force_authenticate(user=non_manager)
        response = self.client.post(
            f"/api/online-payments/{op.pk}/void/",
            {"reason": "تست"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        op.refresh_from_db()
        self.assertEqual(op.status, "received")

    # ------------------------------------------------------------------
    # Void requires a non-empty reason
    # ------------------------------------------------------------------
    def test_void_online_payment_requires_reason(self):
        """Voiding without a reason is rejected."""
        op = OnlinePayment.objects.create(
            driver=self.online_driver,
            amount=D("600"),
            payment_date=date(2026, 11, 9),
            purpose="تست",
            recorded_by=self.user,
        )
        response = self.client.post(
            f"/api/online-payments/{op.pk}/void/",
            {"reason": ""},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        op.refresh_from_db()
        self.assertEqual(op.status, "received")
        self.assertIsNone(op.voided_at)

    # ------------------------------------------------------------------
    # Audit trail
    # ------------------------------------------------------------------
    def test_online_payment_audit_trail(self):
        """Each online payment records who, when, and why."""
        op = OnlinePayment.objects.create(
            driver=self.online_driver,
            amount=D("600"),
            payment_date=date(2026, 11, 9),
            purpose="تست",
            description="توضیحات",
            recorded_by=self.user,
        )
        self.assertEqual(op.recorded_by, self.user)
        self.assertIsNotNone(op.created_at)
        self.assertEqual(op.status, "received")

        response = self.client.post(
            f"/api/online-payments/{op.pk}/void/",
            {"reason": "دلیل ابطال تست"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        op.refresh_from_db()
        self.assertEqual(op.voided_by, self.user)
        self.assertIsNotNone(op.voided_at)
        self.assertEqual(op.void_reason, "دلیل ابطال تست")

        detail = self.client.get(f"/api/online-payments/{op.pk}/")
        self.assertEqual(detail.data["recorded_by_name"], self.user.username)
        self.assertEqual(detail.data["voided_by_name"], self.user.username)
        self.assertEqual(detail.data["void_reason"], "دلیل ابطال تست")

    # ------------------------------------------------------------------
    # Correction workflow (append-only)
    # ------------------------------------------------------------------
    def test_correct_online_payment_creates_replacement(self):
        """Correcting an online payment marks the original and creates a new row."""
        original = OnlinePayment.objects.create(
            driver=self.online_driver,
            amount=D("600"),
            payment_date=date(2026, 11, 9),
            purpose="عمرانی",
            description="توضیحات",
            recorded_by=self.user,
        )
        response = self.client.post(
            f"/api/online-payments/{original.pk}/correct/",
            {
                "reason": "مبلغ اشتباه بود",
                "new_amount": "800",
                "new_purpose": "عمرانی اصلاح‌شده",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["amount"], "800.00")
        self.assertEqual(response.data["purpose"], "عمرانی اصلاح‌شده")
        self.assertEqual(response.data["correction_of"], original.pk)

        original.refresh_from_db()
        self.assertEqual(original.status, "corrected")
        self.assertEqual(original.corrected_by, self.user)
        self.assertIsNotNone(original.corrected_at)
        self.assertEqual(original.correction_reason, "مبلغ اشتباه بود")
        # Original amount is unchanged — append-only
        self.assertEqual(original.amount, D("600"))
        self.assertEqual(OnlinePayment.objects.count(), 2)

    def test_correct_already_voided_online_payment_rejected(self):
        """A voided online payment cannot be corrected."""
        op = OnlinePayment.objects.create(
            driver=self.online_driver,
            amount=D("600"),
            payment_date=date(2026, 11, 9),
            purpose="تست",
            recorded_by=self.user,
            status=OnlinePaymentStatus.VOIDED,
            voided_at=timezone.now(),
            voided_by=self.user,
            void_reason="قبلاً باطل شده",
        )
        response = self.client.post(
            f"/api/online-payments/{op.pk}/correct/",
            {"reason": "تست", "new_amount": "800"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(OnlinePayment.objects.count(), 1)

    def test_correct_online_payment_requires_reason(self):
        """Correction without a reason is rejected."""
        op = OnlinePayment.objects.create(
            driver=self.online_driver,
            amount=D("600"),
            payment_date=date(2026, 11, 9),
            purpose="تست",
            recorded_by=self.user,
        )
        response = self.client.post(
            f"/api/online-payments/{op.pk}/correct/",
            {"reason": "", "new_amount": "800"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        op.refresh_from_db()
        self.assertEqual(op.status, "received")

    def test_non_manager_cannot_correct_online_payment(self):
        """Non-manager authenticated user cannot correct an online payment."""
        op = OnlinePayment.objects.create(
            driver=self.online_driver,
            amount=D("600"),
            payment_date=date(2026, 11, 9),
            purpose="تست",
            recorded_by=self.user,
        )
        non_manager = User.objects.create_user(
            username="clerk_online3", password="pass123"
        )
        self.client.force_authenticate(user=non_manager)
        response = self.client.post(
            f"/api/online-payments/{op.pk}/correct/",
            {"reason": "تست", "new_amount": "800"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        op.refresh_from_db()
        self.assertEqual(op.status, "received")

    def test_corrected_online_payment_excluded_from_summary(self):
        """Corrected and voided online payments are excluded from totals."""
        op = OnlinePayment.objects.create(
            driver=self.online_driver,
            amount=D("600"),
            payment_date=date(2026, 11, 9),
            purpose="تست",
            recorded_by=self.user,
        )
        self.client.post(
            f"/api/online-payments/{op.pk}/correct/",
            {"reason": "اصلاح", "new_amount": "800"},
            format="json",
        )
        response = self.client.get("/api/online-payments/summary/")
        # Only the replacement (received) counts
        self.assertEqual(response.data["total_amount"], "800.00")
        self.assertEqual(response.data["total_count"], 1)

    # ------------------------------------------------------------------
    # Regression: driver type triggers must survive all migrations
    # ------------------------------------------------------------------
    def test_driver_type_triggers_exist(self):
        """All four driver type triggers are present after the migration chain.

        SQLite rebuilds a table (dropping its triggers) on AlterField, so
        migration 0007 re-installs them. This test guards against a future
        migration silently dropping them again.
        """
        from django.db import connection

        expected = {
            "payments_pay_driver_type_ins",
            "payments_pay_driver_type_upd",
            "payments_onlpay_driver_type_ins",
            "payments_onlpay_driver_type_upd",
        }
        if connection.vendor == "sqlite":
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT name FROM sqlite_master WHERE type='trigger'"
                )
                found = {row[0] for row in cursor.fetchall()}
            self.assertTrue(
                expected.issubset(found),
                f"Missing driver type triggers: {sorted(expected - found)}",
            )