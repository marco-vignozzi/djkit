"""
Tests for djkit.auth (password validation and session login).

login_with_password is exercised through the public login endpoint of
djkit/tests/urls.py, so the session cookie is really set.

Run with: python manage.py test djkit.tests.test_auth
"""

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, override_settings

from djkit.auth import MinimumLengthValidator, UserAttributeSimilarityValidator, validate_new_password
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
