"""
Tests for djkit.views (Django error views answering with JSON).

Run with: python manage.py test djkit.tests.test_views
"""

import tempfile
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
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


@override_settings(ROOT_URLCONF="djkit.tests.urls", DJKIT_MESSAGES=TEST_MESSAGES, DEBUG=True)
class ApiCatchAllTests(ApiTestCase):
    """page_not_found as the catch-all after the API: JSON 404 under /api/ even with DEBUG on."""

    def test_unknown_api_path_is_json_404_with_debug_on(self):
        """GET and POST /api/public/missing (no endpoint) -> 404 {'detail': 'Non trovato.'}, not Django's HTML page."""
        client = self.client_for()
        for response in (client.get("/api/public/missing"), client.post("/api/public/missing/42", {})):
            with self.subTest(path=response.request["PATH_INFO"]):
                self.assertStatus(response, 404)
                self.assertEqual(response["Content-Type"], "application/json")
                self.assertEqual(response.json(), {"detail": "Non trovato."})

    def test_existing_endpoints_are_not_caught(self):
        """GET /api/public/conflict still reaches its endpoint (409)."""
        self.assertStatus(self.client_for().get("/api/public/conflict"), 409)


@override_settings(DJKIT_MESSAGES=TEST_MESSAGES)
class SpaIndexTests(SimpleTestCase):
    """spa_index serves the SPA index.html, fails loudly when it is missing."""

    def test_serves_the_index_file_without_cache(self):
        """An existing file -> 200 text/html with its bytes and Cache-Control no-cache."""
        with tempfile.TemporaryDirectory() as folder:
            index = Path(folder) / "index.html"
            index.write_text("<div id=root></div>", encoding="utf-8")
            with override_settings(DJKIT_SPA_INDEX=index):
                response = views.spa_index(RequestFactory().get("/properties/3"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/html; charset=utf-8")
        self.assertEqual(response["Cache-Control"], "no-cache")
        self.assertEqual(response.content, b"<div id=root></div>")

    def test_missing_file_answers_404_and_logs_an_error(self):
        """No build -> 404 {'detail': not_found} and an ERROR log line."""
        with override_settings(DJKIT_SPA_INDEX="/nonexistent/index.html"):
            with self.assertLogs("djkit.views", level="ERROR"):
                response = views.spa_index(RequestFactory().get("/"))
        self.assertEqual(response.status_code, 404)
        self.assertJSONEqual(response.content, {"detail": "Non trovato."})

    def test_missing_setting_raises_improperly_configured(self):
        """DJKIT_SPA_INDEX unset -> ImproperlyConfigured."""
        with override_settings():
            from django.conf import settings

            if hasattr(settings, "DJKIT_SPA_INDEX"):
                del settings.DJKIT_SPA_INDEX
            with self.assertRaises(ImproperlyConfigured):
                views.spa_index(RequestFactory().get("/"))
