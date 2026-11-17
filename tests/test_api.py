"""
Tests for djkit.api (error handlers, schemas) and djkit.testing.api
(ApiClient, make_user, ApiTestCase), through the test API of
djkit/tests/urls.py.

Run with: python manage.py test djkit.tests.test_api
"""

from django.contrib.auth import get_user_model
from django.conf import settings
from django.test import SimpleTestCase, override_settings

from djkit.api import NON_FIELD_ERRORS, error_field, validation_errors, validation_message
from djkit.testing.api import ApiClient, ApiTestCase, make_user


@override_settings(ROOT_URLCONF="djkit.tests.urls", DJKIT_MESSAGES={})
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

    def test_too_many_requests_is_429_with_retry_at(self):
        """TooManyRequests(retry_at) -> 429 with the default message and retry_at in ISO format."""
        response = self.client.get("/api/public/too-many")
        self.assertStatus(response, 429)
        self.assertEqual(
            response.json(),
            {"detail": "Too many requests: try again later.", "retry_at": "2030-01-01T12:00:00+00:00"},
        )

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


@override_settings(ROOT_URLCONF="djkit.tests.urls", DJKIT_MESSAGES={})
class NinjaErrorTests(ApiTestCase):
    """Errors produced by Django Ninja itself answer with ErrorOut and djkit messages."""

    def test_anonymous_request_gets_unauthorized_message(self):
        """No session -> 401 {'detail': 'Authentication required.'} (not Ninja's 'Unauthorized')."""
        response = self.client.post("/api/echo", {"name": "x"})
        self.assertStatus(response, 401)
        self.assertEqual(response.json(), {"detail": "Authentication required."})

    def test_session_csrf_failure_gets_csrf_message(self):
        """Logged in without the CSRF header -> 403 with the 'csrf_failed' message."""
        client = self.client_for(make_user(), send_csrf_token=False)
        response = client.post("/api/echo", {"name": "Anna"})
        self.assertStatus(response, 403)
        self.assertEqual(response.json(), {"detail": "Security check failed: reload the page and try again."})

    def test_schema_errors_are_per_field_messages(self):
        """name 'A' and age -1 -> 422 'Invalid data.' with one message on 'name' and one on 'age'."""
        response = self.client.post("/api/public/person", {"name": "A", "age": -1})
        self.assertStatus(response, 422)
        self.assertEqual(
            response.json(),
            {
                "detail": "Invalid data.",
                "errors": {
                    "name": ["Enter at least 2 characters."],
                    "age": ["Enter a value greater than or equal to 0."],
                },
            },
        )

    def test_missing_and_wrong_type_fields(self):
        """Body {'age': 'abc'} -> 'name' required, 'age' not a number."""
        response = self.client.post("/api/public/person", {"age": "abc"})
        self.assertStatus(response, 422)
        self.assertEqual(
            response.json()["errors"],
            {"name": ["This field is required."], "age": ["Enter a valid number."]},
        )

    def test_unknown_fields_are_rejected(self):
        """InputSchema: 'nickname' and 'agee' not declared -> 422 'This field is not accepted.' on each of them."""
        response = self.client.post("/api/public/person", {"name": "Anna", "age": 30, "nickname": "A", "agee": 3})
        self.assertStatus(response, 422)
        self.assertEqual(
            response.json()["errors"],
            {"nickname": ["This field is not accepted."], "agee": ["This field is not accepted."]},
        )

    def test_unknown_field_in_confirmation_body(self):
        """ConfirmationIn {'confirmation': 2} (typo) -> 422 on 'confirmation', not a 428 with 0 confirmations."""
        response = self.client.delete("/api/public/confirm", {"confirmation": 2})
        self.assertStatus(response, 422)
        self.assertEqual(response.json()["errors"], {"confirmation": ["This field is not accepted."]})

    def test_malformed_json_body(self):
        """Body 'not json' -> 400 {'detail': 'The request body is not valid JSON.'} (Ninja refuses to parse it)."""
        response = self.client.post("/api/public/person", "not json")
        self.assertStatus(response, 400)
        self.assertEqual(response.json(), {"detail": "The request body is not valid JSON."})

    def test_http404_inside_operation(self):
        """Http404('Technical message never shown.') -> 404 {'detail': 'Not found.'}."""
        response = self.client.get("/api/public/http404")
        self.assertStatus(response, 404)
        self.assertEqual(response.json(), {"detail": "Not found."})


