"""
Italian helpers.

    - Tax code ("codice fiscale"): validate_tax_code (TaxCodeValidator),
      normalize_tax_code. With dev.relaxed_validation() on, a tax code may
      be shorter (1 to 16 letters or digits). The same rules are meant to be reused by models, admin forms and API
      schemas, so a tax code is validated identically everywhere.
    - Formatting of the values put inside Italian texts: format_date
      ("15/03/2026"), format_amount ("1.234,50"), format_percent ("33,33"),
      format_names ("Anna, Bruno e Carla"). A frontend formatting with Intl
      in it-IT gets the same result.
"""

from datetime import date
from decimal import Decimal

import re

from django.core.exceptions import ValidationError
from django.utils.deconstruct import deconstructible
from django.utils.functional import lazy

from .dev import relaxed_validation
from .messages import get_message

# The message is looked up when shown, so the project's text applies
# (message key "tax_code_invalid").
_lazy_message = lazy(get_message, str)

# Length of an Italian tax code ("codice fiscale").
TAX_CODE_LENGTH = 16

# Exactly 16 uppercase letters or digits (values are normalized to uppercase
# before being validated, see normalize_tax_code); 1 to 16 with relaxed
# validation (development only).
TAX_CODE_PATTERN = re.compile(rf"^[A-Z0-9]{{{TAX_CODE_LENGTH}}}$")
RELAXED_TAX_CODE_PATTERN = re.compile(rf"^[A-Z0-9]{{1,{TAX_CODE_LENGTH}}}$")


@deconstructible(path="djkit.it.TaxCodeValidator")
class TaxCodeValidator:
    """
    Validator of an Italian tax code (format only, no check character).

    Raises ValidationError (code "invalid_tax_code", message key
    "tax_code_invalid") when the value does not match TAX_CODE_PATTERN, or
    RELAXED_TAX_CODE_PATTERN with dev.relaxed_validation() on.
    """

    def __call__(self, value) -> None:
        """
        Validate one value.

        Args:
            value: the (normalized) tax code.

        Raises:
            ValidationError: the value is not a valid tax code.
        """
        pattern = RELAXED_TAX_CODE_PATTERN if relaxed_validation() else TAX_CODE_PATTERN
        if not isinstance(value, str) or not pattern.match(value):
            raise ValidationError(_lazy_message("tax_code_invalid", length=TAX_CODE_LENGTH), code="invalid_tax_code")

    def __eq__(self, other) -> bool:
        """All instances are equal (no options), so migrations stay stable."""
        return isinstance(other, TaxCodeValidator)

    def __hash__(self) -> int:
        """Hash consistent with __eq__."""
        return hash(TaxCodeValidator)


# The validator used by models, admin forms and API schemas.
validate_tax_code = TaxCodeValidator()


def normalize_tax_code(value: str | None) -> str | None:
    """
    Bring a tax code to its canonical form, so that "rssmra..." and
    " RSSMRA... " are treated as the same value by unique constraints.

    Args:
        value: the raw tax code typed by the user (may be None).

    Returns:
        The value without surrounding spaces and in uppercase, or None if
        `value` is None.
    """
    return value.strip().upper() if value is not None else None


def format_date(value: date) -> str:
    """
    A date as the interface shows it.

    Args:
        value: the date.

    Returns:
        "15/03/2026".
    """
    return value.strftime("%d/%m/%Y")


def format_amount(value: Decimal) -> str:
    """
    An amount in euro as the interface shows it, without the symbol.

    Args:
        value: the amount.

    Returns:
        "1.234,50" (thousands with a dot, two decimals after a comma).
    """
    whole, cents = f"{Decimal(value):,.2f}".split(".")
    return f"{whole.replace(',', '.')},{cents}"


def format_percent(value: Decimal) -> str:
    """
    A percentage as the interface shows it, without the symbol and without
    useless zeros.

    Args:
        value: e.g. Decimal("50.00"), Decimal("33.33"), Decimal("21").

    Returns:
        "50", "33,33", "21".
    """
    plain = f"{Decimal(value):f}"
    if "." in plain:
        plain = plain.rstrip("0").rstrip(".")
    return plain.replace(".", ",")


def format_names(names) -> str:
    """
    A list of names as a sentence shows it.

    Args:
        names: the names, in order.

    Returns:
        "Anna", "Anna e Bruno", "Anna, Bruno e Carla" ("" when empty).
    """
    names = list(names)
    if len(names) <= 1:
        return "".join(names)
    return f"{', '.join(names[:-1])} e {names[-1]}"
