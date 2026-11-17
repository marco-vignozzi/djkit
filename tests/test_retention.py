"""
Tests of djkit.retention: the dates of the purge and of the warning.

Run with: python manage.py test djkit.tests.test_retention
"""

from datetime import datetime, timedelta, timezone as dt_timezone

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, override_settings

from djkit.retention import purge_at, purge_cutoff, retention_days, warning_cutoff, warning_days

NOW = datetime(2026, 11, 17, 9, 0, tzinfo=dt_timezone.utc)


class RetentionTests(SimpleTestCase):
    """Defaults 183 / 30 days; the settings are checked."""

    def test_defaults(self):
        """No settings -> 183 and 30 days."""
        with self.settings():
            from django.conf import settings

            for name in ("DJKIT_RETENTION_DAYS", "DJKIT_RETENTION_WARNING_DAYS"):
                if hasattr(settings, name):
                    delattr(settings, name)
            self.assertEqual((retention_days(), warning_days()), (183, 30))

    @override_settings(DJKIT_RETENTION_DAYS=10, DJKIT_RETENTION_WARNING_DAYS=3)
    def test_dates(self):
        """Purge 10 days after the deletion; due when deleted 10 days ago; warned when deleted 7 days ago."""
        self.assertEqual(purge_at(NOW), NOW + timedelta(days=10))
        self.assertEqual(purge_cutoff(NOW), NOW - timedelta(days=10))
        self.assertEqual(warning_cutoff(NOW), NOW - timedelta(days=7))

    def test_invalid_settings(self):
        """0 days, a warning not shorter than the retention, a negative warning -> ImproperlyConfigured."""
        for days, warning in ((0, 0), (10, 10), (10, -1)):
            with self.subTest(days=days, warning=warning), override_settings(
                DJKIT_RETENTION_DAYS=days, DJKIT_RETENTION_WARNING_DAYS=warning
            ):
                with self.assertRaises(ImproperlyConfigured):
                    warning_days()
