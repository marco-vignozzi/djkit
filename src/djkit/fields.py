"""
Model field helpers.

    - choice_field: VARCHAR column restricted to a TextChoices class.
    - choices_constraint: database CHECK that the column holds only allowed
      values (Django validates choices in forms and full_clean, but does not
      create a database constraint by itself).
"""

from django.db import models
from django.db.models import Q

# Default length of a "choice" column: enough for short codes such as
# "SETTLEMENT" or "FLAT_TAX".
DEFAULT_CHOICE_LENGTH = 12


def choice_field(
    verbose_name: str,
    choices: type[models.TextChoices],
    max_length: int = DEFAULT_CHOICE_LENGTH,
    **kwargs,
) -> models.CharField:
    """
    Build a VARCHAR field restricted to a TextChoices class.

    Args:
        verbose_name: human-readable field name.
        choices: the TextChoices class with the allowed values.
        max_length: column length (DEFAULT_CHOICE_LENGTH by default).
        **kwargs: extra CharField options (default, ...).

    Returns:
        The CharField. Add the database check separately with
        choices_constraint() in the model's Meta.constraints.
    """
    return models.CharField(verbose_name, max_length=max_length, choices=choices.choices, **kwargs)


def choices_constraint(field: str, values, name: str) -> models.CheckConstraint:
    """
    Database check that a column only contains allowed values.

    Args:
        field: column name, e.g. "type".
        values: the allowed values (e.g. MyChoices.values).
        name: constraint name (may use "%(app_label)s" and "%(class)s").

    Returns:
        A CheckConstraint "field IN (values)".
    """
    return models.CheckConstraint(condition=Q(**{f"{field}__in": list(values)}), name=name)


def money_field(verbose_name: str, max_digits: int = 10, decimal_places: int = 2, **kwargs) -> models.DecimalField:
    """
    Build a field for an amount of money.

    Decimal is used instead of float to avoid rounding errors on amounts.

    Args:
        verbose_name: human-readable field name.
        max_digits: total digits (10 by default: max 99,999,999.99).
        decimal_places: digits after the decimal point (2 by default).
        **kwargs: extra DecimalField options (default, null, blank, ...).

    Returns:
        The DecimalField.
    """
    return models.DecimalField(verbose_name, max_digits=max_digits, decimal_places=decimal_places, **kwargs)


def positive_constraint(field: str, name: str) -> models.CheckConstraint:
    """
    Database check that a numeric column is greater than zero.

    Args:
        field: column name, e.g. "amount".
        name: constraint name (may use "%(app_label)s" and "%(class)s").

    Returns:
        A CheckConstraint "field > 0".
    """
    return models.CheckConstraint(condition=Q(**{f"{field}__gt": 0}), name=name)
