"""
Tests for djkit.numbers.

Run with: python manage.py test djkit.tests.test_numbers
"""

from decimal import Decimal

from django.test import SimpleTestCase

from djkit.numbers import split_evenly


class SplitEvenlyTests(SimpleTestCase):
    """split_evenly divides a total into equal parts adding up exactly to it."""

    def test_exact_division(self):
        """50.00 into 2 -> [25.00, 25.00]."""
        self.assertEqual(split_evenly(Decimal("50.00"), 2), [Decimal("25.00"), Decimal("25.00")])

    def test_leftover_cents_go_to_the_first_parts(self):
        """100 into 3 -> [33.34, 33.33, 33.33]; 0.05 into 3 -> [0.02, 0.02, 0.01]."""
        self.assertEqual(split_evenly(Decimal("100"), 3), [Decimal("33.34"), Decimal("33.33"), Decimal("33.33")])
        self.assertEqual(split_evenly(Decimal("0.05"), 3), [Decimal("0.02"), Decimal("0.02"), Decimal("0.01")])

    def test_parts_always_add_up_to_the_total(self):
        """Totals 0.01 to 1.00 into 1 to 7 parts: the sum is always the total."""
        for cents in range(1, 101):
            total = Decimal(cents) / 100
            for parts in range(1, 8):
                with self.subTest(total=total, parts=parts):
                    self.assertEqual(sum(split_evenly(total, parts)), total)

    def test_custom_step(self):
        """10 into 3 with step 1 -> [4, 3, 3]."""
        self.assertEqual(split_evenly(Decimal("10"), 3, step=Decimal("1")), [4, 3, 3])

    def test_invalid_arguments(self):
        """0 parts, or a total with more decimals than the step -> ValueError."""
        with self.assertRaises(ValueError):
            split_evenly(Decimal("10"), 0)
        with self.assertRaises(ValueError):
            split_evenly(Decimal("10.005"), 2)
