"""Document API tests: security, upload, deactivation, download."""

import shutil
import tempfile
from datetime import date
from decimal import Decimal as D
from io import BytesIO

from django.contrib.auth import get_user_model
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from PIL import Image
from rest_framework import status
from rest_framework.test import APITestCase

from apps.drivers.models import Driver
from apps.payments.models import Payment
from .models import Document


class DocumentPermissionTestCase(APITestCase):
    """Test document access control for Superuser, Admin and Guest.

    Uses DRF's APITestCase so that ``self.client`` is an APIClient and
    ``force_authenticate`` is available.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._media_dir = tempfile.mkdtemp(prefix="dm-document-tests-")
        cls._media_override = override_settings(MEDIA_ROOT=cls._media_dir)
        cls._media_override.enable()

    @classmethod
    def tearDownClass(cls):
        cls._media_override.disable()
        shutil.rmtree(cls._media_dir, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.manager = get_user_model().objects.create_superuser(
            username="manager", password="pass123", is_staff=True, is_superuser=True
        )
        self.admin = get_user_model().objects.create_user(
            username="admin", password="pass123", is_staff=True
        )
        self.guest = get_user_model().objects.create_user(
            username="guest", password="pass123"
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

    def test_guest_cannot_upload_document(self):
        """Guest cannot upload a PDF document."""
        self.client.force_authenticate(user=self.guest)
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

    def test_admin_can_upload_document(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.post(
            "/api/documents/upload/",
            {
                "driver_id": self.driver.id,
                "documents": [self._make_pdf("admin-upload.pdf")],
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, 201, response.data)

    def test_admin_can_upload_valid_image(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.post(
            "/api/documents/upload/",
            {
                "driver_id": self.driver.id,
                "documents": [self._make_image("driver.png")],
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(
            response.data["documents"][0]["content_type"], "image/png"
        )

    def test_upload_rejects_invalid_file_content(self):
        self.client.force_authenticate(user=self.admin)
        response = self.client.post(
            "/api/documents/upload/",
            {
                "driver_id": self.driver.id,
                "documents": [
                    SimpleUploadedFile(
                        "not-a-pdf.pdf",
                        b"not a PDF",
                        content_type="application/pdf",
                    )
                ],
            },
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("documents", response.data)
        self.assertEqual(Document.objects.count(), 0)

    def test_upload_rejects_file_over_10mb(self):
        self.client.force_authenticate(user=self.admin)
        oversized_pdf = SimpleUploadedFile(
            "oversized.pdf",
            b"%PDF-1.4\n" + b"x" * (10 * 1024 * 1024),
            content_type="application/pdf",
        )
        response = self.client.post(
            "/api/documents/upload/",
            {"driver_id": self.driver.id, "documents": [oversized_pdf]},
            format="multipart",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("documents", response.data)
        self.assertEqual(Document.objects.count(), 0)

    def test_guest_can_list_and_download_documents(self):
        self.client.force_authenticate(user=self.admin)
        upload_response = self.client.post(
            "/api/documents/upload/",
            {
                "driver_id": self.driver.id,
                "documents": [self._make_pdf("guest-view.pdf")],
            },
            format="multipart",
        )
        self.assertEqual(upload_response.status_code, status.HTTP_201_CREATED)
        document_id = upload_response.data["documents"][0]["id"]

        self.client.force_authenticate(user=self.guest)
        list_response = self.client.get(
            f"/api/documents/?driver_id={self.driver.id}"
        )
        self.assertEqual(list_response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(list_response.data["documents"]), 1)

        download_response = self.client.get(
            f"/api/documents/{document_id}/download/"
        )
        self.assertEqual(download_response.status_code, status.HTTP_200_OK)
        self.assertEqual(download_response["Content-Type"], "application/pdf")

    def test_anonymous_user_cannot_download_document(self):
        self.client.force_authenticate(user=self.admin)
        upload_response = self.client.post(
            "/api/documents/upload/",
            {
                "driver_id": self.driver.id,
                "documents": [self._make_pdf("private.pdf")],
            },
            format="multipart",
        )
        self.assertEqual(upload_response.status_code, status.HTTP_201_CREATED)
        document_id = upload_response.data["documents"][0]["id"]

        self.client.force_authenticate(user=None)
        response = self.client.get(f"/api/documents/{document_id}/download/")
        self.assertIn(
            response.status_code,
            (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
        )

    def test_document_list_is_scoped_to_requested_driver(self):
        self.client.force_authenticate(user=self.admin)
        upload_response = self.client.post(
            "/api/documents/upload/",
            {
                "driver_id": self.driver.id,
                "documents": [self._make_pdf("scoped.pdf")],
            },
            format="multipart",
        )
        self.assertEqual(upload_response.status_code, status.HTTP_201_CREATED)
        other_driver = Driver.objects.create(
            driver_code="D-TEST02",
            full_name="Other Driver",
            father_name="Father",
            phone="0700000002",
            tazkira_number="T123457",
            plate_number="P 12346",
            address="Kabul, Afghanistan",
            registration_date=date(2026, 1, 1),
            fee_start_date=date(2026, 11, 1),
            status=True,
        )
        response = self.client.get(
            f"/api/documents/?driver_id={other_driver.id}"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["documents"], [])

    def test_guest_cannot_deactivate_document(self):
        """Guest cannot deactivate a document."""
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

        # Now try to deactivate as Guest
        self.client.force_authenticate(user=self.guest)
        response = self.client.post(
            f"/api/documents/{doc_id}/deactivate/",
            {},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_deactivate_document(self):
        self.client.force_authenticate(user=self.manager)
        upload_resp = self.client.post(
            "/api/documents/upload/",
            {
                "driver_id": self.driver.id,
                "documents": [self._make_pdf("admin-deactivate.pdf")],
            },
            format="multipart",
        )
        self.assertEqual(upload_resp.status_code, 201)
        doc_id = upload_resp.data["documents"][0]["id"]

        self.client.force_authenticate(user=self.admin)
        response = self.client.post(
            f"/api/documents/{doc_id}/deactivate/",
            {},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["status"], "inactive")

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

    def _make_image(self, name):
        buffer = BytesIO()
        Image.new("RGB", (20, 20), "navy").save(buffer, format="PNG")
        return SimpleUploadedFile(
            name, buffer.getvalue(), content_type="image/png"
        )


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