import json
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import Client, TestCase

from .models import EmailVerificationCode, UserProfile


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
        User.objects.create_user(username=self.username, email=self.email, password=self.password)

        response = self.post_json(
            "/api/auth/account/update/",
            {
                "email": self.email,
                "current_password": "wrong-password",
                "display_name": "Updated Name",
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(UserProfile.objects.filter(user__email=self.email).exists())

    def test_account_update_modifies_user_profile_and_password(self):
        user = User.objects.create_user(
            username=self.username,
            email=self.email,
            password=self.password,
            first_name="Old",
            last_name="Name",
        )
        UserProfile.objects.create(user=user, display_name="Old Display", language="English")

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

