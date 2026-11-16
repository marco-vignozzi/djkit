"""
Tests of djkit.clients: the client address behind proxies and its key.

Run with: python manage.py test djkit.tests.test_clients
"""

from django.test import RequestFactory, SimpleTestCase

from djkit.clients import client_address, client_key


class ClientAddressTests(SimpleTestCase):
    """client_address(): REMOTE_ADDR, or the address seen by the outermost trusted proxy."""

    def request(self, forwarded=None):
        """A request from 10.0.0.1 (the proxy), with an optional X-Forwarded-For."""
        extra = {"HTTP_X_FORWARDED_FOR": forwarded} if forwarded is not None else {}
        return RequestFactory().get("/", REMOTE_ADDR="10.0.0.1", **extra)

    def test_without_proxies_the_header_is_ignored(self):
        """proxy_count 0 -> REMOTE_ADDR even with a (forgeable) X-Forwarded-For."""
        self.assertEqual(client_address(self.request("1.2.3.4")), "10.0.0.1")

    def test_one_proxy_takes_the_last_address(self):
        """Header "6.6.6.6, 1.2.3.4" (the first one forged), 1 proxy -> 1.2.3.4."""
        self.assertEqual(client_address(self.request("6.6.6.6, 1.2.3.4"), 1), "1.2.3.4")

    def test_header_shorter_than_the_proxies_falls_back(self):
        """2 proxies but one address in the header -> REMOTE_ADDR; no header -> REMOTE_ADDR."""
        self.assertEqual(client_address(self.request("1.2.3.4"), 2), "10.0.0.1")
        self.assertEqual(client_address(self.request(), 1), "10.0.0.1")

    def test_key_is_stable_and_hides_the_address(self):
        """Same address -> same 32-character key, without the address in it; another address -> another key."""
        first = client_key(self.request("1.2.3.4"), 1)
        self.assertEqual(first, client_key(self.request("9.9.9.9, 1.2.3.4"), 1))
        self.assertEqual(len(first), 32)
        self.assertNotIn("1.2.3.4", first)
        self.assertNotEqual(first, client_key(self.request("1.2.3.5"), 1))
