"""
Tests of the formatting helpers of djkit.it (the tax code ones are in
test_validators).

Run with: python manage.py test djkit.tests.test_it
"""

from datetime import date
from decimal import Decimal

from django.test import SimpleTestCase

from djkit.it import format_amount, format_date, format_names, format_percent


class FormatTests(SimpleTestCase):
    """format_date, format_amount, format_percent, format_names: values as Italian texts show them."""

    def test_amount_and_date(self):
        """1234.5 -> "1.234,50"; 650 -> "650,00"; 15/3/2026 -> "15/03/2026"."""
        self.assertEqual(format_amount(Decimal("1234.5")), "1.234,50")
        self.assertEqual(format_amount(Decimal("650")), "650,00")
        self.assertEqual(format_date(date(2026, 3, 15)), "15/03/2026")

    def test_percent_without_useless_zeros(self):
        """50.00 -> "50"; 33.33 -> "33,33"; 21 -> "21"; 12.50 -> "12,5"."""
        for value, shown in (("50.00", "50"), ("33.33", "33,33"), ("21", "21"), ("12.50", "12,5")):
            self.assertEqual(format_percent(Decimal(value)), shown)

    def test_zero_one_two_and_three_names(self):
        """[] -> "", [Anna] -> "Anna", two -> "Anna e Bruno", three -> "Anna, Bruno e Carla"."""
        self.assertEqual(format_names([]), "")
        self.assertEqual(format_names(["Anna"]), "Anna")
        self.assertEqual(format_names(["Anna", "Bruno"]), "Anna e Bruno")
        self.assertEqual(format_names(["Anna", "Bruno", "Carla"]), "Anna, Bruno e Carla")
