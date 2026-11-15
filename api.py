"""
Django Ninja integration.

    - ErrorOut: body of every error response produced by the handlers.
    - InputSchema: base of request bodies; a field the schema does not
      declare is rejected (422 "unknown_field") instead of being silently
      ignored, so a client that sends a wrong or misspelled field finds out.
    - ConfirmationIn: body of destructive requests (number of confirmations).
    - register_error_handlers(api): maps the djkit.errors exceptions, Django's
      ValidationError and the errors produced by Django Ninja itself (401,
      403 CSRF, 404, schema validation 422, 429) to ErrorOut responses whose
      texts come from djkit.messages, so no English default of Ninja or
      Pydantic reaches the user.
    - validation_errors(errors): Ninja/Pydantic validation errors ->
      {"field": [message]}.
    - csrf_protected / sets_csrf_cookie: operation decorators for public
      endpoints (auth=None) of a session-based API.

Typical setup:

    api = NinjaAPI(auth=django_auth)   # django_auth already enforces CSRF
    register_error_handlers(api)

    @api.get("/csrf", auth=None, response={204: None})
    @sets_csrf_cookie                  # the client reads the csrftoken cookie
    def csrf(request): ...

    @api.post("/login", auth=None)
    @csrf_protected                    # auth=None skips Ninja's CSRF check
    def login(request, payload: LoginIn): ...
"""

from django.core.exceptions import ValidationError
from django.http import Http404
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from ninja import Field, NinjaAPI, Schema
from ninja import errors as ninja_errors
from ninja.decorators import decorate_view
from pydantic import ConfigDict

from .errors import Conflict, ConfirmationRequired, DomainError, InvalidData, NotFound, TooManyRequests
from .messages import get_message

# Default HTTP status of each domain exception. Subclasses inherit the status
# of their closest registered ancestor (Ninja looks handlers up along the MRO).
DEFAULT_STATUS_CODES: dict[type[DomainError], int] = {
    DomainError: 400,
    NotFound: 404,
    Conflict: 409,
    InvalidData: 422,
    ConfirmationRequired: 428,
    TooManyRequests: 429,
}


# Message key (djkit.messages) of each HTTP status raised by Django Ninja as
# an HttpError; statuses not listed use "domain_error".
HTTP_ERROR_MESSAGE_KEYS: dict[int, str] = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    429: "too_many_requests",
}

# Message Django Ninja's session authentication uses for a failed CSRF check
# (ninja.security.APIKeyCookie); recognized to answer with "csrf_failed".
NINJA_CSRF_FAILED_MESSAGE = "CSRF check Failed"

# Start of the message Django Ninja uses when the request body cannot be
# parsed (400; with DEBUG on the parser's error follows in parentheses);
# recognized to answer with "invalid_json".
NINJA_BODY_PARSE_MESSAGE = "Cannot parse request body"

# Message key (djkit.messages) of each Pydantic error type. Types not listed
# use "invalid_value"; "value_error" (a custom validator raising ValueError)
# keeps the validator's own message.
VALIDATION_MESSAGE_KEYS: dict[str, str] = {
    "missing": "missing",
    "json_invalid": "invalid_json",
    "string_type": "string_type",
    "string_too_short": "string_too_short",
    "string_too_long": "string_too_long",
    # Lists (and other collections): items, not characters.
    "too_short": "list_too_short",
    "too_long": "list_too_long",
    "int_type": "number_type",
    "int_parsing": "number_type",
    "int_from_float": "number_type",
    "float_type": "number_type",
    "float_parsing": "number_type",
    "decimal_type": "number_type",
    "decimal_parsing": "number_type",
    "finite_number": "number_type",
    "bool_type": "boolean_type",
    "bool_parsing": "boolean_type",
    "date_type": "date_type",
    "date_parsing": "date_type",
    "date_from_datetime_parsing": "date_type",
    "date_from_datetime_inexact": "date_type",
    "datetime_type": "datetime_type",
    "datetime_parsing": "datetime_type",
    "datetime_from_date_parsing": "datetime_type",
    "greater_than": "greater_than",
    "greater_than_equal": "greater_than_equal",
    "less_than": "less_than",
    "less_than_equal": "less_than_equal",
    "decimal_max_digits": "max_digits",
    "decimal_whole_digits": "max_digits",
    "decimal_max_places": "decimal_places",
    "literal_error": "choice",
    "enum": "choice",
    "list_type": "list_type",
    "dict_type": "object_type",
    "model_type": "object_type",
    "model_attributes_type": "object_type",
    "extra_forbidden": "unknown_field",
}

# First items of a Ninja error location that name where the value came from;
# for request bodies the next item is the view's parameter name (e.g.
# ("body", "payload", "email")), which is dropped too.
LOCATION_SOURCES = {"body": 2, "form": 2, "file": 2, "query": 1, "path": 1, "header": 1, "cookie": 1}

# Key of the errors not tied to a field (same convention as Django forms).
NON_FIELD_ERRORS = "__all__"


# Operation decorator enforcing Django's CSRF check. Needed on public unsafe
# endpoints (auth=None) such as login or registration: Ninja checks the CSRF
# token only inside session authentication (django_auth), so without it these
# endpoints would accept cross-site requests (login CSRF). Missing or wrong
# token -> 403.
csrf_protected = decorate_view(csrf_protect)

