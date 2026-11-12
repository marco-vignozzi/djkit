"""
Django Ninja integration.

    - ErrorOut: body of every error response produced by the handlers.
    - ConfirmationIn: body of destructive requests (number of confirmations).
    - register_error_handlers(api): maps the djkit.errors exceptions (and
      Django's ValidationError) to HTTP responses.

Typical setup:

    api = NinjaAPI(auth=django_auth)   # django_auth already enforces CSRF
    register_error_handlers(api)
"""

from django.core.exceptions import ValidationError
from ninja import Field, NinjaAPI, Schema

from .errors import Conflict, ConfirmationRequired, DomainError, InvalidData, NotFound

# Default HTTP status of each domain exception. Subclasses inherit the status
# of their closest registered ancestor (Ninja looks handlers up along the MRO).
DEFAULT_STATUS_CODES: dict[type[DomainError], int] = {
    DomainError: 400,
    NotFound: 404,
    Conflict: 409,
    InvalidData: 422,
    ConfirmationRequired: 428,
}


class ErrorOut(Schema):
    """
    Body of an error response.

    Fields:
        detail   -> user-facing message (always present).
        errors   -> per-field messages, {"field": ["message", ...]} (422).
        impact   -> what a destructive operation would remove (428).
        required -> confirmations needed (428).
        given    -> confirmations received (428).
    """

    detail: str
    errors: dict[str, list[str]] | None = None
    impact: dict | None = None
    required: int | None = None
    given: int | None = None


class ConfirmationIn(Schema):
    """
    Body of a destructive request (e.g. DELETE).

    Fields:
        confirmations -> how many times the user confirmed (0 or more); the
                         service compares it with the number required.
    """

    confirmations: int = Field(0, ge=0)


def register_error_handlers(api: NinjaAPI, status_codes: dict[type[DomainError], int] | None = None) -> None:
    """
    Register the exception handlers of the domain errors on a NinjaAPI.

    Args:
        api: the NinjaAPI instance.
        status_codes: extra or overriding {exception class: HTTP status},
            merged over DEFAULT_STATUS_CODES (e.g. {PaymentRequired: 402}
            for a project-specific DomainError subclass).

    Every DomainError produces `exc.payload()` with its status; Django's
    ValidationError produces the 422 of InvalidData.from_validation_error.
    """
    codes = {**DEFAULT_STATUS_CODES, **(status_codes or {})}

    def make_handler(status: int):
        """Build the handler that answers with `status` and the error payload."""

        def handler(request, exc: DomainError):
            return api.create_response(request, exc.payload(), status=status)

        return handler

    for exception_class, status in codes.items():
        api.add_exception_handler(exception_class, make_handler(status))

    def validation_handler(request, exc: ValidationError):
        payload = InvalidData.from_validation_error(exc).payload()
        return api.create_response(request, payload, status=codes[InvalidData])

    api.add_exception_handler(ValidationError, validation_handler)
