"""Document API tests: security, upload, deactivation, download."""

from datetime import date
from decimal import Decimal as D
from pathlib import Path

from django.contrib.auth import get_user_model
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from apps.drivers.models import Driver
from apps.payments.models import Payment
from .models import Document


class DocumentPermissionTestCase(APITestCase):
    """Test document access control: managers can upload/deactivate, non-managers cannot.

    Uses DRF's APITestCase so that ``self.client`` is an APIClient and
    ``force_authenticate`` is available.
    """

    def setUp(self):
        self.manager = get_user_model().objects.create_superuser(
            username="manager", password="pass123", is_staff=True, is_superuser=True
        )
        self.non_manager = get_user_model().objects.create_user(
            username="clerk", password="pass123", is_staff=True, is_superuser=False
        )
        self.driver = Driver.objects.create(
            driver_code="D-TEST01",
            full_name="Test Driver",
            father_name="Father",
            phone="0700000001",
            tazkira_number="T123456",
            plate_number="P 12345",
            address="Kabul, Afghanistan",
            registration_date=date(2026, 1, 1),
            fee_start_date=date(2026, 11, 1),
            status=True,
        )
        self.payment = Payment.objects.create(
            driver=self.driver,
            amount=D("600"),
            payment_date=date(2026, 11, 10),
            effective_date=date(2026, 11, 10),
            created_by=self.manager,
        )
        self.allocation = self.driver.payments.first().allocations.create(
            allocation_type="credit",
            allocated_amount=D("200"),
            # A CREDIT allocation must not carry a target period
            # (CheckConstraint alloc_target_matches_type).
            target_period_start=None,
            target_period_end=None,
            effective_date=date(2026, 11, 9),
            allocated_by=self.manager,
        )

    def test_non_manager_cannot_upload_document(self):
        """Non-manager authenticated user cannot upload a PDF document."""
        self.client.force_authenticate(user=self.non_manager)
        response = self.client.post(
            "/api/documents/upload/",
            {
                "driver_id": self.driver.id,
                "documents": [self._make_pdf("test.pdf")],
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_manager_can_upload_document(self):
        """Manager can upload a PDF document."""
        self.client.force_authenticate(user=self.manager)
        response = self.client.post(
            "/api/documents/upload/",
            {
                "driver_id": self.driver.id,
                "documents": [self._make_pdf("test.pdf")],
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["documents"][0]["document_name"], "test.pdf")

    def test_non_manager_cannot_deactivate_document(self):
        """Non-manager authenticated user cannot deactivate a document."""
        # First create a document as manager
        self.client.force_authenticate(user=self.manager)
        upload_resp = self.client.post(
            "/api/documents/upload/",
            {
                "driver_id": self.driver.id,
                "documents": [self._make_pdf("test.pdf")],
            },
            format="multipart",
        )
        self.assertEqual(upload_resp.status_code, 201)
        doc_id = upload_resp.data["documents"][0]["id"]

        # Now try to deactivate as non-manager
        self.client.force_authenticate(user=self.non_manager)
        response = self.client.post(
            f"/api/documents/{doc_id}/deactivate/",
            {},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_manager_can_deactivate_document(self):
        """Manager can deactivate a document."""
        self.client.force_authenticate(user=self.manager)
        upload_resp = self.client.post(
            "/api/documents/upload/",
            {
                "driver_id": self.driver.id,
                "documents": [self._make_pdf("test.pdf")],
            },
            format="multipart",
        )
        self.assertEqual(upload_resp.status_code, 201)
        doc_id = upload_resp.data["documents"][0]["id"]

        response = self.client.post(
            f"/api/documents/{doc_id}/deactivate/",
            {},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "inactive")

    def test_manager_can_download_document(self):
        """Manager can download a document PDF."""
        self.client.force_authenticate(user=self.manager)
        upload_resp = self.client.post(
            "/api/documents/upload/",
            {
                "driver_id": self.driver.id,
                "documents": [self._make_pdf("test.pdf")],
            },
            format="multipart",
        )
        self.assertEqual(upload_resp.status_code, 201)
        doc_id = upload_resp.data["documents"][0]["id"]

        response = self.client.get(f"/api/documents/{doc_id}/download/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")

    def tearDown(self):
        """Remove the uploaded files.

        The test database is rolled back, but the files written to MEDIA_ROOT
        are real files on disk; without this cleanup every test run would
        leave orphaned PDFs in the media store.
        """
        import shutil

        from django.conf import settings

        driver_dir = Path(settings.MEDIA_ROOT) / "drivers" / self.driver.driver_code
        if driver_dir.exists():
            shutil.rmtree(driver_dir, ignore_errors=True)

    def _make_pdf(self, name):
        """Create a minimal valid PDF file for testing."""
        content = (
            b"%PDF-1.4\n"
            b"1 0 obj\n<< /Type /Catalog >>\nendobj\n"
            b"2 0 obj\n<< /Type /Pages /Kids [] /Count 0 >>\nendobj\n"
            b"3 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
            b"4 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
            b"xref\n0 5\n0000000000 65535 f \n"
            b"0000000009 00000 n \n0000000052 00000 n \n"
            b"0000000100 00000 n \n0000000152 00000 n \n"
            b"trailer\n<< /Size 5 /Root 3 0 R >>\n"
            b"startxref\n162\n%%EOF"
        )
        return SimpleUploadedFile(name, content, content_type="application/pdf")


class DocumentValidationTests(APITestCase):
    """Validation messages of the document endpoints."""

    def setUp(self):
        self.manager = get_user_model().objects.create_superuser(
            username="doc_manager", password="pass123", is_staff=True, is_superuser=True
        )
        self.client.force_authenticate(user=self.manager)

    def test_upload_without_driver_id_returns_readable_persian_message(self):
        """The message must be Persian text (no stray non-Latin characters)."""
        response = self.client.post("/api/documents/upload/", {"documents": []})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        detail = response.data["driver_id"][0]
        self.assertIn("الزامی است", detail)
        # every character must belong to the Arabic/Persian block or be ASCII
        for char in detail:
            self.assertTrue(
                char.isascii() or 0x0600 <= ord(char) <= 0x06FF,
                f"unexpected character {char!r} (U+{ord(char):04X}) in {detail!r}",
            )

    def test_document_list_without_driver_id_returns_readable_persian_message(self):
        response = self.client.get("/api/documents/")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        detail = response.data["driver_id"][0]
        self.assertIn("الزامی است", detail)
        for char in detail:
            self.assertTrue(
                char.isascii() or 0x0600 <= ord(char) <= 0x06FF,
                f"unexpected character {char!r} (U+{ord(char):04X}) in {detail!r}",
            )