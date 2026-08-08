import json
from unittest.mock import Mock, patch

from django.contrib.auth import SESSION_KEY
from django.contrib.auth.models import User
from django.test import Client, TestCase, override_settings
from requests import HTTPError

from .auth_data import send_email
from .models import EmailVerificationCode, UserProfile


@override_settings(EMAIL_VERIFICATION_ENABLED=True)
class EmailVerificationRegistrationTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.email = "new-user@example.com"
        self.username = "newuser"
        self.password = "safe-password-123"

    def post_json(self, path: str, payload: dict):
        return self.client.post(
            path,
            data=json.dumps(payload),
            content_type="application/json",
        )

    def test_register_requires_verified_email(self):
        response = self.post_json(
            "/api/auth/register/",
            {
                "email": self.email,
                "username": self.username,
                "password": self.password,
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(User.objects.filter(email=self.email).exists())

    @override_settings(EMAIL_VERIFICATION_ENABLED=False)
    def test_register_skips_email_verification_when_disabled(self):
        response = self.post_json(
            "/api/auth/register/",
            {
                "email": self.email,
                "username": self.username,
                "password": self.password,
                "confirm_password": self.password,
                "first_name": "New",
                "last_name": "User",
            },
        )

        self.assertEqual(response.status_code, 201)
        self.assertTrue(User.objects.filter(email=self.email).exists())
        self.assertFalse(EmailVerificationCode.objects.filter(email=self.email).exists())

    @override_settings(EMAIL_VERIFICATION_ENABLED=False)
    @patch("auth_model.views.send_email")
    def test_email_verification_endpoints_noop_when_disabled(self, mock_send_email):
        request_response = self.post_json(
            "/api/auth/request-code/",
            {"email": self.email, "name": "New User"},
        )
        verify_response = self.post_json(
            "/api/auth/verify-code/",
            {"email": self.email, "code": "not-a-code"},
        )

        self.assertEqual(request_response.status_code, 200)
        self.assertEqual(verify_response.status_code, 200)
        mock_send_email.assert_not_called()
        self.assertFalse(EmailVerificationCode.objects.filter(email=self.email).exists())

    @patch("auth_model.views.send_email")
    @patch("auth_model.views._generate_verification_code", return_value="123456")
    def test_user_can_register_after_email_verification(self, _mock_code, mock_send_email):
        request_response = self.post_json(
            "/api/auth/request-code/",
            {"email": self.email, "name": "New User"},
        )
        self.assertEqual(request_response.status_code, 201)
        mock_send_email.assert_called_once_with(self.email, "123456", "New User")
        self.assertEqual(EmailVerificationCode.objects.filter(email=self.email).count(), 1)

        verify_response = self.post_json(
            "/api/auth/verify-code/",
            {"email": self.email, "code": "123456"},
        )
        self.assertEqual(verify_response.status_code, 200)

        register_response = self.post_json(
            "/api/auth/register/",
            {
                "email": self.email,
                "username": self.username,
                "password": self.password,
                "confirm_password": self.password,
                "first_name": "New",
                "last_name": "User",
                "display_name": "Neighborhood Helper",
                "location": "San Jose, CA",
                "profile_focus": "I am looking for community resources",
                "receive_updates": True,
                "nickname": "Jamie",
                "age_group": "adult",
                "language": "Japanese",
                "avatar_color": "Lavender",
                "self_introduction": "I like helping my community.",
            },
        )
        self.assertEqual(register_response.status_code, 201)

        user = User.objects.get(email=self.email)
        self.assertEqual(user.username, self.username)
        self.assertEqual(user.first_name, "New")
        self.assertEqual(user.last_name, "User")
        self.assertTrue(user.check_password(self.password))
        profile = UserProfile.objects.get(user=user)
        self.assertEqual(profile.role, UserProfile.ROLE_USER)
        self.assertEqual(profile.display_name, "Neighborhood Helper")
        self.assertEqual(profile.location, "San Jose, CA")
        self.assertEqual(profile.profile_focus, "I am looking for community resources")
        self.assertTrue(profile.receive_updates)
        self.assertEqual(profile.nickname, "Jamie")
        self.assertEqual(profile.age_group, "adult")
        self.assertEqual(profile.language, "Japanese")
        self.assertEqual(profile.avatar_color, "Lavender")
        self.assertEqual(profile.self_introduction, "I like helping my community.")
        self.assertTrue(EmailVerificationCode.objects.get(email=self.email).is_consumed)

    @patch("auth_model.views.send_email")
    @patch("auth_model.views._generate_verification_code", side_effect=["111111", "222222"])
    def test_user_can_register_after_verified_email_requests_another_code(self, _mock_code, mock_send_email):
        first_request = self.post_json(
            "/api/auth/request-code/",
            {"email": self.email, "name": "New User"},
        )
        self.assertEqual(first_request.status_code, 201)

        verify_response = self.post_json(
            "/api/auth/verify-code/",
            {"email": self.email, "code": "111111"},
        )
        self.assertEqual(verify_response.status_code, 200)

        second_request = self.post_json(
            "/api/auth/request-code/",
            {"email": self.email, "name": "New User"},
        )
        self.assertEqual(second_request.status_code, 201)
        self.assertEqual(mock_send_email.call_count, 2)

        register_response = self.post_json(
            "/api/auth/register/",
            {
                "email": self.email,
                "username": self.username,
                "password": self.password,
                "confirm_password": self.password,
                "first_name": "New",
                "last_name": "User",
            },
        )

        self.assertEqual(register_response.status_code, 201)
        self.assertTrue(User.objects.filter(email=self.email).exists())

    def test_account_update_requires_current_password(self):
        user = User.objects.create_user(username=self.username, email=self.email, password=self.password)
        self.client.force_login(user)

        response = self.post_json(
            "/api/auth/account/update/",
            {
                "email": self.email,
                "current_password": "wrong-password",
                "display_name": "Updated Name",
            },
        )

        self.assertEqual(response.status_code, 403)

    def test_account_update_modifies_user_profile_and_password(self):
        user = User.objects.create_user(
            username=self.username,
            email=self.email,
            password=self.password,
            first_name="Old",
            last_name="Name",
        )
        UserProfile.objects.create(user=user, display_name="Old Display", language="English")
        self.client.force_login(user)

        response = self.post_json(
            "/api/auth/account/update/",
            {
                "email": self.email,
                "current_password": self.password,
                "username": "updateduser",
                "first_name": "Jamie",
                "last_name": "Lee",
                "display_name": "Neighborhood Helper",
                "location": "San Jose, CA",
                "profile_focus": "I am looking for community resources",
                "receive_updates": True,
                "nickname": "Helper",
                "age_group": "adult",
                "language": "Japanese",
                "avatar_color": "Mint",
                "self_introduction": "Updated intro",
                "new_password": "new-safe-password-123",
                "confirm_new_password": "new-safe-password-123",
            },
        )

        self.assertEqual(response.status_code, 200)
        user.refresh_from_db()
        profile = UserProfile.objects.get(user=user)
        self.assertEqual(user.username, "updateduser")
        self.assertEqual(user.first_name, "Jamie")
        self.assertEqual(user.last_name, "Lee")
        self.assertTrue(user.check_password("new-safe-password-123"))
        self.assertEqual(profile.display_name, "Neighborhood Helper")
        self.assertEqual(profile.location, "San Jose, CA")
        self.assertEqual(profile.profile_focus, "I am looking for community resources")
        self.assertTrue(profile.receive_updates)
        self.assertEqual(profile.nickname, "Helper")
        self.assertEqual(profile.age_group, "adult")
        self.assertEqual(profile.language, "Japanese")
        self.assertEqual(profile.avatar_color, "Mint")
        self.assertEqual(profile.self_introduction, "Updated intro")

    def test_account_update_requires_login(self):
        User.objects.create_user(username=self.username, email=self.email, password=self.password)

        response = self.post_json(
            "/api/auth/account/update/",
            {
                "email": self.email,
                "current_password": self.password,
                "display_name": "Updated Name",
            },
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"], "Authentication required")

    def test_login_with_email_and_password_creates_session(self):
        user = User.objects.create_user(
            username=self.username,
            email=self.email,
            password=self.password,
            first_name="New",
            last_name="User",
        )
        UserProfile.objects.create(user=user, display_name="Neighborhood Helper", language="Japanese")

        response = self.post_json(
            "/api/auth/login/",
            {
                "email": f"  {self.email.upper()}  ",
                "password": self.password,
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["message"], "Login successful")
        self.assertEqual(payload["user"]["email"], self.email)
        self.assertEqual(payload["user"]["username"], self.username)
        self.assertEqual(payload["user"]["role"], UserProfile.ROLE_USER)
        self.assertEqual(payload["profile"]["role"], UserProfile.ROLE_USER)
        self.assertEqual(payload["profile"]["display_name"], "Neighborhood Helper")
        self.assertEqual(str(user.pk), self.client.session[SESSION_KEY])

    def test_login_rejects_invalid_email_or_password(self):
        User.objects.create_user(username=self.username, email=self.email, password=self.password)

        wrong_password_response = self.post_json(
            "/api/auth/login/",
            {
                "email": self.email,
                "password": "wrong-password",
            },
        )
        unknown_email_response = self.post_json(
            "/api/auth/login/",
            {
                "email": "missing@example.com",
                "password": self.password,
            },
        )

        self.assertEqual(wrong_password_response.status_code, 403)
        self.assertEqual(wrong_password_response.json()["error"], "Invalid email or password")
        self.assertEqual(unknown_email_response.status_code, 403)
        self.assertEqual(unknown_email_response.json()["error"], "Invalid email or password")

    def test_login_requires_password(self):
        response = self.post_json(
            "/api/auth/login/",
            {
                "email": self.email,
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "Password is required")

    def test_logout_clears_authenticated_session(self):
        user = User.objects.create_user(username=self.username, email=self.email, password=self.password)
        self.client.force_login(user)
        self.assertEqual(str(user.pk), self.client.session[SESSION_KEY])

        response = self.post_json("/api/auth/logout/", {})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["message"], "Logout successful")
        self.assertTrue(response.json()["was_authenticated"])
        self.assertNotIn(SESSION_KEY, self.client.session)

    def test_logout_succeeds_when_already_logged_out(self):
        response = self.post_json("/api/auth/logout/", {})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["message"], "Logout successful")
        self.assertFalse(response.json()["was_authenticated"])


class RoleApiTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="regular",
            email="regular@example.com",
            password="safe-password-123",
        )
        self.user_profile = UserProfile.objects.create(user=self.user)
        self.admin = User.objects.create_user(
            username="admin",
            email="admin@example.com",
            password="safe-password-123",
        )
        self.admin_profile = UserProfile.objects.create(user=self.admin, role=UserProfile.ROLE_ADMIN)

    def put_json(self, path: str, payload: dict):
        return self.client.put(
            path,
            data=json.dumps(payload),
            content_type="application/json",
        )

    def test_current_role_requires_authentication(self):
        response = self.client.get("/api/auth/role/")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"], "Authentication required")

    def test_current_role_returns_authenticated_user_role(self):
        self.client.force_login(self.user)

        response = self.client.get("/api/auth/role/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["role"], UserProfile.ROLE_USER)
        self.assertEqual(response.json()["user"]["role"], UserProfile.ROLE_USER)

    def test_admin_can_access_user_role_required_api(self):
        self.client.force_login(self.admin)

        response = self.client.get("/api/auth/role/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["role"], UserProfile.ROLE_ADMIN)
        self.assertEqual(response.json()["user"]["role"], UserProfile.ROLE_ADMIN)

    def test_health_check_requires_user_role(self):
        response = self.client.get("/api/health/")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"], "Authentication required")

    def test_user_can_access_health_check(self):
        self.client.force_login(self.user)

        response = self.client.get("/api/health/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_admin_can_access_health_check(self):
        self.client.force_login(self.admin)

        response = self.client.get("/api/health/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_user_role_api_requires_admin_role(self):
        self.client.force_login(self.user)

        response = self.put_json(f"/api/users/{self.user.pk}/role/", {"role": UserProfile.ROLE_ADMIN})

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"], "admin role required")
        self.user_profile.refresh_from_db()
        self.assertEqual(self.user_profile.role, UserProfile.ROLE_USER)

    def test_admin_can_change_user_role(self):
        self.client.force_login(self.admin)

        response = self.put_json(f"/api/users/{self.user.pk}/role/", {"role": UserProfile.ROLE_ADMIN})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["message"], "User role updated")
        self.assertEqual(response.json()["role"], UserProfile.ROLE_ADMIN)
        self.user_profile.refresh_from_db()
        self.assertEqual(self.user_profile.role, UserProfile.ROLE_ADMIN)

    def test_admin_role_api_rejects_invalid_role(self):
        self.client.force_login(self.admin)

        response = self.put_json(f"/api/users/{self.user.pk}/role/", {"role": "owner"})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["valid_roles"], [UserProfile.ROLE_ADMIN, UserProfile.ROLE_USER])

    def test_pr_info_requires_user_role(self):
        response = self.client.get("/api/pr-info/?repo=owner/repo&pr=1")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"], "Authentication required")


class MailerSendIntegrationTests(TestCase):
    @override_settings(
        MAILERSEND_API_TOKEN="test-token",
        MAILERSEND_API_URL="https://api.example.test/email",
        MAILERSEND_FROM_EMAIL="verified@example.com",
        MAILERSEND_FROM_NAME="Sweet Tea",
    )
    @patch("auth_model.auth_data.requests.post")
    def test_send_email_posts_mailersend_payload(self, mock_post):
        response = Mock()
        response.content = b'{"id":"email-id"}'
        response.json.return_value = {"id": "email-id"}
        response.raise_for_status.return_value = None
        mock_post.return_value = response

        result = send_email("recipient@example.com", "123456", "Recipient")

        self.assertEqual(result, {"id": "email-id"})
        mock_post.assert_called_once()
        self.assertEqual(mock_post.call_args.kwargs["headers"]["Authorization"], "Bearer test-token")
        self.assertEqual(mock_post.call_args.kwargs["timeout"], 10)

        payload = mock_post.call_args.kwargs["json"]
        self.assertEqual(payload["from"], {"email": "verified@example.com", "name": "Sweet Tea"})
        self.assertEqual(payload["to"], [{"email": "recipient@example.com", "name": "Recipient"}])
        self.assertEqual(payload["subject"], "Your Sweet Tea verification code")
        self.assertIn("123456", payload["text"])
        self.assertIn("123456", payload["html"])
        self.assertNotIn("personalization", payload)

    @override_settings(
        MAILERSEND_API_TOKEN="test-token",
        MAILERSEND_API_URL="https://api.example.test/email",
        MAILERSEND_FROM_EMAIL="unverified@example.com",
        MAILERSEND_FROM_NAME="Sweet Tea",
    )
    @patch("auth_model.auth_data.requests.post")
    def test_send_email_includes_mailersend_validation_details(self, mock_post):
        response = Mock()
        response.status_code = 422
        response.text = '{"message":"The from.email must be a verified email address."}'
        response.json.return_value = {"message": "The from.email must be a verified email address."}
        response.raise_for_status.side_effect = HTTPError("422 Client Error", response=response)
        mock_post.return_value = response

        with self.assertRaisesMessage(RuntimeError, "from.email must be a verified email address"):
            send_email("recipient@example.com", "123456", "Recipient")


class CorsConfigurationTests(TestCase):
    @override_settings(CORS_ALLOW_ALL_ORIGINS=True, CORS_ALLOW_CREDENTIALS=False)
    def test_preflight_request_allows_cross_origin(self):
        response = self.client.options(
            "/api/auth/request-code/",
            HTTP_ORIGIN="http://localhost:3000",
            HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["access-control-allow-origin"], "*")

    @override_settings(CORS_ALLOW_ALL_ORIGINS=True, CORS_ALLOW_CREDENTIALS=True)
    def test_preflight_request_allows_credentialed_cross_origin(self):
        response = self.client.options(
            "/api/auth/request-code/",
            HTTP_ORIGIN="http://localhost:5173",
            HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST",
            HTTP_ACCESS_CONTROL_REQUEST_HEADERS="content-type",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["access-control-allow-origin"], "http://localhost:5173")
        self.assertEqual(response["access-control-allow-credentials"], "true")

    @override_settings(CORS_ALLOW_ALL_ORIGINS=True, CORS_ALLOW_CREDENTIALS=True)
    def test_post_response_allows_credentialed_cross_origin(self):
        response = self.client.post(
            "/api/auth/request-code/",
            data=json.dumps({"email": "not-an-email"}),
            content_type="application/json",
            HTTP_ORIGIN="http://localhost:5173",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response["access-control-allow-origin"], "http://localhost:5173")
        self.assertEqual(response["access-control-allow-credentials"], "true")
