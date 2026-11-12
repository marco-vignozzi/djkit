"""
URL configuration used only by djkit's API tests
(@override_settings(ROOT_URLCONF="djkit.tests.urls")).

A small NinjaAPI with session authentication and the djkit error handlers:
each endpoint raises one kind of error or echoes the request.
"""

from django.core.exceptions import ValidationError
from django.urls import path
from ninja import NinjaAPI, Schema
from ninja.security import django_auth

from djkit.api import ConfirmationIn, csrf_protected, register_error_handlers, sets_csrf_cookie
from djkit.auth import login_with_password
from djkit.errors import Conflict, DomainError, InvalidData, NotFound, require_confirmation


class PaymentRequired(DomainError):
    """Project-specific error registered with a custom status (402)."""


class NameIn(Schema):
    """Body of the echo endpoint."""

    name: str


class CredentialsIn(Schema):
    """Body of the test login endpoint."""

    username: str
    password: str


api =NinjaAPI(urls_namespace="djkit-tests", auth=django_auth)
register_error_handlers(api, {PaymentRequired: 402})


@api.get("/public/not-found", auth=None)
def not_found(request):
    """Always 404 with a custom message."""
    raise NotFound("Invoice not found.")


@api.get("/public/conflict", auth=None)
def conflict(request):
    """Always 409 with the default message."""
    raise Conflict()


@api.get("/public/invalid", auth=None)
def invalid(request):
    """Always 422 with per-field errors."""
    raise InvalidData("Check the fields.", errors={"email": ["Already used."]})


@api.get("/public/validation", auth=None)
def validation(request):
    """Django ValidationError tied to a field -> 422."""
    raise ValidationError({"amount": ["Must be positive."]})


@api.get("/public/payment-required", auth=None)
def payment_required(request):
    """Custom DomainError subclass -> 402."""
    raise PaymentRequired("Upgrade your plan.")


@api.delete("/public/confirm", auth=None, response={204: None})
def confirm(request, payload: ConfirmationIn):
    """428 until two confirmations are sent, then 204."""
    require_confirmation(payload.confirmations, 2, {"invoices": 3})
    return 204, None


@api.post("/echo", response={200: dict})
def echo(request, payload: NameIn):
    """Logged-in only (session + CSRF): returns the user's pk and the name."""
    return {"user": request.user.pk, "name": payload.name}


@api.get("/public/csrf", auth=None, response={204: None})
@sets_csrf_cookie
def csrf(request):
    """Public: always sets the CSRF cookie, 204."""
    return 204, None


@api.post("/public/protected-echo", auth=None, response={200: dict})
@csrf_protected
def protected_echo(request, payload: NameIn):
    """Public but CSRF-protected: echoes the name (403 without the token)."""
    return {"name": payload.name}


@api.post("/public/login", auth=None, response={200: dict})
@csrf_protected
def login(request, payload: CredentialsIn):
    """Public login with login_with_password: returns the user's pk (422 on wrong credentials)."""
    user = login_with_password(request, payload.username, payload.password)
    return {"user": user.pk}


urlpatterns = [path("api/", api.urls)]
