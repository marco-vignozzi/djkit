"""
Retention of deleted data: how long closed or deleted rows are kept before
the project purges them for good, and when the owner is warned.

The project decides what to purge and how; this module only computes the
dates, from two settings, so every purge uses the same rule.

Settings:
    DJKIT_RETENTION_DAYS          days a deleted row is kept (default 183,
                                  about six months); must be positive.
    DJKIT_RETENTION_WARNING_DAYS  days before the purge when the owner is
                                  warned (default 30); 0 <= value < days.

Functions:
    retention_days()              -> DJKIT_RETENTION_DAYS (checked)
    warning_days()                -> DJKIT_RETENTION_WARNING_DAYS (checked)
    purge_at(deleted_at)          -> when a row deleted at that time is purged
    purge_cutoff(now)             -> rows deleted at or before it are due
    warning_cutoff(now)           -> rows deleted at or before it get the
                                     warning
"""

from datetime import datetime, timedelta

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.utils import timezone


def retention_days() -> int:
    """
    Days a deleted row is kept.

    Raises:
        ImproperlyConfigured: the setting is not a positive integer.
    """
    days = getattr(settings, "DJKIT_RETENTION_DAYS", 183)
    if not isinstance(days, int) or days <= 0:
        raise ImproperlyConfigured("DJKIT_RETENTION_DAYS must be a positive integer.")
    return days


def warning_days() -> int:
    """
    Days before the purge when the owner is warned.

    Raises:
        ImproperlyConfigured: not an integer between 0 and retention_days() - 1.
    """
    days = getattr(settings, "DJKIT_RETENTION_WARNING_DAYS", 30)
    if not isinstance(days, int) or not 0 <= days < retention_days():
        raise ImproperlyConfigured("DJKIT_RETENTION_WARNING_DAYS must be 0 or more and less than DJKIT_RETENTION_DAYS.")
    return days


def purge_at(deleted_at: datetime) -> datetime:
    """When a row deleted at `deleted_at` is purged."""
    return deleted_at + timedelta(days=retention_days())


def purge_cutoff(now: datetime | None = None) -> datetime:
    """Rows deleted at or before the returned time are due for purging."""
    return (now or timezone.now()) - timedelta(days=retention_days())


def warning_cutoff(now: datetime | None = None) -> datetime:
    """Rows deleted at or before the returned time get the warning before the purge."""
    return (now or timezone.now()) - timedelta(days=retention_days() - warning_days())
