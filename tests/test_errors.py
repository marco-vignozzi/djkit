"""
Unit tests for djkit.errors.

Run with: python manage.py test djkit.tests.test_errors
"""

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from djkit.errors import Conflict, ConfirmationRequired, InvalidData, NotFound, require_confirmation


class DomainErrorTests(SimpleTestCase):
    """Domain exceptions carry a message and extra data for the response body."""

    def test_default_detail_when_no_message(self):
        """NotFound() -> 'Not found.'; Conflict('Taken') -> 'Taken'."""
        self.assertEqual(NotFound().payload(), {"detail": "Not found."})
        self.assertEqual(Conflict("Taken").payload(), {"detail": "Taken"})

    def test_extra_data_in_payload_and_none_dropped(self):
        """errors are kept, None values are dropped."""
        error = InvalidData("Check", errors={"email": ["Used"]}, hint=None)
        self.assertEqual(error.payload(), {"detail": "Check", "errors": {"email": ["Used"]}})

    def test_confirmation_required_payload(self):
        """ConfirmationRequired carries impact, required and given."""
        error = ConfirmationRequired({"invoices": 3}, required=2, given=1)
        self.assertEqual(
            error.payload(),
            {"detail": "Confirmation required.", "impact": {"invoices": 3}, "required": 2, "given": 1},
        )


class RequireConfirmationTests(SimpleTestCase):
    """require_confirmation stops until enough confirmations are given."""

    def test_raises_while_given_is_lower(self):
        """given 1, required 2 -> ConfirmationRequired with the impact."""
        with self.assertRaises(ConfirmationRequired) as caught:
            require_confirmation(1, 2, {"invoices": 3})
        self.assertEqual((caught.exception.given, caught.exception.required), (1, 2))
        self.assertEqual(caught.exception.impact, {"invoices": 3})

    def test_passes_when_enough(self):
        """given 2 (or more), required 2 -> no exception."""
        require_confirmation(2, 2, {})
        require_confirmation(3, 2, {})


class FromValidationErrorTests(SimpleTestCase):
    """InvalidData.from_validation_error keeps Django's messages."""

    def test_field_errors_become_errors_dict(self):
        """{'amount': ['Must be positive.']} -> errors with the same content."""
        error = InvalidData.from_validation_error(ValidationError({"amount": ["Must be positive."]}))
        self.assertEqual(error.payload(), {"detail": "Invalid data.", "errors": {"amount": ["Must be positive."]}})

    def test_plain_messages_become_detail(self):
        """ValidationError(['A.', 'B.']) -> detail 'A. B.'."""
        error = InvalidData.from_validation_error(ValidationError(["A.", "B."]))
        self.assertEqual(error.payload(), {"detail": "A. B."})
