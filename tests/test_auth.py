"""
Tests for djkit.auth (password validation and session login).

login_with_password is exercised through the public login endpoint of
djkit/tests/urls.py, so the session cookie is really set.

Run with: python manage.py test djkit.tests.test_auth
"""

from django.test import SimpleTestCase, override_settings

from djkit.auth import DEFAULT_LOGIN_FAILED_DETAIL, validate_new_password
from djkit.errors import InvalidData
from djkit.testing.api import ApiTestCase, make_user

# Validators used by the password tests, independent of the project settings.
MIN_LENGTH_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 8},
    },
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


@override_settings(AUTH_PASSWORD_VALIDATORS=MIN_LENGTH_VALIDATORS)
class ValidateNewPasswordTests(SimpleTestCase):
    """validate_new_password turns validator failures into InvalidData on a field."""

    def test_strong_password_passes(self):
        """'Long-enough-1' -> no error."""
        validate_new_password("Long-enough-1")

    def test_weak_password_reports_every_message_on_password_field(self):
        """'123' -> InvalidData with two messages (too short, entirely numeric) under 'password'."""
        with self.assertRaises(InvalidData) as caught:
            validate_new_password("123")
        errors = caught.exception.extra["errors"]
        self.assertEqual(list(errors), ["password"])
        self.assertEqual(len(errors["password"]), 2)

    def test_custom_field_name(self):
        """field='new_password' -> errors reported under 'new_password'."""
        with self.assertRaises(InvalidData) as caught:
            validate_new_password("123", field="new_password")
        self.assertEqual(list(caught.exception.extra["errors"]), ["new_password"])


@override_settings(ROOT_URLCONF="djkit.tests.urls")
class LoginWithPasswordTests(ApiTestCase):
    """login_with_password starts a session or fails with a generic 422."""

    def setUp(self):
        """One active user with a known password."""
        self.user = make_user(password="Right-pass-1")
        self.username = self.user.get_username()

    def test_right_credentials_start_a_session(self):
        """Right password -> 200 with the user's pk, then a logged-in endpoint answers 200."""
        response = self.client.post("/api/public/login", {"username": self.username, "password": "Right-pass-1"})
        self.assertStatus(response, 200)
        self.assertEqual(response.json(), {"user": self.user.pk})
        self.assertStatus(self.client.post("/api/echo", {"name": "Anna"}), 200)

    def test_wrong_password_and_unknown_user_give_same_error(self):
        """Wrong password and unknown username -> same 422 with the generic message."""
        for username, password in [(self.username, "Wrong-pass-1"), ("nobody@example.com", "Right-pass-1")]:
            with self.subTest(username=username):
                response = self.client.post("/api/public/login", {"username": username, "password": password})
                self.assertStatus(response, 422)
                self.assertEqual(response.json(), {"detail": DEFAULT_LOGIN_FAILED_DETAIL})

    def test_inactive_user_cannot_log_in(self):
        """is_active False -> 422, no session."""
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        response = self.client.post("/api/public/login", {"username": self.username, "password": "Right-pass-1"})
        self.assertStatus(response, 422)
        self.assertStatus(self.client.post("/api/echo", {"name": "Anna"}), 401)
