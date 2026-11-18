"""Automated API tests for the Driver module."""

import shutil
import tempfile
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from datetime import date
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import override_settings
from django.utils import timezone
from decimal import Decimal as D
from PIL import Image
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from apps.payments import services
from apps.documents.models import Document
from apps.payments.models import (
    AllocationType,
    OnlinePayment,
    Payment,
    PaymentAllocation,
    PaymentRefund,
)
from apps.payments.periods import fee_for_period, period_for_start

from .models import Driver, DriverFeeHistory


def make_image(name="photo.png", size=(40, 40), color="navy"):
    buffer = BytesIO()
    Image.new("RGB", size, color).save(buffer, format="PNG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")


def driver_payload(**overrides):
    data = {
        "driver_code": "D-10001",
        "full_name": "احمد علی",
        "father_name": "محمد",
        "phone": "0700123456",
        "tazkira_number": "1234567890",
        "plate_number": "KBL 12345",
        "address": "کابل، ناحیه ۴",
        "registration_date": date(2026, 1, 1),
        "fee_start_date": date(2026, 11, 9),
        "status": True,
    }
    data.update(overrides)
    return data


class DriverApiTests(APITestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._media_dir = tempfile.mkdtemp(prefix="dm-test-media-")
        cls._override = override_settings(MEDIA_ROOT=cls._media_dir)
        cls._override.enable()

    @classmethod
    def tearDownClass(cls):
        cls._override.disable()
        shutil.rmtree(cls._media_dir, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username="admin", password="StrongPass-2026!"
        )
        self.client.force_authenticate(user=self.user)

    def _initial_payment_payload(self, driver_code, amount):
        return driver_payload(
            driver_code=driver_code,
            initial_payment_amount=str(amount),
            initial_payment_date="2026-11-10",
            initial_payment_period_start="2026-11-09",
            initial_payment_idempotency_key=f"initial-{driver_code}",
        )

    # ------------------------------------------------------------------
    # Authentication and permissions
    # ------------------------------------------------------------------
    def test_driver_endpoints_require_authentication(self):
        self.client.force_authenticate(user=None)
        for url in ("/api/drivers/", "/api/drivers/stats/", "/api/drivers/1/"):
            response = self.client.get(url)
            self.assertIn(response.status_code, (401, 403))

    def test_anonymous_cannot_read_photo(self):
        driver = Driver.objects.create(**driver_payload())
        self.client.force_authenticate(user=None)
        response = self.client.get(f"/api/drivers/{driver.pk}/photo/")
        self.assertIn(response.status_code, (401, 403))

    def test_non_manager_cannot_create_driver(self):
        """Non-manager authenticated user cannot create a driver."""
        non_manager = get_user_model().objects.create_user(
            username="clerk", password="pass123"
        )
        self.client.force_authenticate(user=non_manager)
        response = self.client.post("/api/drivers/", driver_payload(), format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_create_update_and_deactivate_driver(self):
        admin = get_user_model().objects.create_user(
            username="driver-admin", password="pass123", is_staff=True
        )
        self.client.force_authenticate(user=admin)

        response = self.client.post("/api/drivers/", driver_payload(), format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        driver_id = response.data["id"]

        response = self.client.patch(
            f"/api/drivers/{driver_id}/",
            {"address": "آدرس تازه"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

        response = self.client.post(
            f"/api/drivers/{driver_id}/status/",
            {"status": False},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertFalse(Driver.objects.get(pk=driver_id).status)

    def test_authenticated_staff_admin_can_create_driver_without_superuser_flag(self):
        password = "StrongPass-2026!"
        admin = get_user_model().objects.create_user(
            username="live-admin",
            password=password,
            is_staff=True,
            is_superuser=False,
            is_active=True,
        )
        client = APIClient()
        self.assertTrue(client.login(username=admin.username, password=password))

        response = client.post("/api/drivers/", driver_payload(), format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(
            client.get("/api/users/").status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_driver_creation_without_initial_payment_creates_no_payment(self):
        response = self.client.post(
            "/api/drivers/", driver_payload(), format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertFalse(Payment.objects.filter(driver_id=response.data["id"]).exists())

    def test_zero_initial_payment_creates_no_payment(self):
        response = self.client.post(
            "/api/drivers/",
            driver_payload(initial_payment_amount="0"),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertFalse(Payment.objects.filter(driver_id=response.data["id"]).exists())

    def test_full_initial_payment_is_allocated_to_selected_period_and_coverage(self):
        period_start = date(2026, 11, 9)
        amount = fee_for_period(period_start)
        response = self.client.post(
            "/api/drivers/",
            self._initial_payment_payload("D-INIT-FULL", amount),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

        payment = Payment.objects.get(driver_id=response.data["id"])
        self.assertEqual(payment.amount, amount)
        driver = Driver.objects.get(pk=response.data["id"])
        self.assertEqual(driver.period_calendar, Driver.PERIOD_CALENDAR_JALALI)
        allocation = payment.allocations.get()
        self.assertEqual(allocation.allocation_type, AllocationType.FEE_PERIOD)
        self.assertEqual(allocation.target_period_start, period_start)
        self.assertEqual(
            allocation.target_period_end,
            period_for_start(driver, period_start)[1],
        )
        self.assertEqual(allocation.target_period_end, date(2027, 2, 6))

        coverage_response = self.client.get(
            f"/api/drivers/{response.data['id']}/period-coverage/"
            "?as_of=2026-11-15"
        )
        self.assertEqual(coverage_response.status_code, status.HTTP_200_OK)
        period = next(
            item
            for item in coverage_response.data["periods"]
            if item["start"] == period_start.isoformat()
        )
        self.assertEqual(period["paid"], str(amount))
        self.assertEqual(period["remaining"], "0.00")
        self.assertEqual(period["status"], "paid")

    def test_partial_initial_payment_updates_period_coverage(self):
        fee = fee_for_period(date(2026, 11, 9))
        amount = fee - D("1")
        response = self.client.post(
            "/api/drivers/",
            self._initial_payment_payload("D-INIT-PARTIAL", amount),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

        payment = Payment.objects.get(driver_id=response.data["id"])
        self.assertEqual(payment.amount, amount)
        self.assertEqual(
            payment.allocations.get().target_period_start, date(2026, 11, 9)
        )
        coverage_response = self.client.get(
            f"/api/drivers/{response.data['id']}/period-coverage/"
            "?as_of=2026-11-15"
        )
        period = next(
            item
            for item in coverage_response.data["periods"]
            if item["start"] == "2026-11-09"
        )
        self.assertEqual(period["paid"], f"{amount:.2f}")
        self.assertEqual(period["remaining"], "1.00")
        self.assertEqual(period["status"], "partial")

    def test_initial_payment_requires_start_but_not_end(self):
        payload = self._initial_payment_payload(
            "D-INIT-NO-START", fee_for_period(date(2026, 11, 9))
        )
        payload.pop("initial_payment_period_start")

        response = self.client.post("/api/drivers/", payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data["initial_payment_period_start"][0],
            "شروع دوره پرداخت اولیه الزامی است.",
        )
        self.assertNotIn("initial_payment_period_end", response.data)
        self.assertFalse(Driver.objects.filter(driver_code="D-INIT-NO-START").exists())

    def test_retried_driver_creation_does_not_duplicate_initial_payment(self):
        payload = self._initial_payment_payload(
            "D-INIT-RETRY", fee_for_period(date(2026, 11, 9))
        )
        first_response = self.client.post(
            "/api/drivers/", payload, format="json"
        )
        self.assertEqual(first_response.status_code, status.HTTP_201_CREATED)

        retry_response = self.client.post(
            "/api/drivers/", payload, format="json"
        )
        self.assertEqual(retry_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Payment.objects.filter(idempotency_key=payload[
            "initial_payment_idempotency_key"
        ]).count(), 1)

    def test_initial_payment_failure_rolls_back_driver_and_payment(self):
        fee = fee_for_period(date(2026, 11, 9))
        driver_code = "D-INIT-ROLLBACK"
        idempotency_key = f"initial-{driver_code}"
        create_allocation = PaymentAllocation.objects.create

        def fail_after_allocation_create(**kwargs):
            allocation = create_allocation(**kwargs)
            self.assertTrue(
                Payment.objects.filter(idempotency_key=idempotency_key).exists()
            )
            self.assertTrue(Driver.objects.filter(driver_code=driver_code).exists())
            self.assertTrue(
                DriverFeeHistory.objects.filter(
                    driver__driver_code=driver_code
                ).exists()
            )
            self.assertTrue(
                PaymentAllocation.objects.filter(pk=allocation.pk).exists()
            )
            raise services.FinancialError(
                "شکست شبیه‌سازی‌شده در تخصیص پرداخت.",
                "initial_payment_allocation_failed",
            )

        with patch.object(
            PaymentAllocation.objects,
            "create",
            side_effect=fail_after_allocation_create,
        ) as create_mock:
            response = self.client.post(
                "/api/drivers/",
                self._initial_payment_payload(driver_code, fee),
                format="json",
            )

        create_mock.assert_called_once()
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data["code"], "initial_payment_allocation_failed"
        )
        self.assertFalse(Driver.objects.filter(driver_code=driver_code).exists())
        self.assertFalse(
            Payment.objects.filter(idempotency_key=idempotency_key).exists()
        )
        self.assertFalse(
            PaymentAllocation.objects.filter(
                payment__idempotency_key=idempotency_key
            ).exists()
        )
        self.assertFalse(
            DriverFeeHistory.objects.filter(driver__driver_code=driver_code).exists()
        )

    def test_guest_can_read_drivers_but_cannot_write_or_check_uniqueness(self):
        driver = Driver.objects.create(**driver_payload())
        guest = get_user_model().objects.create_user(
            username="driver-guest", password="pass123"
        )
        self.client.force_authenticate(user=guest)

        self.assertEqual(
            self.client.get(f"/api/drivers/{driver.pk}/").status_code,
            status.HTTP_200_OK,
        )
        self.assertEqual(
            self.client.get("/api/drivers/check-unique/").status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.assertEqual(
            self.client.post(
                "/api/drivers/", driver_payload(driver_code="D-GUEST"), format="json"
            ).status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.assertEqual(
            self.client.patch(
                f"/api/drivers/{driver.pk}/",
                {"full_name": "Guest edit"},
                format="json",
            ).status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.assertEqual(
            self.client.post(
                f"/api/drivers/{driver.pk}/status/",
                {"status": False},
                format="json",
            ).status_code,
            status.HTTP_403_FORBIDDEN,
        )
        driver.refresh_from_db()
        self.assertEqual(driver.full_name, "احمد علی")
        self.assertTrue(driver.status)

    def test_non_manager_cannot_void_payment(self):
        """Non-manager authenticated user cannot void a payment."""
        non_manager = get_user_model().objects.create_user(
            username="clerk2", password="pass123"
        )
        self.client.force_authenticate(user=non_manager)
        driver = Driver.objects.create(
            driver_code='D-E2E02', full_name='رانندهٔ تست دو', father_name='پدر تستی',
            phone='0700000002', tazkira_number='T123457', plate_number='پ 12346',
            address='هلمت، افغانستان', registration_date=date(2026,11,9),
            fee_start_date=date(2026,11,9), status=True,
            period_calendar=Driver.PERIOD_CALENDAR_GREGORIAN,
        )
        payment = services.receive_payment(
            driver=driver,
            amount=D("600"),
            payment_date=date(2026, 2, 1),
            user=self.user,
            target_period=(date(2026, 11, 9), date(2027, 2, 8)),
        )
        response = self.client.post(
            f"/api/payments/{payment.pk}/void/",
            {"reason": "test"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_non_manager_cannot_consume_credit(self):
        """Non-manager authenticated user cannot consume credit."""
        non_manager = get_user_model().objects.create_user(
            username="clerk3", password="pass123"
        )
        self.client.force_authenticate(user=non_manager)
        driver = Driver.objects.create(
            driver_code='D-E2E03', full_name='رانندهٔ تست سه', father_name='پدر تستی',
            phone='0700000003', tazkira_number='T123458', plate_number='پ 12347',
            address='هلمت، افغانستان', registration_date=date(2026,11,9),
            fee_start_date=date(2026,11,9), status=True
        )
        payment = Payment.objects.create(
            driver=driver,
            amount=D("800"),
            payment_date=date(2026, 2, 1),
            effective_date=date(2026, 2, 1),
            created_by=self.user,
        )
        credit_alloc = PaymentAllocation.objects.create(
            payment=payment,
            allocation_type=AllocationType.CREDIT,
            allocated_amount=D("800"),
            effective_date=date(2026, 2, 1),
            allocated_by=self.user,
        )
        response = self.client.post(
            "/api/credits/consume/",
            {
                "source_allocation_id": credit_alloc.pk,
                "amount": "100",
                "target_period_start": "2026-11-09",
                "target_period_end": "2027-02-06",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_non_manager_cannot_create_transfer(self):
        """Non-manager authenticated user cannot create a transfer."""
        non_manager = get_user_model().objects.create_user(
            username="clerk4", password="pass123"
        )
        self.client.force_authenticate(user=non_manager)
        response = self.client.post(
            "/api/adjustments/",
            {
                "driver_id": driver.id if (driver := Driver.objects.first()) else 1,
                "adjustment_type": "transfer",
                "amount": "50",
                "source_period_start": "2026-01-01",
                "source_period_end": "2026-03-31",
                "destination_period_start": "2026-04-01",
                "destination_period_end": "2026-06-30",
                "reason": "test transfer",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_non_manager_cannot_change_fee_schedule(self):
        """Non-manager authenticated user cannot change fee schedule."""
        non_manager = get_user_model().objects.create_user(
            username="clerk5", password="pass123"
        )
        self.client.force_authenticate(user=non_manager)
        response = self.client.post(
            "/api/fee-schedule/",
            {
                "amount": "700",
                "effective_from": "2027-01-01",
                "reason": "test",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_non_manager_cannot_change_fee_start_date(self):
        """Non-manager authenticated user cannot change fee_start_date."""
        non_manager = get_user_model().objects.create_user(
            username="clerk6", password="pass123"
        )
        self.client.force_authenticate(user=non_manager)
        driver = Driver.objects.create(**driver_payload())
        response = self.client.post(
            f"/api/drivers/{driver.pk}/fee-start-date/",
            {
                "requested_fee_start_date": "2027-01-01",
                "reason": "test",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_fee_start_date_readonly_on_normal_update(self):
        """fee_start_date cannot be changed via the normal PATCH /api/drivers/{id}/ endpoint.

        Changes to fee_start_date must go through the dedicated
        POST /api/drivers/{id}/fee-start-date/ endpoint (W10).
        """
        driver = Driver.objects.create(**driver_payload())
        original = driver.fee_start_date
        self.client.force_authenticate(user=self.user)
        response = self.client.patch(
            f"/api/drivers/{driver.pk}/",
            {"fee_start_date": "2027-06-01"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        driver.refresh_from_db()
        self.assertEqual(driver.fee_start_date, original)

    # ------------------------------------------------------------------
    # Creation and manual driver code
    # ------------------------------------------------------------------
    def test_create_driver_with_manual_code(self):
        response = self.client.post("/api/drivers/", driver_payload(), format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["driver_code"], "D-10001")
        self.assertEqual(Driver.objects.count(), 1)
        driver = Driver.objects.get()
        self.assertEqual(driver.driver_code, "D-10001")
        self.assertEqual(str(driver.registration_date), "2026-01-01")

    def test_driver_registration_requires_father_name_phone_and_tazkira(self):
        for field in ("father_name", "phone", "tazkira_number"):
            invalid_payloads = []
            missing = driver_payload()
            missing.pop(field)
            invalid_payloads.append(missing)
            invalid_payloads.extend(
                driver_payload(**{field: value})
                for value in ("", "   ", None)
            )

            for payload in invalid_payloads:
                with self.subTest(field=field, payload=payload):
                    response = self.client.post(
                        "/api/drivers/", payload, format="json"
                    )
                    self.assertEqual(
                        response.status_code, status.HTTP_400_BAD_REQUEST
                    )
                    self.assertIn(field, response.data)

        self.assertEqual(Driver.objects.count(), 0)

    def test_partial_update_allows_legacy_driver_with_missing_details(self):
        driver = Driver.objects.create(
            **driver_payload(father_name=None, phone=None, tazkira_number=None)
        )

        response = self.client.patch(
            f"/api/drivers/{driver.pk}/",
            {"address": "آدرس به‌روز شده"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        driver.refresh_from_db()
        self.assertEqual(driver.address, "آدرس به‌روز شده")
        self.assertIsNone(driver.father_name)
        self.assertIsNone(driver.phone)
        self.assertIsNone(driver.tazkira_number)

    def test_driver_code_is_required_and_never_generated(self):
        payload = driver_payload()
        payload.pop("driver_code")
        response = self.client.post("/api/drivers/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("driver_code", response.data)
        self.assertEqual(Driver.objects.count(), 0)

    def test_blank_driver_code_is_rejected(self):
        response = self.client.post(
            "/api/drivers/", driver_payload(driver_code="   "), format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Driver.objects.count(), 0)

    def test_duplicate_driver_code_is_rejected_case_insensitively(self):
        Driver.objects.create(**driver_payload())
        response = self.client.post(
            "/api/drivers/",
            driver_payload(driver_code="d-10001", plate_number="KBL 99999"),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("driver_code", response.data)
        self.assertEqual(Driver.objects.count(), 1)

    def test_database_enforces_case_insensitive_code_uniqueness(self):
        Driver.objects.create(**driver_payload())
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Driver.objects.create(
                    **driver_payload(
                        driver_code="d-10001",
                        plate_number="KBL 99999",
                    )
                )

    def test_duplicate_plate_is_rejected_after_normalization(self):
        Driver.objects.create(**driver_payload())
        response = self.client.post(
            "/api/drivers/",
            driver_payload(driver_code="D-10002", plate_number="  kbl   12345 "),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("plate_number", response.data)
        self.assertEqual(Driver.objects.count(), 1)

    # ------------------------------------------------------------------
    # Update and status
    # ------------------------------------------------------------------
    def test_update_driver_keeps_code_and_updates_fields(self):
        driver = Driver.objects.create(**driver_payload())
        response = self.client.patch(
            f"/api/drivers/{driver.pk}/",
            {"full_name": "احمد علی کریمی", "phone": "0799888777"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        driver.refresh_from_db()
        self.assertEqual(driver.driver_code, "D-10001")
        self.assertEqual(driver.full_name, "احمد علی کریمی")
        self.assertEqual(driver.phone, "0799888777")

    def test_driver_code_can_be_changed_explicitly(self):
        driver = Driver.objects.create(**driver_payload())
        response = self.client.patch(
            f"/api/drivers/{driver.pk}/",
            {"driver_code": "D-10009"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        driver.refresh_from_db()
        self.assertEqual(driver.driver_code, "D-10009")

    def test_driver_cannot_be_deleted(self):
        driver = Driver.objects.create(**driver_payload())
        response = self.client.delete(f"/api/drivers/{driver.pk}/")
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertTrue(Driver.objects.filter(pk=driver.pk).exists())

    def test_archiving_removes_driver_from_active_list_search_and_unique_check(self):
        driver = Driver.objects.create(**driver_payload())

        response = self.client.post(f"/api/drivers/{driver.pk}/archive/")

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        driver.refresh_from_db()
        self.assertTrue(driver.is_deleted)
        self.assertIsNotNone(driver.deleted_at)
        self.assertEqual(self.client.get("/api/drivers/").data["count"], 0)
        self.assertEqual(
            self.client.get("/api/drivers/?search=D-10001").data["count"], 0
        )
        self.assertEqual(
            self.client.get(
                "/api/drivers/check-unique/?driver_code=D-10001&plate_number=KBL%2012345"
            ).data["driver_code_taken"],
            False,
        )
        self.assertTrue(
            self.client.get(
                "/api/drivers/check-unique/?driver_code=D-10001&plate_number=KBL%2012345"
            ).data["plate_number_taken"]
        )
        archived = self.client.get("/api/drivers/archived/")
        self.assertEqual(archived.status_code, status.HTTP_200_OK)
        self.assertEqual([item["id"] for item in archived.data["results"]], [driver.pk])
        self.assertEqual(
            self.client.get(f"/api/drivers/{driver.pk}/").status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_archived_driver_code_can_be_reused_without_moving_history_or_files(self):
        driver = Driver.objects.create(**driver_payload())
        driver.photo.save("old.png", make_image(), save=True)
        photo_path = Path(self._media_dir) / driver.photo.name
        payment = Payment.objects.create(
            driver=driver,
            amount=D("600"),
            payment_date=date(2026, 11, 10),
            effective_date=date(2026, 11, 10),
            created_by=self.user,
        )
        allocation = PaymentAllocation.objects.create(
            payment=payment,
            allocation_type=AllocationType.FEE_PERIOD,
            target_period_start=date(2026, 11, 9),
            target_period_end=date(2027, 2, 8),
            allocated_amount=D("600"),
            effective_date=date(2026, 11, 10),
            allocated_by=self.user,
        )
        refund = PaymentRefund.objects.create(
            payment=payment,
            amount=D("100"),
            refund_date=date(2026, 11, 11),
            effective_date=date(2026, 11, 11),
            reason="آزمایش آرشیو",
            refunded_by=self.user,
        )
        document = Document.objects.create(
            driver=driver,
            document_name="تذکره",
            file=SimpleUploadedFile(
                "identity.pdf",
                b"%PDF-1.4\n%%EOF",
                content_type="application/pdf",
            ),
        )
        document_path = Path(self._media_dir) / document.file.name
        old_history = DriverFeeHistory.objects.create(
            driver=driver,
            old_fee_start_date=None,
            requested_fee_start_date=driver.fee_start_date,
            effective_fee_start_date=driver.fee_start_date,
            reason="سابقهٔ پیش از آرشیف",
            changed_by=self.user,
        )
        history_count = DriverFeeHistory.objects.filter(driver=driver).count()

        archive_response = self.client.post(f"/api/drivers/{driver.pk}/archive/")
        self.assertEqual(
            archive_response.status_code, status.HTTP_200_OK, archive_response.data
        )
        create_response = self.client.post(
            "/api/drivers/",
            driver_payload(driver_code=driver.driver_code, plate_number="NEW 12345"),
            format="json",
        )
        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
        replacement = Driver.objects.get(pk=create_response.data["id"])

        self.assertNotEqual(replacement.pk, driver.pk)
        self.assertEqual(driver.payments.count(), 1)
        self.assertEqual(payment.allocations.count(), 1)
        self.assertEqual(payment.refunds.count(), 1)
        self.assertEqual(payment.allocations.get().pk, allocation.pk)
        self.assertEqual(payment.refunds.get().pk, refund.pk)
        self.assertEqual(driver.documents.count(), 1)
        self.assertEqual(driver.fee_history.count(), history_count)
        self.assertFalse(replacement.payments.exists())
        self.assertFalse(replacement.documents.exists())
        self.assertEqual(replacement.fee_history.count(), 1)
        self.assertEqual(driver.fee_history.get().pk, old_history.pk)
        self.assertNotEqual(replacement.fee_history.get().pk, old_history.pk)
        self.assertTrue(photo_path.exists())
        self.assertTrue(document_path.exists())

    def test_restore_succeeds_when_serial_is_available(self):
        driver = Driver.objects.create(**driver_payload())
        self.client.post(f"/api/drivers/{driver.pk}/archive/")

        response = self.client.post(f"/api/drivers/{driver.pk}/restore/")

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        driver.refresh_from_db()
        self.assertFalse(driver.is_deleted)
        self.assertIsNone(driver.deleted_at)
        self.assertEqual(
            self.client.get("/api/drivers/?search=D-10001").data["count"], 1
        )

    def test_admin_can_archive_and_restore_driver(self):
        admin = get_user_model().objects.create_user(
            username="archive-admin",
            password="pass123",
            is_staff=True,
        )
        self.client.force_authenticate(user=admin)
        driver = Driver.objects.create(**driver_payload())

        archive_response = self.client.post(f"/api/drivers/{driver.pk}/archive/")
        restore_response = self.client.post(f"/api/drivers/{driver.pk}/restore/")

        self.assertEqual(archive_response.status_code, status.HTTP_200_OK)
        self.assertEqual(restore_response.status_code, status.HTTP_200_OK)

    def test_restore_fails_clearly_if_serial_was_reused(self):
        archived = Driver.objects.create(**driver_payload())
        self.client.post(f"/api/drivers/{archived.pk}/archive/")
        replacement = self.client.post(
            "/api/drivers/",
            driver_payload(driver_code=archived.driver_code, plate_number="NEW 54321"),
            format="json",
        )
        self.assertEqual(replacement.status_code, status.HTTP_201_CREATED)

        response = self.client.post(f"/api/drivers/{archived.pk}/restore/")

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertIn("شماره مسلسل", response.data["detail"])
        archived.refresh_from_db()
        self.assertTrue(archived.is_deleted)

    def test_guest_cannot_list_archive_archive_or_restore_drivers(self):
        driver = Driver.objects.create(**driver_payload())
        guest = get_user_model().objects.create_user(
            username="archive-guest", password="pass123"
        )
        self.client.force_authenticate(user=guest)

        self.assertEqual(
            self.client.get("/api/drivers/archived/").status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.assertEqual(
            self.client.post(f"/api/drivers/{driver.pk}/archive/").status_code,
            status.HTTP_403_FORBIDDEN,
        )
        driver.is_deleted = True
        driver.deleted_at = timezone.now()
        driver.save(update_fields=["is_deleted", "deleted_at", "updated_at"])
        self.assertEqual(
            self.client.post(f"/api/drivers/{driver.pk}/restore/").status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_activate_and_deactivate(self):
        driver = Driver.objects.create(**driver_payload())
        response = self.client.post(
            f"/api/drivers/{driver.pk}/status/", {"status": False}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        driver.refresh_from_db()
        self.assertFalse(driver.status)

        response = self.client.post(
            f"/api/drivers/{driver.pk}/status/", {"status": True}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        driver.refresh_from_db()
        self.assertTrue(driver.status)

    def test_invalid_status_payload_is_rejected(self):
        driver = Driver.objects.create(**driver_payload())
        response = self.client.post(
            f"/api/drivers/{driver.pk}/status/", {"status": "no"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # ------------------------------------------------------------------
    # Search, filter, pagination, stats
    # ------------------------------------------------------------------
    def _create_three_drivers(self):
        Driver.objects.create(**driver_payload())
        Driver.objects.create(
            **driver_payload(
                driver_code="D-10002",
                full_name="محمد کریمی",
                plate_number="HER 77777",
                phone="0788111222",
                status=False,
            )
        )
        Driver.objects.create(
            **driver_payload(
                driver_code="D-10003",
                full_name="علی رضایی",
                plate_number="BAL 33333",
                phone="0777333444",
            )
        )

    def test_search_by_name_plate_and_code(self):
        self._create_three_drivers()

        by_name = self.client.get("/api/drivers/?search=کریمی")
        self.assertEqual(by_name.status_code, 200)
        self.assertEqual(by_name.data["count"], 1)
        self.assertEqual(by_name.data["results"][0]["driver_code"], "D-10002")

        by_plate = self.client.get("/api/drivers/?search=BAL 33333")
        self.assertEqual(by_plate.data["count"], 1)
        self.assertEqual(by_plate.data["results"][0]["full_name"], "علی رضایی")

        by_code = self.client.get("/api/drivers/?search=D-10003")
        self.assertEqual(by_code.data["count"], 1)
        self.assertEqual(by_code.data["results"][0]["full_name"], "علی رضایی")

    def test_specific_search_parameters(self):
        self._create_three_drivers()
        self.assertEqual(
            self.client.get("/api/drivers/?name=رضایی").data["count"], 1
        )
        self.assertEqual(
            self.client.get("/api/drivers/?plate=HER").data["count"], 1
        )
        self.assertEqual(
            self.client.get("/api/drivers/?code=D-10002").data["count"], 1
        )

    def test_filter_active_and_inactive(self):
        self._create_three_drivers()
        active = self.client.get("/api/drivers/?status=active")
        inactive = self.client.get("/api/drivers/?status=inactive")
        self.assertEqual(active.data["count"], 2)
        self.assertEqual(inactive.data["count"], 1)

    def test_pagination(self):
        self._create_three_drivers()
        response = self.client.get("/api/drivers/?page_size=2&page=2")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 3)
        self.assertEqual(len(response.data["results"]), 1)

    def test_stats(self):
        self._create_three_drivers()
        response = self.client.get("/api/drivers/stats/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["total"], 3)
        self.assertEqual(response.data["active"], 2)
        self.assertEqual(response.data["inactive"], 1)
        self.assertEqual(len(response.data["recent"]), 3)

    def test_unique_check_endpoint(self):
        Driver.objects.create(**driver_payload())
        response = self.client.get(
            "/api/drivers/check-unique/?driver_code=d-10001&plate_number=ABC 111"
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["driver_code_taken"])
        self.assertFalse(response.data["plate_number_taken"])

    def test_idempotency_same_key_returns_same_payment(self):
        """Same idempotency key returns the same payment."""
        driver = Driver.objects.create(
            driver_code='D-E2E08', full_name='رانندهٔ تست هشت', father_name='پدر تستی',
            phone='0700000008', tazkira_number='T123459', plate_number='پ 12351',
            address='بمیان، افغانستان', registration_date=date(2026,11,9),
            fee_start_date=date(2026,11,9), status=True
        )
        payment_data = {
            "driver_id": driver.id,
            "amount": "300",
            "payment_date": "2026-11-09",
            "target_period_start": "2026-11-09",
            "target_period_end": "2027-02-06",
            "idempotency_key": "unique-payment-key-1",
        }

        # First request
        response1 = self.client.post("/api/payments/", payment_data, format="json")
        self.assertEqual(response1.status_code, status.HTTP_201_CREATED)
        payment1_id = response1.data["id"]

        # Second request with same idempotency key
        response2 = self.client.post("/api/payments/", payment_data, format="json")
        self.assertEqual(response2.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response2.data["id"], payment1_id)

        # Verify only one payment exists in DB
        self.assertEqual(Payment.objects.filter(driver=driver).count(), 1)

    def test_idempotency_different_key_creates_different_payment(self):
        """Different idempotency keys create different payments."""
        driver = Driver.objects.create(
            driver_code='D-E2E09', full_name='رانندهٔ هشت', father_name='پدر تستی',
            phone='0700000009', tazkira_number='T123460', plate_number='پ 12352',
            address='بمیان، افغانستان', registration_date=date(2026,11,9),
            fee_start_date=date(2026,11,9), status=True
        )

        payment_data = {
            "driver_id": driver.id,
            "amount": "300",
            "payment_date": "2026-11-09",
            "target_period_start": "2026-11-09",
            "target_period_end": "2027-02-06",
        }

        # First payment with key 1
        response1 = self.client.post(
            "/api/payments/",
            {**payment_data, "idempotency_key": "key-1"},
            format="json",
        )
        self.assertEqual(response1.status_code, status.HTTP_201_CREATED)

        # Second payment with key 2
        response2 = self.client.post(
            "/api/payments/",
            {**payment_data, "idempotency_key": "key-2"},
            format="json",
        )
        self.assertEqual(response2.status_code, status.HTTP_201_CREATED)
        self.assertNotEqual(response1.data["id"], response2.data["id"])

        # Two payments exist
        self.assertEqual(Payment.objects.filter(driver=driver).count(), 2)

    # ------------------------------------------------------------------
    # Photo upload and private delivery
    # ------------------------------------------------------------------
    def test_photo_upload_creates_driver_folder_and_private_url(self):
        response = self.client.post(
            "/api/drivers/",
            driver_payload(photo=make_image()),
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIsNotNone(response.data["photo_url"])

        driver = Driver.objects.get()
        self.assertTrue(driver.photo.name.startswith("drivers/D-10001/photos/"))
        photo_path = Path(self._media_dir) / driver.photo.name
        self.assertTrue(photo_path.exists())

        self.client.force_authenticate(user=None)
        anonymous = self.client.get(f"/api/drivers/{driver.pk}/photo/")
        self.assertIn(anonymous.status_code, (401, 403))

        self.client.force_authenticate(user=self.user)
        authenticated = self.client.get(f"/api/drivers/{driver.pk}/photo/")
        self.assertEqual(authenticated.status_code, 200)
        self.assertEqual(authenticated["Content-Type"], "image/png")

    def test_replacing_photo_removes_old_file(self):
        driver = Driver.objects.create(**driver_payload())
        first = self.client.patch(
            f"/api/drivers/{driver.pk}/",
            {"photo": make_image("first.png", color="red")},
            format="multipart",
        )
        self.assertEqual(first.status_code, 200)
        driver.refresh_from_db()
        first_name = driver.photo.name
        first_path = Path(self._media_dir) / first_name
        self.assertTrue(first_path.exists())

        second = self.client.patch(
            f"/api/drivers/{driver.pk}/",
            {"photo": make_image("second.png", color="green")},
            format="multipart",
        )
        self.assertEqual(second.status_code, 200)
        driver.refresh_from_db()
        self.assertNotEqual(driver.photo.name, first_name)
        self.assertFalse(first_path.exists())
        self.assertTrue((Path(self._media_dir) / driver.photo.name).exists())

    def test_invalid_photo_extension_is_rejected(self):
        bad_file = SimpleUploadedFile(
            "photo.txt", b"not an image", content_type="text/plain"
        )
        response = self.client.post(
            "/api/drivers/",
            driver_payload(photo=bad_file),
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("photo", response.data)
        self.assertEqual(Driver.objects.count(), 0)

    @patch("apps.drivers.serializers.MAX_PHOTO_SIZE", 10)
    def test_oversized_photo_is_rejected(self):
        response = self.client.post(
            "/api/drivers/",
            driver_payload(photo=make_image()),
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("photo", response.data)
        self.assertEqual(Driver.objects.count(), 0)

    def test_photo_paths_are_collision_free(self):
        first = self.client.post(
            "/api/drivers/",
            driver_payload(photo=make_image("same.png")),
            format="multipart",
        )
        second = self.client.post(
            "/api/drivers/",
            driver_payload(
                driver_code="D-10002",
                plate_number="KBL 54321",
                photo=make_image("same.png"),
            ),
            format="multipart",
        )
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        names = list(Driver.objects.values_list("photo", flat=True))
        self.assertEqual(len(names), 2)
        self.assertNotEqual(names[0], names[1])

    # ------------------------------------------------------------------
    # Driver type (guaranteed vs online)
    # ------------------------------------------------------------------
    def test_create_online_driver(self):
        """Creating an online driver via API sets driver_type=online."""
        payload = driver_payload(driver_code="D-ONLINE01", plate_number="ONL 0001")
        payload["driver_type"] = "online"
        response = self.client.post("/api/drivers/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["driver_type"], "online")
        driver = Driver.objects.get(driver_code="D-ONLINE01")
        self.assertEqual(driver.driver_type, "online")
        # Online drivers should NOT have a DriverFeeHistory entry
        self.assertFalse(DriverFeeHistory.objects.filter(driver=driver).exists())

    def test_create_guaranteed_driver_defaults_to_guaranteed(self):
        """Creating a driver without driver_type defaults to guaranteed."""
        payload = driver_payload(driver_code="D-GUAR01", plate_number="GUA 0001")
        # No driver_type specified → defaults to guaranteed
        response = self.client.post("/api/drivers/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["driver_type"], "guaranteed")
        driver = Driver.objects.get(driver_code="D-GUAR01")
        self.assertEqual(driver.driver_type, "guaranteed")
        # Guaranteed drivers should have a DriverFeeHistory entry
        self.assertTrue(DriverFeeHistory.objects.filter(driver=driver).exists())

    def test_create_online_driver_with_pdf(self):
        """Online driver creation with PDF upload works."""
        payload = driver_payload(driver_code="D-ONLINE02", plate_number="ONL 0002")
        payload["driver_type"] = "online"
        # Minimal valid PDF content
        pdf_content = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\nstartxref\n0\n%%EOF\n"
        pdf_file = SimpleUploadedFile("doc.pdf", pdf_content, content_type="application/pdf")
        response = self.client.post(
            "/api/drivers/",
            {**payload, "documents": pdf_file},
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["driver_type"], "online")
        driver = Driver.objects.get(driver_code="D-ONLINE02")
        self.assertEqual(driver.driver_type, "online")
        # PDF was uploaded
        self.assertEqual(driver.documents.count(), 1)

    def test_filter_drivers_by_type(self):
        """Filtering drivers by driver_type works."""
        # Create one online and one guaranteed driver
        Driver.objects.create(
            **driver_payload(driver_code="D-ONL01", plate_number="ONL 001",
                             driver_type="online")
        )
        Driver.objects.create(
            **driver_payload(driver_code="D-GUA01", plate_number="GUA 001",
                             driver_type="guaranteed")
        )

        online = self.client.get("/api/drivers/?driver_type=online")
        self.assertEqual(online.status_code, 200)
        self.assertEqual(online.data["count"], 1)
        self.assertEqual(online.data["results"][0]["driver_type"], "online")

        guaranteed = self.client.get("/api/drivers/?driver_type=guaranteed")
        self.assertEqual(guaranteed.status_code, 200)
        self.assertEqual(guaranteed.data["count"], 1)
        self.assertEqual(guaranteed.data["results"][0]["driver_type"], "guaranteed")

    def test_driver_type_readonly_on_update(self):
        """driver_type cannot be changed via normal PATCH update."""
        driver = Driver.objects.create(**driver_payload(driver_code="D-TYPE01",
                                                         plate_number="TYP 001"))
        self.assertEqual(driver.driver_type, "guaranteed")
        response = self.client.patch(
            f"/api/drivers/{driver.pk}/",
            {"driver_type": "online"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        driver.refresh_from_db()
        self.assertEqual(driver.driver_type, "guaranteed")

    def test_existing_drivers_default_to_guaranteed(self):
        """Drivers created without driver_type default to guaranteed."""
        driver = Driver.objects.create(**driver_payload(driver_code="D-DEF01",
                                                         plate_number="DEF 001"))
        self.assertEqual(driver.driver_type, "guaranteed")

    def test_create_multiple_drivers_mixed_types(self):
        """Creating multiple drivers of different types works."""
        Driver.objects.create(
            **driver_payload(driver_code="D-ONLINE-A", plate_number="ONL-A 01",
                             driver_type="online")
        )
        Driver.objects.create(
            **driver_payload(driver_code="D-ONLINE-B", plate_number="ONL-B 02",
                             driver_type="online")
        )
        Driver.objects.create(
            **driver_payload(driver_code="D-GUAR-A", plate_number="GUA-A 01",
                             driver_type="guaranteed")
        )
        self.assertEqual(Driver.objects.filter(driver_type="online").count(), 2)
        self.assertEqual(Driver.objects.filter(driver_type="guaranteed").count(), 1)
        self.assertEqual(Driver.objects.count(), 3)

    def test_payment_created_for_online_driver(self):
        """Creating an online payment for an online driver works (financial isolation preserved)."""
        driver = Driver.objects.create(
            **driver_payload(driver_code="D-ONLINE-PAY", plate_number="ONL-PAY 01",
                             driver_type="online")
        )
        response = self.client.post(
            "/api/online-payments/",
            {
                "driver_id": driver.id,
                "amount": "500",
                "payment_date": "2026-11-09",
                "purpose": "تست پرداخت آنلاین",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        payment = OnlinePayment.objects.get(id=response.data["id"])
        self.assertEqual(payment.driver.driver_type, "online")

    def test_invalid_driver_type_is_rejected(self):
        """Invalid driver_type value is rejected."""
        payload = driver_payload(driver_code="D-BAD01", plate_number="BAD 001")
        payload["driver_type"] = "invalid_type"
        response = self.client.post("/api/drivers/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("driver_type", response.data)
        self.assertEqual(Driver.objects.filter(driver_code="D-BAD01").count(), 0)
