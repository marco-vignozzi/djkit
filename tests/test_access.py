"""
Tests for djkit.access (policy, scope, check, get_accessible_or_404), on Django's own auth models
(see test_db.AccessibleQuerySetTests for the Group / Permission setup).

Run with: python manage.py test djkit.tests.test_access
"""

from unittest import mock

from django.contrib.auth.models import Group, Permission
from django.db import transaction
from django.test import TestCase, override_settings

from djkit.access import AccessLevel, AccessPolicy, Action, check, get_accessible_or_404, get_policy, level, scope
from djkit.db import AccessibleQuerySet
from djkit.errors import Forbidden, NotFound
from djkit.messages import get_message


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


class ReadEverythingPolicy(AccessPolicy):
    """Test policy: every group is readable by anyone, writable only by its members."""

    def scope(self, principal, queryset, action, include_deleted=False):
        """READ -> every row; WRITE -> the rows of accessible_by (membership)."""
        return queryset if action == Action.READ else queryset.accessible_by(principal)


POLICY_PATH = "djkit.tests.test_access.ReadEverythingPolicy"


@override_settings(DJKIT_ACCESS_POLICY=POLICY_PATH)
class AccessPolicyTests(TestCase):
    """DJKIT_ACCESS_POLICY: read-only rows give Forbidden on a write, invisible ones NotFound."""

    def setUp(self):
        """Groups 'red' (member Anna) and 'blue' (member Bruno), all readable by anyone."""
        patcher = mock.patch.object(Group, "ACCESS_PATH", "permissions", create=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.anna, self.bruno = Permission.objects.order_by("pk")[:2]
        self.red = Group.objects.create(name="red")
        self.blue = Group.objects.create(name="blue")
        self.red.permissions.add(self.anna)
        self.blue.permissions.add(self.bruno)
        self.groups = AccessibleQuerySet(model=Group)

    def test_policy_comes_from_the_setting(self):
        """get_policy() -> an instance of the class named by DJKIT_ACCESS_POLICY."""
        self.assertIsInstance(get_policy(), ReadEverythingPolicy)

    def test_scope_depends_on_the_action(self):
        """Anna: READ -> red and blue; WRITE -> only red."""
        self.assertEqual(set(scope(self.anna, self.groups, Action.READ)), {self.red, self.blue})
        self.assertEqual(list(scope(self.anna, self.groups, Action.WRITE)), [self.red])

    def test_level_and_check(self):
        """Anna on red FULL, on blue READ_ONLY: check WRITE on blue -> Forbidden with the "read_only" message, READ passes."""
        groups = self.groups
        self.assertEqual((level(self.anna, self.red, groups), level(self.anna, self.blue, groups)), (AccessLevel.FULL, AccessLevel.READ_ONLY))
        check(self.anna, Action.READ, self.blue, source=groups)
        check(self.anna, Action.WRITE, self.red, source=groups)
        with self.assertRaises(Forbidden) as caught:
            check(self.anna, Action.WRITE, self.blue, source=groups)
        self.assertEqual(caught.exception.detail, get_message("read_only"))

    def test_get_for_write_of_a_read_only_row_is_forbidden(self):
        """get_accessible_or_404(blue, action=WRITE) for Anna -> Forbidden with the given message; READ -> blue."""
        self.assertEqual(get_accessible_or_404(self.groups, self.anna, self.blue.pk), self.blue)
        with self.assertRaises(Forbidden) as caught:
            get_accessible_or_404(self.groups, self.anna, self.blue.pk, action=Action.WRITE, read_only_detail="Read only.")
        self.assertEqual(caught.exception.detail, "Read only.")


class DefaultPolicyTests(TestCase):
    """Without DJKIT_ACCESS_POLICY read and write both follow accessible_by."""

    def test_default_policy_level(self):
        """Anna on her group FULL, on another group None; check READ on it -> NotFound."""
        with mock.patch.object(Group, "ACCESS_PATH", "permissions", create=True):
            anna = Permission.objects.order_by("pk")[0]
            red, blue = Group.objects.create(name="red"), Group.objects.create(name="blue")
            red.permissions.add(anna)
            groups = AccessibleQuerySet(model=Group)
            self.assertEqual((level(anna, red, groups), level(anna, blue, groups)), (AccessLevel.FULL, None))
            with self.assertRaises(NotFound):
                check(anna, Action.READ, blue, source=groups)
