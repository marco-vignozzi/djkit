"""
Unit tests for djkit.validators and djkit.it.

Pure-function tests (SimpleTestCase, no database).

Run with: python manage.py test djkit.tests.test_validators
"""

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from djkit.it import TAX_CODE_LENGTH, normalize_tax_code, validate_tax_code
from djkit.validators import normalize_email_address, strip_text_values


class NormalizeEmailAddressTests(SimpleTestCase):
    """normalize_email_address trims and lowercases."""

    def test_spaces_removed_and_lowercased(self):
        """' Mario@Mail.COM ' -> 'mario@mail.com'."""
        self.assertEqual(normalize_email_address(" Mario@Mail.COM "), "mario@mail.com")

    def test_none_stays_none(self):
        """None is returned unchanged (optional fields)."""
        self.assertIsNone(normalize_email_address(None))


class StripTextValuesTests(SimpleTestCase):
    """strip_text_values removes the spaces around text values only."""

    def test_text_values_are_stripped_and_others_kept(self):
        """{"city": "  Rome ", "blank": "   ", "count": 3, "note": None} -> "Rome", "", 3, None."""
        data = {"city": "  Rome ", "blank": "   ", "count": 3, "note": None}
        self.assertEqual(strip_text_values(data), {"city": "Rome", "blank": "", "count": 3, "note": None})

    def test_input_is_not_changed(self):
        """The dict passed in keeps its original values."""
        data = {"city": " Rome "}
        strip_text_values(data)
        self.assertEqual(data, {"city": " Rome "})


class TaxCodeTests(SimpleTestCase):
    """Italian tax code: normalization and validation."""

    def test_normalize_trims_and_uppercases(self):
        """' rssmra80a01h501u ' -> 'RSSMRA80A01H501U'."""
        self.assertEqual(normalize_tax_code(" rssmra80a01h501u "), "RSSMRA80A01H501U")

    def test_normalize_keeps_none(self):
        """None is returned unchanged."""
        self.assertIsNone(normalize_tax_code(None))

    def test_valid_code_accepted(self):
        """16 uppercase letters or digits pass the validator."""
        validate_tax_code("RSSMRA80A01H501U")

    def test_wrong_length_or_characters_rejected(self):
        """15 characters, 17 characters, lowercase or symbols -> invalid_tax_code."""
        for value in ("RSSMRA80A01H501", "RSSMRA80A01H501UX", "rssmra80a01h501u", "RSSMRA80A01H501-"):
            with self.subTest(value=value), self.assertRaises(ValidationError) as caught:
                validate_tax_code(value)
            self.assertEqual(caught.exception.code, "invalid_tax_code")

    def test_length_constant(self):
        """TAX_CODE_LENGTH is 16."""
        self.assertEqual(TAX_CODE_LENGTH, 16)
