"""
Tests for the pure functions of djkit.notices (rules, to_notify,
deadline_key), with a registry defined here. The abstract models and
sent_for / record / prune are exercised by the project tests that use
concrete models.

Run with: python manage.py test djkit.tests.test_notices
"""

from datetime import date

from django.test import SimpleTestCase

from djkit.deadlines import Deadline, DeadlineRegistry
from djkit.notices import NoticeRule, deadline_key, rules, to_notify

TODAY = date(2026, 6, 1)


def sample_registry() -> DeadlineRegistry:
    """"invoice_due" on 3/6 and 20/6 (subjects 3 and 20), "renewal" of contract 1 on 10/6."""
    registry = DeadlineRegistry()

    @registry.provider("invoice_due")
    def invoices(user, start, end):
        days = [date(2026, 6, 3), date(2026, 6, 20)]
        return [Deadline("invoice_due", d, "invoice", d.day) for d in days if start <= d <= end]

    @registry.provider("renewal")
    def renewals(user, start, end):
        due = date(2026, 6, 10)
        return [Deadline("renewal", due, "contract", 1)] if start <= due <= end else []

    return registry


DEFAULTS = {"invoice_due": NoticeRule(True, 5), "renewal": NoticeRule(True, 30)}


class RulesTests(SimpleTestCase):
    """rules(): the defaults, replaced by what the user saved."""

    def test_saved_replace_defaults_and_unknown_kinds_are_ignored(self):
        """Saved renewal off and "gone" (not a default) -> invoice default, renewal off, no "gone"."""
        result = rules(DEFAULTS, [("renewal", False, 7), ("gone", True, 1)])
        self.assertEqual(result, {"invoice_due": NoticeRule(True, 5), "renewal": NoticeRule(False, 7)})


class ToNotifyTests(SimpleTestCase):
    """to_notify(): enabled kinds, each in its own window, minus what was already notified."""

    def test_each_kind_has_its_window(self):
        """Today 1/6: invoices within 5 days -> 3/6 only; renewal within 30 -> 10/6."""
        found = to_notify(sample_registry(), None, TODAY, DEFAULTS, {})
        self.assertEqual([(d.kind, d.due_date.day) for d in found], [("invoice_due", 3), ("renewal", 10)])

    def test_disabled_kind_is_skipped(self):
        """Renewal off -> only the invoice."""
        found = to_notify(sample_registry(), None, TODAY, {**DEFAULTS, "renewal": NoticeRule(False, 30)}, {})
        self.assertEqual([d.kind for d in found], ["invoice_due"])

    def test_zero_days_means_only_today(self):
        """Invoices with 0 days on 3/6 -> the 3/6 one; on 1/6 -> nothing."""
        only = {"invoice_due": NoticeRule(True, 0)}
        self.assertEqual(len(to_notify(sample_registry(), None, date(2026, 6, 3), only, {})), 1)
        self.assertEqual(to_notify(sample_registry(), None, TODAY, only, {}), [])

    def test_already_notified_for_the_same_date_is_skipped_but_a_new_date_is_not(self):
        """Invoice 3 notified for 3/6 -> skipped; renewal notified for 10/6 of last year -> notified again."""
        sent = {("invoice_due", "invoice", 3): date(2026, 6, 3), ("renewal", "contract", 1): date(2025, 6, 10)}
        found = to_notify(sample_registry(), None, TODAY, DEFAULTS, sent)
        self.assertEqual([d.kind for d in found], ["renewal"])

    def test_deadline_key_ignores_the_date(self):
        """Same kind, subject and id on two dates -> the same key."""
        first = Deadline("renewal", date(2026, 6, 10), "contract", 1)
        second = Deadline("renewal", date(2027, 6, 10), "contract", 1)
        self.assertEqual(deadline_key(first), deadline_key(second))
