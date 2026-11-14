"""Authentication tests: session login, CSRF, logout and access control."""

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIClient, APITestCase


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
