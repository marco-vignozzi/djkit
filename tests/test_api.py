"""
Tests for djkit.api (error handlers, schemas) and djkit.testing.api
(ApiClient, make_user, ApiTestCase), through the test API of
djkit/tests/urls.py.

Run with: python manage.py test djkit.tests.test_api
"""

from django.conf import settings
from django.test import override_settings

from djkit.testing.api import ApiClient, ApiTestCase, make_user


@override_settings(ROOT_URLCONF="djkit.tests.urls")
class ErrorHandlerTests(ApiTestCase):
    """Domain errors become HTTP responses with an ErrorOut body."""

    def test_not_found_is_404_with_message(self):
        """NotFound('Invoice not found.') -> 404 {'detail': 'Invoice not found.'}."""
        response = self.client.get("/api/public/not-found")
        self.assertStatus(response, 404)
        self.assertEqual(response.json(), {"detail": "Invoice not found."})

    def test_conflict_is_409(self):
        """Conflict() -> 409 with the default message."""
        response = self.client.get("/api/public/conflict")
        self.assertStatus(response, 409)
        self.assertEqual(response.json()["detail"], "Conflict with the current state.")

    def test_invalid_data_is_422_with_field_errors(self):
        """InvalidData(errors=...) -> 422 with the errors."""
        response = self.client.get("/api/public/invalid")
        self.assertStatus(response, 422)
        self.assertEqual(response.json(), {"detail": "Check the fields.", "errors": {"email": ["Already used."]}})

    def test_django_validation_error_is_422(self):
        """A Django ValidationError raised by a service -> 422 with the field errors."""
        response = self.client.get("/api/public/validation")
        self.assertStatus(response, 422)
        self.assertEqual(response.json()["errors"], {"amount": ["Must be positive."]})

    def test_custom_status_for_project_error(self):
        """A DomainError subclass registered with 402 -> 402."""
        response = self.client.get("/api/public/payment-required")
        self.assertStatus(response, 402)
        self.assertEqual(response.json(), {"detail": "Upgrade your plan."})

    def test_confirmation_flow_428_then_204(self):
        """0 or 1 confirmation -> 428 with impact; 2 -> 204."""
        for given in (0, 1):
            with self.subTest(given=given):
                response = self.client.delete("/api/public/confirm", {"confirmations": given})
                self.assertStatus(response, 428)
                self.assertEqual(
                    response.json(),
                    {"detail": "Confirmation required.", "impact": {"invoices": 3}, "required": 2, "given": given},
                )
        self.assertStatus(self.client.delete("/api/public/confirm", {"confirmations": 2}), 204)

    def test_negative_confirmations_rejected_by_schema(self):
        """ConfirmationIn: confirmations -1 -> 422 from schema validation."""
        self.assertStatus(self.client.delete("/api/public/confirm", {"confirmations": -1}), 422)


@override_settings(ROOT_URLCONF="djkit.tests.urls")
class SessionAndCsrfTests(ApiTestCase):
    """ApiClient and ApiTestCase helpers against a session-protected endpoint."""

    def test_anonymous_request_is_401(self):
        """No login -> 401."""
        self.assertStatus(self.client.post("/api/echo", {"name": "x"}), 401)

    def test_logged_in_client_with_csrf_token_succeeds(self):
        """client_for(user) -> 200 with the user's pk and the JSON body echoed."""
        user = make_user()
        response = self.client_for(user).post("/api/echo", {"name": "Anna"})
        self.assertStatus(response, 200)
        self.assertEqual(response.json(), {"user": user.pk, "name": "Anna"})

    def test_request_without_csrf_token_is_rejected(self):
        """Logged in but without the CSRF header -> 403."""
        client = self.client_for(make_user(), send_csrf_token=False)
        self.assertStatus(client.post("/api/echo", {"name": "Anna"}), 403)

    def test_assert_not_accessible_expects_404(self):
        """assertNotAccessible passes on a 404 and fails on any other status."""
        client = ApiClient()
        self.assertNotAccessible(client, "get", "/api/public/not-found")
        with self.assertRaises(AssertionError):
            self.assertNotAccessible(client, "get", "/api/public/conflict")


@override_settings(ROOT_URLCONF="djkit.tests.urls")
class PublicCsrfTests(ApiTestCase):
    """sets_csrf_cookie and csrf_protected on public (auth=None) endpoints."""

    def test_csrf_endpoint_sets_the_cookie(self):
        """GET with no cookie -> 204 and a csrftoken cookie in the response."""
        client = ApiClient()
        client.cookies.clear()
        response = client.get("/api/public/csrf")
        self.assertStatus(response, 204)
        self.assertIn(settings.CSRF_COOKIE_NAME, response.cookies)

    def test_protected_public_endpoint_accepts_the_token(self):
        """Anonymous client with the CSRF header -> 200."""
        response = self.client_for().post("/api/public/protected-echo", {"name": "Anna"})
        self.assertStatus(response, 200)
        self.assertEqual(response.json(), {"name": "Anna"})

    def test_protected_public_endpoint_rejects_missing_token(self):
        """Anonymous client without the CSRF header -> 403."""
        client = self.client_for(send_csrf_token=False)
        self.assertStatus(client.post("/api/public/protected-echo", {"name": "Anna"}), 403)


class MakeUserTests(ApiTestCase):
    """make_user creates valid, unique users of the project's user model."""

    def test_users_are_unique_and_password_is_hashed(self):
        """Two users differ; the password is checkable and not stored in clear."""
        first, second = make_user(password="pw-1"), make_user()
        self.assertNotEqual(first.get_username(), second.get_username())
        self.assertTrue(first.check_password("pw-1"))
        self.assertNotEqual(first.password, "pw-1")

    def test_overrides_replace_placeholders(self):
        """first_name override -> stored as given."""
        user = make_user(first_name="Bruno")
        self.assertEqual(user.first_name, "Bruno")
