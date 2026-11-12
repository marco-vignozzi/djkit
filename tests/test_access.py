"""
Tests for djkit.access (get_accessible_or_404), on Django's own auth models
(see test_db.AccessibleQuerySetTests for the Group / Permission setup).

Run with: python manage.py test djkit.tests.test_access
"""

from unittest import mock

from django.contrib.auth.models import Group, Permission
from django.db import transaction
from django.test import TestCase

from djkit.access import get_accessible_or_404
from djkit.db import AccessibleQuerySet
from djkit.errors import NotFound


class GetAccessibleOr404Tests(TestCase):
    """Missing and not-accessible objects give the same NotFound."""

    def setUp(self):
        """Groups 'red' (member Anna) and 'blue' (member Bruno); permissions play the users."""
        patcher = mock.patch.object(Group, "ACCESS_PATH", "permissions", create=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.anna, self.bruno = Permission.objects.order_by("pk")[:2]
        self.red = Group.objects.create(name="red")
        self.blue = Group.objects.create(name="blue")
        self.red.permissions.add(self.anna)
        self.blue.permissions.add(self.bruno)
        self.groups = AccessibleQuerySet(model=Group)

    def test_accessible_object_returned(self):
        """Anna loads 'red' by id."""
        self.assertEqual(get_accessible_or_404(self.groups, self.anna, self.red.pk), self.red)

    def test_other_users_object_is_not_found(self):
        """Anna asks for 'blue' -> NotFound with the given message."""
        with self.assertRaises(NotFound) as caught:
            get_accessible_or_404(self.groups, self.anna, self.blue.pk, detail="Group not found.")
        self.assertEqual(caught.exception.detail, "Group not found.")

    def test_missing_or_malformed_id_is_not_found(self):
        """Id 999999 or 'abc' -> NotFound (never a 500)."""
        for pk in (999999, "abc"):
            with self.subTest(pk=pk), self.assertRaises(NotFound):
                get_accessible_or_404(self.groups, self.anna, pk)

    def test_queryset_filters_are_kept(self):
        """A QuerySet excluding 'red' -> NotFound even for Anna."""
        with self.assertRaises(NotFound):
            get_accessible_or_404(self.groups.exclude(name="red"), self.anna, self.red.pk)

    def test_lock_for_update(self):
        """for_update=True inside a transaction -> the object is returned."""
        with transaction.atomic():
            self.assertEqual(get_accessible_or_404(self.groups, self.anna, self.red.pk, for_update=True), self.red)
