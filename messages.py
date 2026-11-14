"""
User-facing messages of djkit, looked up by key.

Every text that djkit may send to an end user (error details, per-field
errors, validator messages) has a key and an English default in
DEFAULT_MESSAGES. A project shows its own language by giving the texts in
the DJKIT_MESSAGES setting, {key: text}; keys it does not give keep the
English default.

    # settings.py
    DJKIT_MESSAGES = {"not_found": "Non trovato.", ...}

    get_message("not_found")                       # -> "Non trovato."
    get_message("string_too_short", min_length=3)  # placeholders filled in

Texts may contain str.format placeholders ({min_length}); missing values
leave the text unformatted rather than failing.
"""

from django.conf import settings

# Every user-facing message of djkit: key -> English default.
DEFAULT_MESSAGES: dict[str, str] = {
    # errors: default detail of each domain exception
    "domain_error": "Request failed.",
    "not_found": "Not found.",
    "conflict": "Conflict with the current state.",
    "invalid_data": "Invalid data.",
    "confirmation_required": "Confirmation required.",
    # db.ensure_unique / updates.apply_patch
    "unique": "This value is already used.",
    "field_not_editable": "This field cannot be changed.",
    # db.ensure_not_deleted
    "deleted_read_only": "This item has been deleted: it can only be consulted.",
    # audit: value of a masked field (DJKIT_AUDIT_MASKED_FIELDS)
    "audit_masked": "[hidden]",
    # auth
    "login_failed": "Invalid credentials.",
    "password_reset_invalid": "The password reset link is invalid or has expired: request a new one.",
    "password_too_short": "This password is too short: it must contain at least {min_length} characters.",
    "password_too_similar": "This password is too similar to your personal data.",
    # HTTP errors raised by the framework or by Django Ninja (api, views)
    "bad_request": "Bad request.",
    "unauthorized": "Authentication required.",
    "forbidden": "You are not allowed to perform this operation.",
    "csrf_failed": "Security check failed: reload the page and try again.",
    "method_not_allowed": "Method not allowed.",
    "too_many_requests": "Too many requests: try again later.",
    "server_error": "Internal server error.",
    # schema validation (Pydantic error types, see api.validation_message)
    "missing": "This field is required.",
    "invalid_value": "Invalid value.",
    "invalid_json": "The request body is not valid JSON.",
    "string_type": "Enter a text.",
    "string_too_short": "Enter at least {min_length} characters.",
    "string_too_long": "Enter at most {max_length} characters.",
    "list_too_short": "Enter at least {min_length} items.",
    # it.validate_tax_code
    "tax_code_invalid": "The tax code must contain {length} letters or digits.",
    "list_too_long": "Enter at most {max_length} items.",
    "number_type": "Enter a valid number.",
    "boolean_type": "Enter true or false.",
    "date_type": "Enter a valid date (YYYY-MM-DD).",
    "datetime_type": "Enter a valid date and time.",
    "greater_than": "Enter a value greater than {gt}.",
    "greater_than_equal": "Enter a value greater than or equal to {ge}.",
    "less_than": "Enter a value less than {lt}.",
    "less_than_equal": "Enter a value less than or equal to {le}.",
    "max_digits": "Enter at most {max_digits} digits.",
    "decimal_places": "Enter at most {decimal_places} decimal places.",
    "choice": "Value not allowed.",
    "list_type": "Enter a list of values.",
    "unknown_field": "This field is not accepted.",
    "object_type": "Enter an object.",
}


def configured_messages() -> dict[str, str]:
    """
    Messages given by the project.

    Returns:
        settings.DJKIT_MESSAGES, or {} when the setting is missing.
    """
    return getattr(settings, "DJKIT_MESSAGES", {}) or {}


def get_message(key: str, **params) -> str:
    """
    Text of a user-facing message, in the project's language.

    Args:
        key: a key of DEFAULT_MESSAGES (or a project-defined key present in
            DJKIT_MESSAGES).
        **params: values of the text's placeholders, e.g. min_length=8.

    Returns:
        The project's text (DJKIT_MESSAGES) or the English default, with the
        placeholders filled in; the bare text when a placeholder has no
        value.

    Raises:
        KeyError: unknown key (neither a default nor configured).
    """
    configured = configured_messages()
    text = configured[key] if key in configured else DEFAULT_MESSAGES[key]
    try:
        return text.format(**params)
    except (KeyError, IndexError, ValueError):
        return text


def missing_messages() -> list[str]:
    """
    Keys of DEFAULT_MESSAGES the project has not translated.

    Projects that must never show the English defaults assert in a test
    that this list is empty.

    Returns:
        The sorted missing keys.
    """
    configured = configured_messages()
    return sorted(key for key in DEFAULT_MESSAGES if key not in configured)
