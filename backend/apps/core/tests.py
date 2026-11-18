"""Authentication and role-based access tests."""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import Client
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from apps.core.activity import log_activity
from apps.core.models import ActivityLog, UserPasswordChangeAudit


class AuthenticationTests(APITestCase):
    def setUp(self):
        self.password = "StrongPass-2026!"
        self.user = get_user_model().objects.create_user(
            username="admin",
            password=self.password,
            first_name="مدیر",
            last_name="سیستم",
        )

    def test_csrf_endpoint_sets_cookie(self):
        client = APIClient(enforce_csrf_checks=True)
        response = client.get("/api/auth/csrf/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("csrftoken", response.cookies)

    def test_login_without_csrf_is_rejected(self):
        client = APIClient(enforce_csrf_checks=True)
        response = client.post(
            "/api/auth/login/",
            {"username": "admin", "password": self.password},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_login_me_logout_flow(self):
        client = APIClient(enforce_csrf_checks=True)
        client.get("/api/auth/csrf/")
        csrf_token = client.cookies["csrftoken"].value

        login_response = client.post(
            "/api/auth/login/",
            {"username": "admin", "password": self.password},
            format="json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        self.assertEqual(login_response.status_code, 200)
        self.assertEqual(login_response.data["username"], "admin")

        me_response = client.get("/api/auth/me/")
        self.assertEqual(me_response.status_code, 200)
        self.assertEqual(me_response.data["display_name"], "مدیر سیستم")

        # Django rotates the CSRF token on login.
        csrf_token = client.cookies["csrftoken"].value
        logout_response = client.post(
            "/api/auth/logout/", HTTP_X_CSRFTOKEN=csrf_token
        )
        self.assertEqual(logout_response.status_code, 200)

        me_after_logout = client.get("/api/auth/me/")
        self.assertEqual(me_after_logout.status_code, 401)

    def test_wrong_password_is_rejected(self):
        client = APIClient()
        response = client.post(
            "/api/auth/login/",
            {"username": "admin", "password": "wrong-password"},
            format="json",
        )
        self.assertEqual(response.status_code, 401)
        self.assertIn("detail", response.data)

    def test_inactive_user_cannot_login(self):
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        client = APIClient()
        response = client.post(
            "/api/auth/login/",
            {"username": "admin", "password": self.password},
            format="json",
        )
        self.assertEqual(response.status_code, 401)

    def test_me_requires_authentication(self):
        response = APIClient().get("/api/auth/me/")
        self.assertEqual(response.status_code, 401)

    def test_public_registration_does_not_exist(self):
        response = APIClient().post(
            "/api/auth/register/",
            {"username": "someone", "password": "whatever"},
            format="json",
        )
        self.assertEqual(response.status_code, 404)


class UserManagementTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.superuser = User.objects.create_superuser(
            username="root", password="StrongPass-2026!"
        )
        self.admin = User.objects.create_user(
            username="staff-admin", password="StrongPass-2026!", is_staff=True
        )
        self.guest = User.objects.create_user(
            username="guest", password="StrongPass-2026!"
        )
        self.client.force_authenticate(user=self.superuser)

    def test_superuser_can_create_edit_change_role_and_deactivate_users(self):
        response = self.client.post(
            "/api/users/",
            {
                "username": "managed",
                "full_name": "کاربر آزمایشی",
                "password": "StrongManagedPass-2026!",
                "password_confirmation": "StrongManagedPass-2026!",
                "role": "guest",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        managed = get_user_model().objects.get(username="managed")
        self.assertFalse(managed.is_superuser)
        self.assertFalse(managed.is_staff)

        response = self.client.patch(
            f"/api/users/{managed.pk}/",
            {"full_name": "کاربر ویرایش‌شده", "role": "admin"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        managed.refresh_from_db()
        self.assertEqual(managed.get_full_name(), "کاربر ویرایش‌شده")
        self.assertTrue(managed.is_staff)
        self.assertFalse(managed.is_superuser)

        response = self.client.patch(
            f"/api/users/{managed.pk}/", {"is_active": False}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        managed.refresh_from_db()
        self.assertFalse(managed.is_active)

    def test_create_api_rejects_privilege_flags(self):
        response = self.client.post(
            "/api/users/",
            {
                "username": "privileged",
                "full_name": "کاربر آزمایشی",
                "password": "StrongManagedPass-2026!",
                "password_confirmation": "StrongManagedPass-2026!",
                "role": "guest",
                "is_superuser": True,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(get_user_model().objects.filter(username="privileged").exists())

    def test_admin_cannot_access_user_management_or_change_own_role(self):
        self.client.force_authenticate(user=self.admin)
        self.assertEqual(
            self.client.get("/api/users/").status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.assertEqual(
            self.client.post(
                "/api/users/",
                {
                    "username": "forbidden",
                    "full_name": "کاربر ممنوع",
                    "password": "StrongManagedPass-2026!",
                    "password_confirmation": "StrongManagedPass-2026!",
                    "role": "guest",
                },
                format="json",
            ).status_code,
            status.HTTP_403_FORBIDDEN,
        )
        response = self.client.patch(
            f"/api/users/{self.admin.pk}/",
            {"role": "superuser", "is_superuser": True},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_staff)
        self.assertFalse(self.admin.is_superuser)
        self.assertEqual(
            self.client.patch(
                f"/api/users/{self.guest.pk}/",
                {"role": "admin"},
                format="json",
            ).status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.guest.refresh_from_db()
        self.assertFalse(self.guest.is_staff)
        self.assertFalse(get_user_model().objects.filter(username="forbidden").exists())

    def test_guest_cannot_access_user_management(self):
        self.client.force_authenticate(user=self.guest)
        self.assertEqual(
            self.client.get("/api/users/").status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.assertEqual(
            self.client.post("/api/users/", {}, format="json").status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.assertEqual(
            self.client.patch(
                f"/api/users/{self.guest.pk}/", {"role": "admin"}, format="json"
            ).status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_superuser_privileges_cannot_be_changed_through_user_api(self):
        response = self.client.patch(
            f"/api/users/{self.guest.pk}/",
            {"is_superuser": True},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        response = self.client.patch(
            f"/api/users/{self.guest.pk}/",
            {"role": "superuser"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.guest.refresh_from_db()
        self.assertFalse(self.guest.is_superuser)
        self.assertFalse(self.guest.is_staff)

    def test_superuser_account_cannot_be_edited_by_user_management_api(self):
        response = self.client.patch(
            f"/api/users/{self.superuser.pk}/",
            {"is_active": False},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.superuser.refresh_from_db()
        self.assertTrue(self.superuser.is_active)

    def test_superuser_can_reset_password_and_audit_without_exposing_secret(self):
        new_password = "NewManagedUserPass-2026!"
        response = self.client.post(
            f"/api/users/{self.guest.pk}/password/",
            {
                "new_password": new_password,
                "password_confirmation": new_password,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertNotIn(new_password, str(response.data))
        self.assertEqual(
            set(response.data),
            {"detail"},
        )
        self.guest.refresh_from_db()
        self.assertTrue(self.guest.check_password(new_password))
        self.assertNotEqual(self.guest.password, new_password)
        audit = UserPasswordChangeAudit.objects.get(target=self.guest)
        self.assertEqual(audit.actor, self.superuser)
        self.assertEqual(audit.actor_username, self.superuser.username)
        self.assertEqual(audit.target_username, self.guest.username)
        self.assertIsNotNone(audit.changed_at)
        self.assertNotIn("password", [field.name for field in audit._meta.fields])

    def test_password_reset_invalidates_old_sessions_and_accepts_new_password(self):
        old_password = "StrongPass-2026!"
        new_password = "NewManagedUserPass-2026!"
        target_client = Client()
        self.assertTrue(target_client.login(username=self.guest.username, password=old_password))

        response = self.client.post(
            f"/api/users/{self.guest.pk}/password/",
            {
                "new_password": new_password,
                "password_confirmation": new_password,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(target_client.get("/api/auth/me/").status_code, 401)
        self.assertEqual(
            target_client.post(
                "/api/auth/login/",
                {"username": self.guest.username, "password": old_password},
                format="json",
            ).status_code,
            401,
        )
        self.assertEqual(
            target_client.post(
                "/api/auth/login/",
                {"username": self.guest.username, "password": new_password},
                format="json",
            ).status_code,
            200,
        )

    def test_superuser_can_reset_own_password_without_losing_current_session(self):
        new_password = "NewRootManagedPass-2026!"
        root_client = Client()
        root_client.force_login(self.superuser)

        response = root_client.post(
            f"/api/users/{self.superuser.pk}/password/",
            {
                "new_password": new_password,
                "password_confirmation": new_password,
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(root_client.get("/api/auth/me/").status_code, status.HTTP_200_OK)
        self.superuser.refresh_from_db()
        self.assertTrue(self.superuser.check_password(new_password))

    def test_admin_and_guest_cannot_reset_password(self):
        payload = {
            "new_password": "NewManagedUserPass-2026!",
            "password_confirmation": "NewManagedUserPass-2026!",
        }
        for actor, expected_status in (
            (self.admin, status.HTTP_403_FORBIDDEN),
            (self.guest, status.HTTP_403_FORBIDDEN),
        ):
            with self.subTest(actor=actor.username):
                self.client.force_authenticate(user=actor)
                response = self.client.post(
                    f"/api/users/{self.guest.pk}/password/",
                    payload,
                    format="json",
                )
                self.assertEqual(response.status_code, expected_status)
        self.guest.refresh_from_db()
        self.assertTrue(self.guest.check_password("StrongPass-2026!"))

    def test_password_reset_rejects_mismatch_and_weak_password(self):
        url = f"/api/users/{self.guest.pk}/password/"
        mismatch = self.client.post(
            url,
            {
                "new_password": "NewManagedUserPass-2026!",
                "password_confirmation": "DifferentManagedPass-2026!",
            },
            format="json",
        )
        weak = self.client.post(
            url,
            {"new_password": "123", "password_confirmation": "123"},
            format="json",
        )
        self.assertEqual(mismatch.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(weak.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(UserPasswordChangeAudit.objects.exists())


class DjangoAdminAccessTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.superuser = User.objects.create_superuser(
            username="admin-root", password="StrongPass-2026!"
        )
        self.admin = User.objects.create_user(
            username="admin-staff", password="StrongPass-2026!", is_staff=True
        )
        self.guest = User.objects.create_user(
            username="admin-guest", password="StrongPass-2026!"
        )

    def test_superuser_can_use_django_admin_user_management(self):
        client = Client()
        client.force_login(self.superuser)
        response = client.get("/admin/auth/user/")
        self.assertEqual(response.status_code, 200)

    def test_admin_and_guest_cannot_use_django_admin(self):
        for user in (self.admin, self.guest):
            with self.subTest(username=user.username):
                client = Client()
                client.force_login(user)
                response = client.get("/admin/auth/user/")
                self.assertNotEqual(response.status_code, 200)


class ActivityLogAccessTests(APITestCase):
    """The audit trail is Superuser-only read, append-only and never writable."""

    def setUp(self):
        User = get_user_model()
        self.superuser = User.objects.create_superuser(
            username="audit-root", password="StrongPass-2026!"
        )
        self.admin = User.objects.create_user(
            username="audit-admin", password="StrongPass-2026!", is_staff=True
        )
        self.guest = User.objects.create_user(
            username="audit-guest", password="StrongPass-2026!"
        )
        self.entry = log_activity(
            actor=self.guest,
            action="driver_create",
            module=ActivityLog.Module.DRIVERS,
            description="ایجاد راننده آزمایشی.",
            target_type="driver",
            target_id=1,
            target_label="D1 — راننده آزمایشی",
        )

    def test_superuser_can_list_read_and_get_filter_options(self):
        self.client.force_authenticate(user=self.superuser)
        listing = self.client.get("/api/activity-logs/")
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.data["count"], 1)
        self.assertEqual(listing.data["results"][0]["action"], "driver_create")
        self.assertEqual(listing.data["results"][0]["actor_username"], "audit-guest")

        detail = self.client.get(f"/api/activity-logs/{self.entry.pk}/")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.data["target_label"], "D1 — راننده آزمایشی")
        self.assertIn("before_data", detail.data)

        filters = self.client.get("/api/activity-logs/filters/")
        self.assertEqual(filters.status_code, 200)
        self.assertIn("drivers", [module["value"] for module in filters.data["modules"]])
        self.assertIn("audit-guest", filters.data["actors"])

    def test_admin_and_guest_cannot_access_activity_logs(self):
        for actor in (self.admin, self.guest):
            with self.subTest(actor=actor.username):
                self.client.force_authenticate(user=actor)
                self.assertEqual(
                    self.client.get("/api/activity-logs/").status_code,
                    status.HTTP_403_FORBIDDEN,
                )
                self.assertEqual(
                    self.client.get(f"/api/activity-logs/{self.entry.pk}/").status_code,
                    status.HTTP_403_FORBIDDEN,
                )
                self.assertEqual(
                    self.client.get("/api/activity-logs/filters/").status_code,
                    status.HTTP_403_FORBIDDEN,
                )

    def test_anonymous_cannot_access_activity_logs(self):
        response = APIClient().get("/api/activity-logs/")
        # SessionAuthentication exposes no ``WWW-Authenticate`` header, so DRF
        # answers anonymous callers with 403; either way access is refused.
        self.assertIn(response.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))

    def test_non_superusers_cannot_write_activity_logs(self):
        for actor in (self.admin, self.guest):
            with self.subTest(actor=actor.username):
                self.client.force_authenticate(user=actor)
                self.assertEqual(
                    self.client.post("/api/activity-logs/", {}, format="json").status_code,
                    status.HTTP_403_FORBIDDEN,
                )
                self.assertEqual(
                    self.client.delete(
                        f"/api/activity-logs/{self.entry.pk}/"
                    ).status_code,
                    status.HTTP_403_FORBIDDEN,
                )
        self.assertTrue(ActivityLog.objects.filter(pk=self.entry.pk).exists())

    def test_activity_log_endpoints_expose_no_write_verbs(self):
        self.client.force_authenticate(user=self.superuser)
        self.assertEqual(
            self.client.post("/api/activity-logs/", {}, format="json").status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )
        self.assertEqual(
            self.client.put(
                f"/api/activity-logs/{self.entry.pk}/", {}, format="json"
            ).status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )
        self.assertEqual(
            self.client.patch(
                f"/api/activity-logs/{self.entry.pk}/", {}, format="json"
            ).status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )
        self.assertEqual(
            self.client.delete(
                f"/api/activity-logs/{self.entry.pk}/"
            ).status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )
        self.assertEqual(ActivityLog.objects.count(), 1)

    def test_activity_log_rows_are_append_only(self):
        with self.assertRaises(PermissionError):
            self.entry.description = "تلاش برای ویرایش"
            self.entry.save()
        with self.assertRaises(PermissionError):
            self.entry.delete()
        self.assertTrue(ActivityLog.objects.filter(pk=self.entry.pk).exists())

    def test_username_snapshot_survives_user_deletion(self):
        self.guest.delete()
        self.entry.refresh_from_db()
        self.assertIsNone(self.entry.actor)
        self.assertEqual(self.entry.actor_username, "audit-guest")

    def test_sensitive_values_are_redacted_from_payloads(self):
        secret = "SuperSecret-2026!"
        entry = log_activity(
            actor=self.superuser,
            action="user_password_set",
            module=ActivityLog.Module.USERS,
            after_data={
                "username": "someone",
                "password": secret,
                "api_token": "tok_123",
                "nested": {"session_key": "abc", "amount": 10},
            },
            metadata={"password_changed": True},
        )
        entry.refresh_from_db()
        self.assertEqual(entry.after_data["password"], "***")
        self.assertEqual(entry.after_data["api_token"], "***")
        self.assertEqual(entry.after_data["nested"]["session_key"], "***")
        self.assertEqual(entry.after_data["nested"]["amount"], 10)
        self.assertEqual(entry.after_data["username"], "someone")
        self.assertNotIn(secret, str(entry.after_data))

    def test_filters_search_and_date_range(self):
        log_activity(
            actor=self.superuser,
            action="payment_receive",
            module=ActivityLog.Module.PAYMENTS,
            target_type="payment",
            target_id=42,
            target_label="D9",
        )
        log_activity(
            actor=self.superuser,
            action="payment_void",
            module=ActivityLog.Module.PAYMENTS,
            status=ActivityLog.Status.FAILURE,
        )
        self.client.force_authenticate(user=self.superuser)

        by_module = self.client.get("/api/activity-logs/?module=payments")
        self.assertEqual(by_module.data["count"], 2)

        by_actor = self.client.get("/api/activity-logs/?actor=audit-root")
        self.assertEqual(by_actor.data["count"], 2)

        by_action = self.client.get("/api/activity-logs/?action=payment_receive")
        self.assertEqual(by_action.data["count"], 1)

        by_status = self.client.get("/api/activity-logs/?status=failure")
        self.assertEqual(by_status.data["count"], 1)

        by_search = self.client.get("/api/activity-logs/?search=D1")
        self.assertEqual(by_search.data["count"], 1)

        today = timezone.localdate()
        tomorrow = today + timedelta(days=1)
        in_range = self.client.get(
            f"/api/activity-logs/?date_from={today.isoformat()}&date_to={today.isoformat()}"
        )
        self.assertEqual(in_range.data["count"], 3)
        in_future = self.client.get(
            f"/api/activity-logs/?date_from={tomorrow.isoformat()}"
        )
        self.assertEqual(in_future.data["count"], 0)

    def test_pagination_splits_large_result_sets(self):
        for index in range(12):
            log_activity(
                actor=self.superuser,
                action="login",
                module=ActivityLog.Module.AUTH,
                target_type="user",
                target_id=index,
            )
        self.client.force_authenticate(user=self.superuser)
        response = self.client.get("/api/activity-logs/?page_size=10")
        self.assertEqual(response.data["count"], 13)
        self.assertEqual(len(response.data["results"]), 10)
        self.assertIsNotNone(response.data["next"])

        second_page = self.client.get("/api/activity-logs/?page=2&page_size=10")
        self.assertEqual(len(second_page.data["results"]), 3)
        self.assertIsNone(second_page.data["next"])


class ActivityLogFromOperationsTests(APITestCase):
    """The trail is written from real backend operations, not the frontend."""

    def setUp(self):
        User = get_user_model()
        self.superuser = User.objects.create_superuser(
            username="ops-root", password="StrongPass-2026!"
        )
        self.guest = User.objects.create_user(
            username="ops-guest", password="StrongPass-2026!"
        )

    def test_user_creation_is_logged_without_the_password(self):
        self.client.force_authenticate(user=self.superuser)
        secret = "BrandNewPass-2026!"
        response = self.client.post(
            "/api/users/",
            {
                "username": "fresh-user",
                "full_name": "کاربر تازه",
                "password": secret,
                "password_confirmation": secret,
                "role": "guest",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

        entry = ActivityLog.objects.get(action="user_create")
        self.assertEqual(entry.module, ActivityLog.Module.USERS)
        self.assertEqual(entry.status, ActivityLog.Status.SUCCESS)
        self.assertEqual(entry.actor, self.superuser)
        self.assertEqual(entry.actor_username, "ops-root")
        self.assertEqual(entry.target_type, "user")
        self.assertEqual(entry.after_data["username"], "fresh-user")
        self.assertNotIn("password", entry.after_data)
        self.assertNotIn(secret, str(entry.after_data))
        self.assertNotIn(secret, str(entry.metadata))

    def test_superuser_edit_attempt_is_logged_as_failure(self):
        self.client.force_authenticate(user=self.superuser)
        response = self.client.patch(
            f"/api/users/{self.superuser.pk}/", {"is_active": False}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        entry = ActivityLog.objects.get(action="user_edit_denied")
        self.assertEqual(entry.status, ActivityLog.Status.FAILURE)
        self.assertEqual(entry.actor_username, "ops-root")
        self.superuser.refresh_from_db()
        self.assertTrue(self.superuser.is_active)

    def test_failed_login_is_logged_as_failure(self):
        response = APIClient().post(
            "/api/auth/login/",
            {"username": "ops-guest", "password": "definitely-wrong"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        entry = ActivityLog.objects.get(action="login_failed")
        self.assertEqual(entry.status, ActivityLog.Status.FAILURE)
        self.assertEqual(entry.module, ActivityLog.Module.AUTH)
        self.assertEqual(entry.metadata["username"], "ops-guest")
        self.assertNotIn("definitely-wrong", str(entry.metadata))
        self.assertNotIn("definitely-wrong", str(entry.before_data))
        self.assertNotIn("definitely-wrong", str(entry.after_data))

    def test_successful_login_is_logged_as_success(self):
        response = APIClient().post(
            "/api/auth/login/",
            {"username": "ops-root", "password": "StrongPass-2026!"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        entry = ActivityLog.objects.get(action="login")
        self.assertEqual(entry.status, ActivityLog.Status.SUCCESS)
        self.assertEqual(entry.actor_username, "ops-root")

    def test_successful_user_update_logs_before_and_after(self):
        self.client.force_authenticate(user=self.superuser)
        response = self.client.patch(
            f"/api/users/{self.guest.pk}/",
            {"full_name": "نام ویرایش‌شده", "role": "admin"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

        entry = ActivityLog.objects.get(action="user_update")
        self.assertEqual(entry.before_data["role"], "guest")
        self.assertEqual(entry.before_data["is_active"], True)
        self.assertEqual(entry.after_data["full_name"], "نام ویرایش‌شده")
        self.assertEqual(entry.after_data["role"], "admin")
        self.assertEqual(
            entry.metadata["changed_fields"], ["first_name", "last_name", "is_staff"]
        )
