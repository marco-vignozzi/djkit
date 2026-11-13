"""
Tests for djkit.auth (password validation and session login).

login_with_password is exercised through the public login endpoint of
djkit/tests/urls.py, so the session cookie is really set.

Run with: python manage.py test djkit.tests.test_auth
"""

from datetime import datetime, timedelta
from unittest import mock

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils.http import urlsafe_base64_encode

from djkit.auth import (
    MinimumLengthValidator,
    UserAttributeSimilarityValidator,
    password_reset_token,
    reset_password,
    user_for_password_reset,
    validate_new_password,
)
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


@override_settings(ROOT_URLCONF="djkit.tests.urls", DJKIT_MESSAGES={})
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
        """Wrong password and unknown username -> same 422 'Invalid credentials.'."""
        for username, password in [(self.username, "Wrong-pass-1"), ("nobody@example.com", "Right-pass-1")]:
            with self.subTest(username=username):
                response = self.client.post("/api/public/login", {"username": username, "password": password})
                self.assertStatus(response, 422)
                self.assertEqual(response.json(), {"detail": "Invalid credentials."})

    def test_inactive_user_cannot_log_in(self):
        """is_active False -> 422, no session."""
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        response = self.client.post("/api/public/login", {"username": self.username, "password": "Right-pass-1"})
        self.assertStatus(response, 422)
        self.assertStatus(self.client.post("/api/echo", {"name": "Anna"}), 401)


# Texts used to check that the djkit validators follow DJKIT_MESSAGES.
VALIDATOR_MESSAGES = {
    "password_too_short": "Troppo corta: almeno {min_length} caratteri.",
    "password_too_similar": "Troppo simile ai tuoi dati.",
}


@override_settings(DJKIT_MESSAGES=VALIDATOR_MESSAGES)
class PasswordValidatorTests(ApiTestCase):
    """djkit's password validators keep Django's rules and use djkit messages."""

    def test_minimum_length_message_has_the_limit(self):
        """min_length 10, password 'short' -> 'Troppo corta: almeno 10 caratteri.'."""
        with self.assertRaises(ValidationError) as caught:
            MinimumLengthValidator(min_length=10).validate("short")
        self.assertEqual(caught.exception.messages, ["Troppo corta: almeno 10 caratteri."])
        self.assertEqual(MinimumLengthValidator(min_length=10).get_help_text(), "Troppo corta: almeno 10 caratteri.")

    def test_minimum_length_accepts_long_enough(self):
        """min_length 8, 'long-enough' -> no error."""
        MinimumLengthValidator(min_length=8).validate("long-enough")

    def test_similarity_message_does_not_name_the_field(self):
        """Password equal to the user's username -> 'Troppo simile ai tuoi dati.' (code password_too_similar)."""
        user = make_user()
        with self.assertRaises(ValidationError) as caught:
            UserAttributeSimilarityValidator().validate(user.get_username(), user)
        self.assertEqual(caught.exception.messages, ["Troppo simile ai tuoi dati."])
        self.assertEqual(caught.exception.error_list[0].code, "password_too_similar")

    def test_similarity_accepts_unrelated_password(self):
        """'Zebra-Quartz-77' vs a generated user -> no error."""
        UserAttributeSimilarityValidator().validate("Zebra-Quartz-77", make_user())


@override_settings(AUTH_PASSWORD_VALIDATORS=MIN_LENGTH_VALIDATORS, DJKIT_MESSAGES={}, PASSWORD_RESET_TIMEOUT=3600)
class PasswordResetTests(TestCase):
    """password_reset_token / user_for_password_reset / reset_password: a link valid once, for a limited time."""

    # Message of every invalid link (English default of djkit).
    INVALID = "The password reset link is invalid or has expired: request a new one."

    def setUp(self):
        """One active user with a known password and a fresh link."""
        self.user = make_user(password="Old-pass-123")
        self.uid, self.token = password_reset_token(self.user)

    def assertInvalidLink(self, uid, token):
        """The link is rejected with the generic message and no field errors."""
        with self.assertRaises(InvalidData) as caught:
            user_for_password_reset(uid, token)
        self.assertEqual(caught.exception.payload(), {"detail": self.INVALID})

    def test_valid_link_sets_the_new_password(self):
        """Right uid and token -> the user; reset_password -> new password works, old one no longer."""
        self.assertEqual(user_for_password_reset(self.uid, self.token), self.user)
        reset_password(self.uid, self.token, "New-pass-456")
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("New-pass-456"))
        self.assertFalse(self.user.check_password("Old-pass-123"))

    def test_link_works_only_once(self):
        """After a reset the same link is invalid (the token depends on the password)."""
        reset_password(self.uid, self.token, "New-pass-456")
        self.assertInvalidLink(self.uid, self.token)

    def test_expired_link(self):
        """Token checked 2 hours later with a validity of 1 hour -> invalid."""
        later = datetime.now() + timedelta(hours=2)
        with mock.patch("django.contrib.auth.tokens.PasswordResetTokenGenerator._now", return_value=later):
            self.assertInvalidLink(self.uid, self.token)

    def test_wrong_token_malformed_or_unknown_uid(self):
        """Wrong token, uid not base64, uid of no user -> same generic error."""
        for uid, token in [
            (self.uid, "wrong-token"),
            ("!!not-base64!!", self.token),
            (urlsafe_base64_encode(b"999999999"), self.token),
            (urlsafe_base64_encode(b"abc"), self.token),
        ]:
            with self.subTest(uid=uid, token=token):
                self.assertInvalidLink(uid, token)

    def test_inactive_user(self):
        """is_active False -> invalid, even with a right token."""
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        self.assertInvalidLink(self.uid, self.token)

    def test_weak_password_rejected_and_link_still_valid(self):
        """'123' -> InvalidData on 'new_password'; the password is unchanged and the link still works."""
        with self.assertRaises(InvalidData) as caught:
            reset_password(self.uid, self.token, "123")
        self.assertIn("new_password", caught.exception.payload()["errors"])
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("Old-pass-123"))
        self.assertEqual(user_for_password_reset(self.uid, self.token), self.user)
