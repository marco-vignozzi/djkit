"""
Tests for djkit.deadlines (Deadline, DeadlineRegistry, urgency), with
providers defined here.

Run with: python manage.py test djkit.tests.test_deadlines
"""

from datetime import date
from decimal import Decimal

from django.test import SimpleTestCase

from djkit.deadlines import Deadline, DeadlineRegistry, urgency


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


class UrgencyTests(SimpleTestCase):
    """urgency: the code of a deadline by how close it is."""

    LEVELS = [(30, "month"), (7, "week")]
    TODAY = date(2026, 6, 10)

    def code(self, due: date) -> str | None:
        """urgency of `due` on 10/6/2026 with week (7 days) and month (30 days) levels."""
        return urgency(due, self.TODAY, self.LEVELS, overdue="late")

    def test_levels_by_distance(self):
        """9/6 late; 10/6 and 17/6 week; 18/6 and 10/7 month; 11/7 None."""
        cases = {
            date(2026, 6, 9): "late",
            date(2026, 6, 10): "week",
            date(2026, 6, 17): "week",
            date(2026, 6, 18): "month",
            date(2026, 7, 10): "month",
            date(2026, 7, 11): None,
        }
        for due, expected in cases.items():
            with self.subTest(due=due):
                self.assertEqual(self.code(due), expected)

    def test_invalid_levels_are_a_bug(self):
        """Negative days, or two levels with the same days -> ValueError."""
        for levels in ([(-1, "x")], [(7, "a"), (7, "b")]):
            with self.subTest(levels=levels), self.assertRaises(ValueError):
                urgency(self.TODAY, self.TODAY, levels, overdue="late")
