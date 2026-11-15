"""
Domain exceptions and confirmation of destructive operations.

Services raise these exceptions without knowing anything about HTTP;
djkit.api.register_error_handlers translates them into responses
(NotFound -> 404, Conflict -> 409, InvalidData -> 422,
ConfirmationRequired -> 428, TooManyRequests -> 429).

Every exception carries a user-facing `detail` message and optional extra
data that ends up in the response body next to it (see payload()). When no
message is given, `detail` is the text of the class's `message_key` in
djkit.messages (English by default, the project's language through the
DJKIT_MESSAGES setting).
"""

from django.core.exceptions import NON_FIELD_ERRORS, ValidationError

from .messages import get_message


class DomainError(Exception):
    """
    Base class of the domain exceptions.

    Attributes:
        message_key: key (djkit.messages) of the message used when none is
            given.
        detail: user-facing message.
        extra: additional JSON-serializable data for the response body.
    """

    message_key = "domain_error"

    def __init__(self, detail: str | None = None, **extra):
        """
        Args:
            detail: user-facing message; the text of message_key when
                omitted.
            **extra: additional data for the response body (None values are
                dropped), e.g. errors={"email": ["Already used."]}.
        """
        self.detail = detail or get_message(self.message_key)
        self.extra = {key: value for key, value in extra.items() if value is not None}
        super().__init__(self.detail)

    def payload(self) -> dict:
        """
        Body of the HTTP response for this error.

        Returns:
            {"detail": ..., **extra}.
        """
        return {"detail": self.detail, **self.extra}


class NotFound(DomainError):
    """
    The object does not exist, or the user may not access it: the two cases
    are deliberately indistinguishable, so the API never reveals that an
    object of another user exists.
    """

    message_key = "not_found"


class Conflict(DomainError):
    """The request conflicts with the current state (value already used, read-only object, ...)."""

    message_key = "conflict"


class InvalidData(DomainError):
    """
    A business rule not covered by the input schema is violated.

    Pass `errors={"field": ["message", ...]}` to point at specific fields.
    """

    message_key = "invalid_data"

    @classmethod
    def from_validation_error(cls, error: ValidationError, field_prefix: str = "") -> "InvalidData":
        """
        Convert a Django ValidationError (from full_clean, a validator, ...).

        Args:
            error: the ValidationError.
            field_prefix: prefix of the field names, for an object that is
                part of a larger request body (e.g. "customer." ->
                "customer.email"); its non-field messages go under the
                prefix without the final dot ("customer"). "" keeps the
                names as they are.

        Returns:
            InvalidData with `errors={"field": [messages]}` when the error is
            tied to fields (non-field messages under "__all__", or under the
            prefix), otherwise with the messages joined in `detail`.
        """
        if hasattr(error, "error_dict"):
            errors = {
                prefixed_field(field, field_prefix): [str(message) for message in messages]
                for field, messages in error.message_dict.items()
            }
            return cls(errors=errors)
        return cls(" ".join(str(message) for message in error.messages) or None)


class ConfirmationRequired(DomainError):
    """
    A destructive operation has not been confirmed enough times yet.

    The response tells the client what would be lost (`impact`), how many
    confirmations are needed (`required`) and how many were given (`given`),
    so it can ask the user and repeat the request.
    """

    message_key = "confirmation_required"

    def __init__(self, impact: dict, required: int, given: int, detail: str | None = None):
        """
        Args:
            impact: summary of what would be lost, e.g. {"invoices": 12}.
            required: number of confirmations needed.
            given: number of confirmations received.
            detail: user-facing message; the text of message_key when
                omitted.
        """
        super().__init__(detail, impact=impact, required=required, given=given)
        self.impact = impact
        self.required = required
        self.given = given


class TooManyRequests(DomainError):
    """
    The same operation was repeated too soon (e.g. a second email to the
    same recipient within the cooldown, see djkit.audit.ensure_cooldown).

    The response carries `retry_at` (ISO timestamp): from then on the
    operation is allowed again, so the client can say when to retry.
    """

    message_key = "too_many_requests"

    def __init__(self, retry_at, detail: str | None = None):
        """
        Args:
            retry_at: aware datetime from which the operation is allowed.
            detail: user-facing message; the text of message_key when
                omitted.
        """
        super().__init__(detail, retry_at=retry_at.isoformat())
        self.retry_at = retry_at


def require_confirmation(given: int, required: int, impact: dict, detail: str | None = None) -> None:
    """
    Stop a destructive operation until it has been confirmed enough times.

    Args:
        given: confirmations sent by the client (ConfirmationIn.confirmations).
        required: confirmations needed (e.g. 1, or 2 when data with economic
            value would be lost).
        impact: summary of what would be lost, shown to the user.
        detail: optional user-facing message.

    Raises:
        ConfirmationRequired: while given < required.
    """
    if given < required:
        raise ConfirmationRequired(impact=impact, required=required, given=given, detail=detail)


def prefixed_field(field: str, prefix: str) -> str:
    """
    Name of a field of an object nested in a request body.

    Args:
        field: the field name, or NON_FIELD_ERRORS ("__all__").
        prefix: e.g. "customer."; "" for no prefix.

    Returns:
        "customer.email" for a field; "customer" for NON_FIELD_ERRORS (or
        "__all__" again when there is no prefix).
    """
    if not prefix:
        return field
    if field == NON_FIELD_ERRORS:
        return prefix.rstrip(".")
    return f"{prefix}{field}"