# Operation decorator that always sends the CSRF cookie in the response, so a
# single-page client can read it and send it back in the CSRF header.
sets_csrf_cookie = decorate_view(ensure_csrf_cookie)


class ErrorOut(Schema):
    """
    Body of an error response.

    Fields:
        detail   -> user-facing message (always present).
        errors   -> per-field messages, {"field": ["message", ...]} (422).
        impact   -> what a destructive operation would remove (428).
        required -> confirmations needed (428).
        given    -> confirmations received (428).
        retry_at -> from when the operation is allowed again (429 of
                    TooManyRequests; ISO timestamp).
    """

    detail: str
    errors: dict[str, list[str]] | None = None
    impact: dict | None = None
    required: int | None = None
    given: int | None = None
    retry_at: str | None = None


class InputSchema(Schema):
    """
    Base class of request body schemas: fields not declared by the schema
    are rejected with a 422 on that field (message key "unknown_field"),
    e.g. {"pasword": "..."} or a field that cannot be changed through this
    endpoint. Without it Pydantic would drop them silently and the client
    would believe the value was accepted.

    Response schemas keep inheriting ninja.Schema.
    """

    model_config = ConfigDict(extra="forbid")


class ConfirmationIn(InputSchema):
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

    Responses (body always ErrorOut):
        - every DomainError -> `exc.payload()` with its status;
        - Django's ValidationError -> 422 of InvalidData.from_validation_error;
        - Ninja's schema ValidationError -> 422, detail "invalid_data" and
          per-field errors from validation_errors();
        - Ninja's HttpError (AuthenticationError 401, CSRF failure 403,
          Throttled 429, unparsable body 400, ...) -> its status with the
          message of http_error_message();
        - Http404 raised inside an operation -> 404 "not_found".
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

    def ninja_validation_handler(request, exc: ninja_errors.ValidationError):
        payload = InvalidData(errors=validation_errors(exc.errors)).payload()
        return api.create_response(request, payload, status=codes[InvalidData])

    api.add_exception_handler(ninja_errors.ValidationError, ninja_validation_handler)

    def http_error_handler(request, exc: ninja_errors.HttpError):
        return api.create_response(request, {"detail": http_error_message(exc)}, status=exc.status_code)

    api.add_exception_handler(ninja_errors.HttpError, http_error_handler)

    def not_found_handler(request, exc: Http404):
        return api.create_response(request, {"detail": get_message("not_found")}, status=404)

    api.add_exception_handler(Http404, not_found_handler)


def http_error_message(exc: ninja_errors.HttpError) -> str:
    """
    User-facing message of an HttpError raised by Django Ninja.

    Args:
        exc: the HttpError (Ninja's messages are fixed English texts such as
            "Unauthorized", never shown as they are).

    Returns:
        "csrf_failed" for Ninja's CSRF failure, "invalid_json" for a body
        Ninja cannot parse, otherwise the message of HTTP_ERROR_MESSAGE_KEYS
        for the status ("domain_error" for unlisted statuses).
    """
    if exc.status_code == 403 and exc.message == NINJA_CSRF_FAILED_MESSAGE:
        return get_message("csrf_failed")
    if exc.status_code == 400 and str(exc.message).startswith(NINJA_BODY_PARSE_MESSAGE):
        return get_message("invalid_json")
    return get_message(HTTP_ERROR_MESSAGE_KEYS.get(exc.status_code, "domain_error"))


def error_field(loc) -> str:
    """
    Field name of a Ninja / Pydantic error location.

    Args:
        loc: the error's "loc", e.g. ("body", "payload", "email"),
            ("query", "usable") or ("body", "payload", "items", 0, "amount").

    Returns:
        The field path without the source and parameter name, joined with
        dots ("email", "usable", "items.0.amount"); NON_FIELD_ERRORS when
        nothing is left (e.g. a malformed body).
    """
    parts = [str(part) for part in (loc or ())]
    if parts and parts[0] in LOCATION_SOURCES:
        parts = parts[LOCATION_SOURCES[parts[0]] :]
    return ".".join(parts) or NON_FIELD_ERRORS


def validation_message(error: dict) -> str:
    """
    User-facing message of one Pydantic validation error.

    Args:
        error: one item of Ninja's ValidationError.errors ({"type", "loc",
            "msg", "ctx"?}).

    Returns:
        The message of VALIDATION_MESSAGE_KEYS for the error type, with the
        placeholders filled from "ctx" (e.g. {min_length}); for "value_error"
        the custom validator's own message; "invalid_value" otherwise.
    """
    error_type = error.get("type", "")
    ctx = error.get("ctx") or {}
    if error_type == "value_error" and ctx.get("error") is not None:
        return str(ctx["error"])
    return get_message(VALIDATION_MESSAGE_KEYS.get(error_type, "invalid_value"), **ctx)


def validation_errors(errors: list[dict]) -> dict[str, list[str]]:
    """
    Convert Ninja / Pydantic validation errors into per-field messages.

    Args:
        errors: Ninja's ValidationError.errors.

    Returns:
        {"field": [message, ...]} in the order the errors were reported
        (see error_field and validation_message).
    """
    result: dict[str, list[str]] = {}
    for error in errors:
        result.setdefault(error_field(error.get("loc")), []).append(validation_message(error))
    return result
