"""
Unit tests for djkit.fields.

Run with: python manage.py test djkit.tests.test_fields
"""

from django.db import models
from django.db.models import Q
from django.test import SimpleTestCase

from djkit.fields import DEFAULT_CHOICE_LENGTH, choice_field, choices_constraint, money_field, positive_constraint


class Color(models.TextChoices):
    """Choices used by the tests."""

    RED = "RED", "Red"
    BLUE = "BLUE", "Blue"


class FieldHelperTests(SimpleTestCase):
    """Field builders and CHECK constraints."""

    def test_choice_field(self):
        """choice_field('color', Color) -> CharField(12) with Color's choices."""
        field = choice_field("color", Color)
        self.assertIsInstance(field, models.CharField)
        self.assertEqual(field.max_length, DEFAULT_CHOICE_LENGTH)
        self.assertEqual(field.choices, Color.choices)
        self.assertEqual(choice_field("color", Color, max_length=20).max_length, 20)

    def test_choices_constraint(self):
        """choices_constraint('color', Color.values, 'c') -> CHECK color IN ('RED', 'BLUE')."""
        constraint = choices_constraint("color", Color.values, "c")
        self.assertEqual(constraint.condition, Q(color__in=["RED", "BLUE"]))
        self.assertEqual(constraint.name, "c")

    def test_money_field(self):
        """money_field -> DecimalField(10, 2) by default."""
        field = money_field("amount")
        self.assertEqual((field.max_digits, field.decimal_places), (10, 2))

    def test_positive_constraint(self):
        """positive_constraint('amount', 'p') -> CHECK amount > 0."""
        self.assertEqual(positive_constraint("amount", "p").condition, Q(amount__gt=0))
