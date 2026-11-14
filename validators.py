"""
Generic normalizers for personal data and text input.

Normalizing before validating and saving guarantees that unique constraints
and lookups treat equivalent spellings as the same value, and that a value
made only of spaces counts as empty for the model's validation.
"""


def normalize_email_address(value: str | None) -> str | None:
    """
    Bring an email address to its canonical form, so that uniqueness and
    login are case-insensitive ("Mario@Mail.com" == "mario@mail.com").

    Args:
        value: the raw email typed by the user (may be None).

    Returns:
        The value without surrounding spaces and in lowercase, or None if
        `value` is None.
    """
    return value.strip().lower() if value is not None else None


def strip_text_values(data: dict) -> dict:
    """
    Remove the spaces around every text value of a request, before model
    validation: "  " becomes "" and is rejected by a required field instead
    of being saved as a blank value.

    Args:
        data: {field: value}, e.g. the fields sent by the client.

    Returns:
        A copy with every str value stripped; other values (None, numbers,
        dates, nested data) unchanged.
    """
    return {name: value.strip() if isinstance(value, str) else value for name, value in data.items()}
