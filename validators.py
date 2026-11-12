"""
Generic normalizers for personal data.

Normalizing before validating and saving guarantees that unique constraints
and lookups treat equivalent spellings as the same value.
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
