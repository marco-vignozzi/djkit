"""
Italian personal data: tax code ("codice fiscale").

The same rules are meant to be reused by models, admin forms and API
schemas, so a tax code is validated identically everywhere.
"""

from django.core.validators import RegexValidator

# Length of an Italian tax code ("codice fiscale").
TAX_CODE_LENGTH = 16

# Accepts exactly 16 uppercase letters or digits (values are normalized to
# uppercase before being validated, see normalize_tax_code).
validate_tax_code = RegexValidator(
    regex=rf"^[A-Z0-9]{{{TAX_CODE_LENGTH}}}$",
    message=f"Il codice fiscale deve contenere {TAX_CODE_LENGTH} lettere o cifre.",
    code="invalid_tax_code",
)


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
