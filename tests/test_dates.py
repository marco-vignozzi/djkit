"""
Unit tests for djkit.dates.

Pure-function tests (SimpleTestCase, no database).

Run with: python manage.py test djkit.tests.test_dates
"""

from datetime import date

from django.test import SimpleTestCase

from djkit.dates import add_months, clamped_date, monthly_due_dates


class ClampedDateTests(SimpleTestCase):
    """clamped_date keeps valid days and clamps missing ones."""

    def test_existing_day_unchanged(self):
        self.assertEqual(clamped_date(2026, 3, 15), date(2026, 3, 15))

    def test_day_31_in_30_day_month(self):
        self.assertEqual(clamped_date(2026, 4, 31), date(2026, 4, 30))

    def test_february_non_leap_and_leap(self):
        self.assertEqual(clamped_date(2026, 2, 30), date(2026, 2, 28))
        self.assertEqual(clamped_date(2028, 2, 30), date(2028, 2, 29))


class AddMonthsTests(SimpleTestCase):
    """add_months handles the year rollover."""

    def test_same_year(self):
        self.assertEqual(add_months(2026, 3, 1), (2026, 4))

    def test_zero_months(self):
        self.assertEqual(add_months(2026, 3, 0), (2026, 3))

    def test_december_to_january(self):
        self.assertEqual(add_months(2026, 12, 1), (2027, 1))

    def test_many_months(self):
        self.assertEqual(add_months(2026, 11, 14), (2028, 1))


class MonthlyDueDatesTests(SimpleTestCase):
    """monthly_due_dates: same day every month, clamped, up to the end date."""

    def test_first_date_on_start_date_then_same_day(self):
        """Start 15/3 -> 15/3, 15/4, 15/5, 15/6 (end 30/6)."""
        self.assertEqual(
            monthly_due_dates(date(2026, 3, 15), date(2026, 6, 30)),
            [date(2026, 3, 15), date(2026, 4, 15), date(2026, 5, 15), date(2026, 6, 15)],
        )

    def test_end_date_is_inclusive(self):
        """A date falling exactly on the end date is included."""
        self.assertEqual(
            monthly_due_dates(date(2026, 3, 15), date(2026, 4, 15)),
            [date(2026, 3, 15), date(2026, 4, 15)],
        )

    def test_no_date_after_end_date(self):
        """End 14/4 -> 15/4 is not generated."""
        self.assertEqual(monthly_due_dates(date(2026, 3, 15), date(2026, 4, 14)), [date(2026, 3, 15)])

    def test_day_31_clamped_without_drifting(self):
        """Start 31/1 -> 28/2, then back to 31/3 and 30/4."""
        self.assertEqual(
            monthly_due_dates(date(2026, 1, 31), date(2026, 4, 30)),
            [date(2026, 1, 31), date(2026, 2, 28), date(2026, 3, 31), date(2026, 4, 30)],
        )

    def test_leap_february(self):
        """Start 30/1/2028 -> 29/2/2028 (leap year)."""
        self.assertEqual(
            monthly_due_dates(date(2028, 1, 30), date(2028, 3, 1)),
            [date(2028, 1, 30), date(2028, 2, 29)],
        )

    def test_year_rollover(self):
        """Start 10/11 -> 10/11, 10/12, 10/1 of the next year."""
        self.assertEqual(
            monthly_due_dates(date(2026, 11, 10), date(2027, 1, 31)),
            [date(2026, 11, 10), date(2026, 12, 10), date(2027, 1, 10)],
        )

    def test_full_year_has_twelve_dates(self):
        self.assertEqual(len(monthly_due_dates(date(2026, 1, 1), date(2026, 12, 31))), 12)

    def test_end_before_start_gives_nothing(self):
        self.assertEqual(monthly_due_dates(date(2026, 5, 1), date(2026, 4, 30)), [])
