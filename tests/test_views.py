"""
Tests for djkit.views (Django error views answering with JSON).

Run with: python manage.py test djkit.tests.test_views
"""

from django.test import RequestFactory, SimpleTestCase, override_settings

from djkit import views
from djkit.testing.api import ApiTestCase

# Project texts used to check that the views follow DJKIT_MESSAGES.
TEST_MESSAGES = {
    "csrf_failed": "Ricarica la pagina.",
    "bad_request": "Richiesta errata.",
    "forbidden": "Vietato.",
    "not_found": "Non trovato.",
    "server_error": "Errore del server.",
}


@override_settings(DJKIT_MESSAGES=TEST_MESSAGES)
class ErrorViewTests(SimpleTestCase):
    """Every error view answers {'detail': message} with its status."""

    def test_each_view_status_and_message(self):
        """csrf_failure 403, bad_request 400, permission_denied 403, page_not_found 404, server_error 500."""
        request = RequestFactory().get("/anything")
        cases = [
            (views.csrf_failure(request, reason="CSRF cookie not set."), 403, "Ricarica la pagina."),
            (views.bad_request(request), 400, "Richiesta errata."),
            (views.permission_denied(request), 403, "Vietato."),
            (views.page_not_found(request), 404, "Non trovato."),
            (views.server_error(request), 500, "Errore del server."),
        ]
        for response, status, detail in cases:
            with self.subTest(status=status, detail=detail):
                self.assertEqual(response.status_code, status)
                self.assertEqual(response["Content-Type"], "application/json")
                self.assertJSONEqual(response.content, {"detail": detail})


@override_settings(
    ROOT_URLCONF="djkit.tests.urls",
    CSRF_FAILURE_VIEW="djkit.views.csrf_failure",
    DJKIT_MESSAGES=TEST_MESSAGES,
)
class CsrfFailureViewTests(ApiTestCase):
    """With CSRF_FAILURE_VIEW set, csrf_protected endpoints reject with JSON."""

    def test_missing_token_on_public_endpoint_is_json_403(self):
        """POST /api/public/protected-echo without the token -> 403 {'detail': 'Ricarica la pagina.'}."""
        client = self.client_for(send_csrf_token=False)
        response = client.post("/api/public/protected-echo", {"name": "Anna"})
        self.assertStatus(response, 403)
        self.assertEqual(response.json(), {"detail": "Ricarica la pagina."})
