"""
Tests for djkit.dev (relaxed validation switch) and the checks it relaxes.

Run with: python manage.py test djkit.tests.test_dev
"""

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.test import SimpleTestCase, override_settings

from djkit.auth import validate_new_password
from djkit.dev import relaxed_validation
from djkit.errors import InvalidData
from djkit.it import validate_tax_code


class RelaxedValidationSwitchTests(SimpleTestCase):
    """relaxed_validation reads DJKIT_RELAXED_VALIDATION, only with DEBUG."""

    def test_runner_forces_the_switch_off(self):
        """While the tests run the setting is False, whatever the .env says."""
        self.assertIs(settings.DJKIT_RELAXED_VALIDATION, False)
        self.assertFalse(relaxed_validation())

    @override_settings(DJKIT_RELAXED_VALIDATION=True, DEBUG=True)
    def test_on_with_debug(self):
        """True with DEBUG -> True."""
        self.assertTrue(relaxed_validation())

    @override_settings(DJKIT_RELAXED_VALIDATION=True, DEBUG=False)
    def test_on_without_debug_raises(self):
        """True without DEBUG -> ImproperlyConfigured (never in production)."""
        with self.assertRaises(ImproperlyConfigured):
            relaxed_validation()


class RelaxedChecksTests(SimpleTestCase):
    """What the switch relaxes: password rules and tax code length."""

    def test_strict_rejects_short_password_and_tax_code(self):
        """Switch off: password "a" -> InvalidData; tax code "ABC" -> ValidationError."""
        with self.assertRaises(InvalidData):
            validate_new_password("a")
        with self.assertRaises(ValidationError):
            validate_tax_code("ABC")
        validate_tax_code("RSSMRA80A01H501U")

    @override_settings(DJKIT_RELAXED_VALIDATION=True, DEBUG=True)
    def test_relaxed_accepts_short_password_and_tax_code(self):
        """Switch on: password "a" and tax code "ABC" accepted."""
        validate_new_password("a")
        validate_tax_code("ABC")

    @override_settings(DJKIT_RELAXED_VALIDATION=True, DEBUG=True)
    def test_relaxed_keeps_the_tax_code_format(self):
        """Switch on: still letters/digits only and at most 16 ("AB-C", 17 chars -> ValidationError)."""
        for value in ["AB-C", "A" * 17, ""]:
            with self.subTest(value=value), self.assertRaises(ValidationError):
                validate_tax_code(value)
