"""
Tests for djkit.db.

Use Django's own models (Group, Permission, ContentType), so the framework is
tested without any project model (the user model is not used: projects may
swap it).

Run with: python manage.py test djkit.tests.test_db
"""

from datetime import date
from decimal import Decimal
from unittest import mock

from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.db.models import OuterRef, Q
from django.test import SimpleTestCase, TestCase, override_settings

from djkit.db import AccessibleQuerySet, count_subquery, date_filter, ensure_unique, sum_subquery
from djkit.errors import Conflict


@override_settings(DJKIT_MESSAGES={})
class EnsureUniqueTests(TestCase):
    """ensure_unique raises Conflict for values already used by other rows."""

    def setUp(self):
        """Two groups: 'staff' and 'sales'."""
        self.staff = Group.objects.create(name="staff")
        Group.objects.create(name="sales")

    def test_free_value_passes(self):
        """name 'support' (unused) -> no error."""
        ensure_unique(Group, {"name": "support"})

    def test_used_value_raises_conflict_on_its_field(self):
        """name 'sales' -> Conflict with errors {'name': ['This value is already used.']}."""
        with self.assertRaises(Conflict) as caught:
            ensure_unique(Group, {"name": "sales"})
        self.assertEqual(caught.exception.extra["errors"], {"name": ["This value is already used."]})
        self.assertEqual(caught.exception.detail, "This value is already used.")

    def test_row_being_updated_may_keep_its_value(self):
        """name 'staff' with exclude_pk of 'staff' -> no error; of another row -> Conflict."""
        ensure_unique(Group, {"name": "staff"}, exclude_pk=self.staff.pk)
        with self.assertRaises(Conflict):
            ensure_unique(Group, {"name": "staff"}, exclude_pk=self.staff.pk + 100)

    def test_custom_message_and_none_values(self):
        """Custom message for 'name' used in errors and detail; a None value is skipped."""
        with self.assertRaises(Conflict) as caught:
            ensure_unique(Group, {"name": "sales", "id": None}, messages={"name": "Name taken."})
        self.assertEqual(caught.exception.extra["errors"], {"name": ["Name taken."]})
        self.assertEqual(caught.exception.detail, "Name taken.")


class DateFilterTests(SimpleTestCase):
    """date_filter builds an optional 'on or before' condition."""

    def test_with_date_filters_on_or_before(self):
        """('due_date', 31/3) -> Q(due_date__lte=31/3)."""
        self.assertEqual(date_filter("due_date", date(2026, 3, 31)), Q(due_date__lte=date(2026, 3, 31)))

    def test_without_date_is_empty(self):
        """as_of None -> empty Q (no restriction)."""
        self.assertEqual(date_filter("due_date", None), Q())


class SubqueryTests(TestCase):
    """sum_subquery and count_subquery annotate each row, with 0 for no rows."""

    def test_count_subquery_counts_related_rows_and_returns_zero_for_none(self):
        """Permissions per content type: the real count, and 0 for a type with no permissions."""
        empty = ContentType.objects.create(app_label="djkit_test", model="empty")
        group_type = ContentType.objects.get_for_model(Group)
        rows = ContentType.objects.annotate(
            permission_count=count_subquery(Permission.objects.filter(content_type=OuterRef("pk")))
        )
        self.assertEqual(rows.get(pk=empty.pk).permission_count, 0)
        self.assertEqual(
            rows.get(pk=group_type.pk).permission_count,
            Permission.objects.filter(content_type=group_type).count(),
        )

    def test_sum_subquery_adds_a_field_and_returns_zero_with_decimals(self):
        """Sum of permission ids per content type; a type with none -> Decimal('0.00')."""
        empty = ContentType.objects.create(app_label="djkit_test", model="empty")
        group_type = ContentType.objects.get_for_model(Group)
        rows = ContentType.objects.annotate(
            id_total=sum_subquery(Permission.objects.filter(content_type=OuterRef("pk")), field="id")
        )
        expected = sum(Permission.objects.filter(content_type=group_type).values_list("id", flat=True))
        self.assertEqual(rows.get(pk=group_type.pk).id_total, Decimal(expected))
        zero = rows.get(pk=empty.pk).id_total
        self.assertEqual(zero, Decimal("0.00"))
        self.assertEqual(str(zero), "0.00")


class AccessibleQuerySetTests(TestCase):
    """accessible_by follows the model's ACCESS_PATH; _model finds models of the same app."""

    def setUp(self):
        """
        Groups 'red' and 'blue' with ACCESS_PATH = 'permissions'. accessible_by
        filters on any related object, so two permissions play the role of the
        users ('anna', 'bruno'): the test needs no user model, which projects
        may swap.
        """
        patcher = mock.patch.object(Group, "ACCESS_PATH", "permissions", create=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.anna, self.bruno = Permission.objects.order_by("pk")[:2]
        self.red = Group.objects.create(name="red")
        self.blue = Group.objects.create(name="blue")
        self.red.permissions.add(self.anna)
        self.blue.permissions.add(self.bruno)
        self.groups = AccessibleQuerySet(model=Group)

    def test_user_sees_only_rows_reachable_through_access_path(self):
        """Anna -> only 'red'; Bruno -> only 'blue'."""
        self.assertQuerySetEqual(self.groups.accessible_by(self.anna), [self.red])
        self.assertQuerySetEqual(self.groups.accessible_by(self.bruno), [self.blue])

    def test_shared_row_visible_to_every_member(self):
        """Bruno joins 'red' -> both see 'red'."""
        self.red.permissions.add(self.bruno)
        self.assertIn(self.red, self.groups.accessible_by(self.anna))
        self.assertIn(self.red, self.groups.accessible_by(self.bruno))

    def test_model_lookup_stays_in_the_same_app(self):
        """On auth.Group, _model('Permission') -> auth.Permission."""
        self.assertIs(self.groups._model("Permission"), Permission)
