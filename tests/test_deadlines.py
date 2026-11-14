"""
Tests for djkit.deadlines (Deadline, DeadlineRegistry), with providers
defined here.

Run with: python manage.py test djkit.tests.test_deadlines
"""

from datetime import date
from decimal import Decimal

from django.test import SimpleTestCase

from djkit.deadlines import Deadline, DeadlineRegistry


def sample_registry() -> DeadlineRegistry:
    """A registry with "invoice_due" (5/6 and 20/6) and "renewal" (10/6) providers."""
    registry = DeadlineRegistry()

    @registry.provider("invoice_due")
    def invoices(user, start, end):
        dates = [date(2026, 6, 20), date(2026, 6, 5)]
        return [Deadline("invoice_due", d, "invoice", d.day, amount=Decimal("10")) for d in dates if start <= d <= end]

    @registry.provider("renewal")
    def renewals(user, start, end):
        due = date(2026, 6, 10)
        return [Deadline("renewal", due, "contract", 1)] if start <= due <= end else []

    return registry


class DeadlineRegistryTests(SimpleTestCase):
    """DeadlineRegistry merges its providers and fails loudly on mistakes."""

    def test_collect_merges_and_sorts_by_date(self):
        """June -> invoice 5/6, renewal 10/6, invoice 20/6."""
        found = sample_registry().collect(None, date(2026, 6, 1), date(2026, 6, 30))
        self.assertEqual([(d.kind, d.due_date.day) for d in found], [("invoice_due", 5), ("renewal", 10), ("invoice_due", 20)])

    def test_collect_only_some_kinds(self):
        """kinds=["renewal"] -> only the renewal; kinds() -> both, sorted."""
        registry = sample_registry()
        self.assertEqual([d.kind for d in registry.collect(None, date(2026, 6, 1), date(2026, 6, 30), ["renewal"])], ["renewal"])
        self.assertEqual(registry.kinds(), ["invoice_due", "renewal"])

    def test_duplicate_kind_unknown_kind_and_reversed_period_raise(self):
        """Second provider for "renewal", kind "nope", end before start -> ValueError."""
        registry = sample_registry()
        with self.assertRaises(ValueError):
            registry.provider("renewal")(lambda user, start, end: [])
        with self.assertRaises(ValueError):
            registry.collect(None, date(2026, 6, 1), date(2026, 6, 30), ["nope"])
        with self.assertRaises(ValueError):
            registry.collect(None, date(2026, 6, 30), date(2026, 6, 1))

    def test_provider_returning_a_wrong_deadline_raises(self):
        """A provider giving another kind, or a date outside the period -> ValueError."""
        for wrong in (Deadline("other", date(2026, 6, 1), "x", 1), Deadline("bad", date(2027, 1, 1), "x", 1)):
            registry = DeadlineRegistry()
            registry.provider("bad")(lambda user, start, end, wrong=wrong: [wrong])
            with self.subTest(wrong=wrong), self.assertRaises(ValueError):
                registry.collect(None, date(2026, 6, 1), date(2026, 6, 30))
