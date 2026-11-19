"""
Helpers for API tests.

    - ApiClient: Django test client that enforces CSRF like a real browser
      session and sends JSON bodies by default.
    - make_user: create a user of the project's user model with placeholder
      values for the required fields.
    - ApiTestCase: TestCase with client_for(user), assertStatus and
      assertNotAccessible (data isolation checks).
"""

from itertools import count

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import models
from django.test import Client, TestCase
from django.urls import Resolver404, resolve

from djkit.views import page_not_found
from django.utils.crypto import get_random_string

JSON = "application/json"

# Password given by make_user unless overridden.
DEFAULT_PASSWORD = "Test-pass-123!"

# Sequence giving each generated user unique placeholder values.
_user_sequence = count(1)


class ApiClient(Client):
    """
    Test client for JSON APIs protected by session authentication.

    CSRF checks are enforced (as for a real browser): the client stores a
    CSRF cookie and copies it into the CSRF header of every request, unless
    created with send_csrf_token=False (to test that requests without the
    token are rejected). post/put/patch/delete send `data` as JSON unless
    another content_type is given.
    """

    def __init__(self, *, send_csrf_token: bool = True, **kwargs):
        """
        Args:
            send_csrf_token: send the CSRF header on every request.
            **kwargs: forwarded to django.test.Client.
        """
        kwargs.setdefault("enforce_csrf_checks", True)
        super().__init__(**kwargs)
        self.send_csrf_token = send_csrf_token
        self.cookies[settings.CSRF_COOKIE_NAME] = get_random_string(32)

    def request(self, **request):
        """Add the CSRF header (from the cookie) before sending the request."""
        cookie = self.cookies.get(settings.CSRF_COOKIE_NAME)
        if self.send_csrf_token and cookie is not None:
            request.setdefault(settings.CSRF_HEADER_NAME, cookie.value)
        return super().request(**request)

    def post(self, path, data=None, content_type=JSON, **extra):
        """POST with a JSON body by default."""
        return super().post(path, data, content_type=content_type, **extra)

    def put(self, path, data=None, content_type=JSON, **extra):
        """PUT with a JSON body by default. No data -> empty body."""
        return super().put(path, "" if data is None else data, content_type=content_type, **extra)

    def patch(self, path, data=None, content_type=JSON, **extra):
        """PATCH with a JSON body by default. No data -> empty body."""
        return super().patch(path, "" if data is None else data, content_type=content_type, **extra)

    def delete(self, path, data=None, content_type=JSON, **extra):
        """DELETE with a JSON body by default (e.g. the confirmations). No data -> empty body."""
        return super().delete(path, "" if data is None else data, content_type=content_type, **extra)


def make_user(password: str = DEFAULT_PASSWORD, **overrides):
    """
    Create and save a user of the project's user model.

    USERNAME_FIELD and REQUIRED_FIELDS get unique placeholder values
    ("user<n>@example.com" for email fields, "user<n>" otherwise, cut to the
    field's max_length). Projects whose user model has stricter rules (check
    constraints, foreign keys among the required fields) pass `overrides`
    or use their own factories.

    Args:
        password: plain-text password (stored hashed).
        **overrides: field values replacing the placeholders.

    Returns:
        The saved user.
    """
    user_model = get_user_model()
    n = next(_user_sequence)
    values = {}
    for name in [user_model.USERNAME_FIELD, *user_model.REQUIRED_FIELDS]:
        field = user_model._meta.get_field(name)
        value = f"user{n}@example.com" if isinstance(field, models.EmailField) else f"user{n}"
        values[name] = value[: field.max_length] if field.max_length else value
    user = user_model(**{**values, **overrides})
    user.set_password(password)
    user.save()
    return user


class ApiTestCase(TestCase):
    """TestCase with helpers for JSON APIs protected by session authentication."""

    client_class = ApiClient

    def client_for(self, user=None, *, send_csrf_token: bool = True) -> ApiClient:
        """
        Build a client, logged in as `user` when given.

        Args:
            user: the user to log in, or None for an anonymous client.
            send_csrf_token: False to test that the API rejects requests
                without the CSRF token.

        Returns:
            A new ApiClient.
        """
        client = ApiClient(send_csrf_token=send_csrf_token)
        if user is not None:
            client.force_login(user)
        return client

    def assertStatus(self, response, status: int) -> None:
        """
        Assert the status code, showing the response body when it differs.

        Args:
            response: the test client response.
            status: expected HTTP status.
        """
        body = response.content.decode(errors="replace")[:1000]
        self.assertEqual(response.status_code, status, f"Unexpected status, body: {body}")

    def assertNotAccessible(self, client: ApiClient, method: str, path: str, data=None) -> None:
        """
        Assert that a request about someone else's object answers 404
        (never 403: the API must not reveal that the object exists).

        The path must match a route: a URL that no longer exists answers 404
        too (also through a catch-all djkit.views.page_not_found), and the
        test would pass without checking anything.

        Args:
            client: client of the user who must not access the object.
            method: "get", "post", "put", "patch" or "delete".
            path: URL of the object.
            data: optional body (query string for GET).
        """
        try:
            match = resolve(path.split("?", 1)[0])
        except Resolver404:
            match = None
        if match is None or match.func is page_not_found:
            self.fail(f"{path} matches no route: the 404 would not prove anything")
        response = getattr(client, method.lower())(path, data)
        self.assertStatus(response, 404)
