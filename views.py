"""
Django error views answering with a JSON ErrorOut body.

Django answers some errors outside any API framework, with HTML pages whose
texts may not be in the user's language: a failed CSRF check of
`csrf_protect` (e.g. djkit.api.csrf_protected) and, with DEBUG off, the 400,
403, 404 and 500 pages. These views answer {"detail": message} instead, with
the texts of djkit.messages.

    # settings.py
    CSRF_FAILURE_VIEW = "djkit.views.csrf_failure"

    # urls.py (root URLconf)
    handler400 = "djkit.views.bad_request"
    handler403 = "djkit.views.permission_denied"
    handler404 = "djkit.views.page_not_found"
    handler500 = "djkit.views.server_error"

With DEBUG on, Django keeps showing its technical 404 / 500 pages. To get
the JSON 404 under an API prefix in every mode, add `page_not_found` as a
catch-all route after the API (a path no API route matches ends there):

    urlpatterns = [path("api/", api.urls), re_path(r"^api/", page_not_found)]

`spa_index` serves the index.html of a single-page application build for
every other path, so client-side routes survive a page reload:

    # settings.py
    DJKIT_SPA_INDEX = BASE_DIR / "frontend" / "dist" / "index.html"
    # urls.py, last route
    re_path(r"^", spa_index)
"""

import logging
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.http import HttpResponse, JsonResponse

logger = logging.getLogger(__name__)

from .messages import get_message


def error_response(key: str, status: int) -> JsonResponse:
    """
    JSON error response with a djkit message.

    Args:
        key: message key (djkit.messages).
        status: HTTP status.

    Returns:
        JsonResponse {"detail": message} with the given status.
    """
    return JsonResponse({"detail": get_message(key)}, status=status)


def csrf_failure(request, reason: str = "") -> JsonResponse:
    """
    View for CSRF_FAILURE_VIEW: 403 with the "csrf_failed" message.

    Args:
        request: the rejected request.
        reason: Django's technical reason (English, not shown to the user).

    Returns:
        403 {"detail": ...}.
    """
    return error_response("csrf_failed", 403)


def bad_request(request, exception=None) -> JsonResponse:
    """handler400: 400 with the "bad_request" message."""
    return error_response("bad_request", 400)


def permission_denied(request, exception=None) -> JsonResponse:
    """handler403: 403 with the "forbidden" message."""
    return error_response("forbidden", 403)


def page_not_found(request, exception=None) -> JsonResponse:
    """handler404: 404 with the "not_found" message."""
    return error_response("not_found", 404)


def server_error(request) -> JsonResponse:
    """handler500: 500 with the "server_error" message."""
    return error_response("server_error", 500)


def spa_index(request) -> HttpResponse:
    """
    Catch-all view: the index.html of the single-page application build.

    The file is read on every request (it is small), so a new build is
    served without restarting the server; `Cache-Control: no-cache` makes
    browsers check for a new version, while the hashed assets it links stay
    cacheable.

    Args:
        request: any request no other route matched.

    Returns:
        200 text/html with the file, or 404 {"detail": ...} ("not_found")
        when the file does not exist (the error is logged: the build is
        missing).

    Raises:
        ImproperlyConfigured: DJKIT_SPA_INDEX is not set.
    """
    index = getattr(settings, "DJKIT_SPA_INDEX", None)
    if index is None:
        raise ImproperlyConfigured("DJKIT_SPA_INDEX must point to the index.html of the SPA build.")
    path = Path(index)
    if not path.is_file():
        logger.error("SPA index not found at %s: build the frontend first.", path)
        return error_response("not_found", 404)
    response = HttpResponse(path.read_bytes(), content_type="text/html; charset=utf-8")
    response["Cache-Control"] = "no-cache"
    return response
