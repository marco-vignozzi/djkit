"""
Who is calling: the client address of a request, and a key that stands
for it without storing it.

    - client_address(request, proxy_count=0) -> str
        The address of the caller: REMOTE_ADDR, or, behind proxy_count
        reverse proxies that append to X-Forwarded-For, the address the
        outermost trusted proxy saw (never a value the client can forge).
    - client_key(request, proxy_count=0) -> str
        A keyed hash of that address (salted_hmac with SECRET_KEY): stable
        for the same client, useless to identify a person, so it can go in
        logs and audit entries for rate limits.
"""

from django.utils.crypto import salted_hmac

# Salt of client_key: changing it makes every stored key stale.
CLIENT_KEY_SALT = "djkit.clients.client_key"


def client_address(request, proxy_count: int = 0) -> str:
    """
    The address of the client of a request.

    Args:
        request: the HttpRequest.
        proxy_count: reverse proxies in front of the app, each appending
            the address it received the request from to X-Forwarded-For.

    Returns:
        REMOTE_ADDR when proxy_count is 0; otherwise the proxy_count-th
        address from the right of X-Forwarded-For (the leftmost ones may be
        forged by the client), REMOTE_ADDR when the header is shorter.
    """
    remote = request.META.get("REMOTE_ADDR", "")
    if proxy_count <= 0:
        return remote
    forwarded = [part.strip() for part in request.META.get("HTTP_X_FORWARDED_FOR", "").split(",") if part.strip()]
    return forwarded[-proxy_count] if len(forwarded) >= proxy_count else remote


def client_key(request, proxy_count: int = 0) -> str:
    """
    A stable, non-reversible key of the client address (client_address).

    Args:
        request: the HttpRequest.
        proxy_count: as in client_address.

    Returns:
        32 hex characters.
    """
    return salted_hmac(CLIENT_KEY_SALT, client_address(request, proxy_count)).hexdigest()[:32]