class ValidationHelperTests(SimpleTestCase):
    """error_field and validation_message turn Pydantic errors into readable ones."""

    def test_error_field_drops_source_and_parameter(self):
        """('body','payload','email') -> 'email'; ('query','usable') -> 'usable'; nested -> dotted; ('body','payload') -> '__all__'."""
        self.assertEqual(error_field(("body", "payload", "email")), "email")
        self.assertEqual(error_field(("query", "usable")), "usable")
        self.assertEqual(error_field(("body", "payload", "items", 0, "amount")), "items.0.amount")
        self.assertEqual(error_field(("body", "payload")), NON_FIELD_ERRORS)

    @override_settings(DJKIT_MESSAGES={})
    def test_validation_message_by_type(self):
        """string_too_long with max_length 5 -> 'Enter at most 5 characters.'; unknown type -> 'Invalid value.'."""
        self.assertEqual(
            validation_message({"type": "string_too_long", "ctx": {"max_length": 5}}),
            "Enter at most 5 characters.",
        )
        self.assertEqual(validation_message({"type": "something_new"}), "Invalid value.")

    @override_settings(DJKIT_MESSAGES={})
    def test_empty_required_text_is_a_missing_field(self):
        """string_too_short min_length 1 -> 'This field is required.' (missing); min_length 3 -> 'Enter at least 3 characters.'."""
        self.assertEqual(validation_message({"type": "string_too_short", "ctx": {"min_length": 1}}), "This field is required.")
        self.assertEqual(
            validation_message({"type": "string_too_short", "ctx": {"min_length": 3}}), "Enter at least 3 characters."
        )

    @override_settings(DJKIT_MESSAGES={})
    def test_list_too_short_or_long_counts_items_not_characters(self):
        """too_short min_length 1 -> 'Enter at least 1 items.'; too_long max_length 3 -> 'Enter at most 3 items.'."""
        self.assertEqual(
            validation_message({"type": "too_short", "ctx": {"min_length": 1}}), "Enter at least 1 items."
        )
        self.assertEqual(validation_message({"type": "too_long", "ctx": {"max_length": 3}}), "Enter at most 3 items.")

    def test_value_error_keeps_validator_message(self):
        """value_error with ctx error ValueError('Data di fine prima dell'inizio.') -> that text."""
        error = {"type": "value_error", "ctx": {"error": ValueError("Data di fine prima dell'inizio.")}}
        self.assertEqual(validation_message(error), "Data di fine prima dell'inizio.")

    @override_settings(DJKIT_MESSAGES={})
    def test_validation_errors_groups_by_field(self):
        """Two errors on 'name' and one on 'age' -> {'name': [two], 'age': [one]}."""
        errors = [
            {"type": "missing", "loc": ("body", "payload", "name")},
            {"type": "string_type", "loc": ("body", "payload", "name")},
            {"type": "int_parsing", "loc": ("body", "payload", "age")},
        ]
        self.assertEqual(
            validation_errors(errors),
            {"name": ["This field is required.", "Enter a text."], "age": ["Enter a valid number."]},
        )


class MakeUserTests(ApiTestCase):
    """make_user creates valid, unique users of the project's user model."""

    def test_users_are_unique_and_password_is_hashed(self):
        """Two users differ; the password is checkable and not stored in clear."""
        first, second = make_user(password="pw-1"), make_user()
        self.assertNotEqual(first.get_username(), second.get_username())
        self.assertTrue(first.check_password("pw-1"))
        self.assertNotEqual(first.password, "pw-1")

    def test_overrides_replace_placeholders(self):
        """USERNAME_FIELD override "bruno@rentals-test.it" -> stored as given (whatever the user model)."""
        user = make_user(**{get_user_model().USERNAME_FIELD: "bruno@rentals-test.it"})
        self.assertEqual(user.get_username(), "bruno@rentals-test.it")


@override_settings(ROOT_URLCONF="djkit.tests.urls", DJKIT_MESSAGES={})
class UnknownQueryParamTests(ApiTestCase):
    """forbid_unknown_query_params (enabled by the test settings): undeclared query names -> 422 on each."""

    def test_declared_parameters_pass(self):
        """?color=red&tag=a&tag=b -> 200, echoed."""
        response = self.client.get("/api/public/filtered?color=red&tag=a&tag=b")
        self.assertStatus(response, 200)
        self.assertEqual(response.json(), {"color": "red", "tag": ["a", "b"]})

    def test_unknown_parameters_are_422_each_on_its_name(self):
        """?colour=red&x=1 -> 422 with errors on "colour" and "x"."""
        response = self.client.get("/api/public/filtered?colour=red&x=1")
        self.assertStatus(response, 422)
        self.assertEqual(response.json()["errors"], {"colour": ["This parameter is not accepted."], "x": ["This parameter is not accepted."]})

    def test_pagination_parameters_are_declared(self):
        """A paged endpoint: ?page=&size= accepted, ?limit= (Ninja's) refused."""
        self.assertStatus(self.client.get("/api/public/numbers?page=1&size=10"), 200)
        response = self.client.get("/api/public/numbers?limit=5")
        self.assertStatus(response, 422)
        self.assertIn("limit", response.json()["errors"])
