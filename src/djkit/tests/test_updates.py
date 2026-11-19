"""
Tests for djkit.updates (apply_patch), on Django's own auth models and on
PricedTestItem, a concrete model defined only for these tests (app_label
"djkit"; its table is created in setUpClass, like SoftDeleteTestItem in
test_soft_delete).

Run with: python manage.py test djkit.tests.test_updates
"""

from decimal import Decimal

from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.db import connection, models
from django.test import TestCase

from djkit.errors import InvalidData
from djkit.updates import apply_patch


class ApplyPatchTests(TestCase):
    """apply_patch changes only the sent fields, validates and returns the diff."""

    def setUp(self):
        """A group 'red' and a permission to edit."""
        self.group = Group.objects.create(name="red")
        self.permission = Permission.objects.select_related("content_type").first()

    def test_sent_field_changed_and_saved(self):
        """{'name': 'blue'} -> saved, diff {'name': ['red', 'blue']}."""
        changes = apply_patch(self.group, {"name": "blue"})
        self.assertEqual(changes, {"name": ["red", "blue"]})
        self.group.refresh_from_db()
        self.assertEqual(self.group.name, "blue")

    def test_other_fields_untouched(self):
        """Changing codename leaves name and content_type as they were."""
        name, content_type_id = self.permission.name, self.permission.content_type_id
        apply_patch(self.permission, {"codename": "new_code"})
        self.permission.refresh_from_db()
        self.assertEqual((self.permission.name, self.permission.content_type_id), (name, content_type_id))

    def test_same_value_gives_empty_diff(self):
        """{'name': 'red'} on 'red' -> {} (nothing to log)."""
        self.assertEqual(apply_patch(self.group, {"name": "red"}), {})

    def test_foreign_key_by_primary_key_or_instance(self):
        """content_type given as pk, then as instance -> content_type_id updated both times."""
        first, second = ContentType.objects.exclude(pk=self.permission.content_type_id)[:2]
        changes = apply_patch(self.permission, {"content_type": first.pk})
        self.assertEqual(changes["content_type_id"][1], first.pk)
        apply_patch(self.permission, {"content_type": second})
        self.permission.refresh_from_db()
        self.assertEqual(self.permission.content_type_id, second.pk)

    def test_unknown_primary_key_or_not_allowed_field_rejected(self):
        """'color' (unknown), 'id' (pk) and 'name' outside allowed -> InvalidData naming each field."""
        with self.assertRaises(InvalidData) as caught:
            apply_patch(self.group, {"color": "x", "id": 5})
        self.assertEqual(set(caught.exception.extra["errors"]), {"color", "id"})
        with self.assertRaises(InvalidData) as caught:
            apply_patch(self.group, {"name": "blue"}, allowed={"permissions"})
        self.assertIn("name", caught.exception.extra["errors"])

    def test_invalid_value_rejected_and_nothing_saved(self):
        """Name of 151 characters -> InvalidData on 'name'; the database keeps 'red'."""
        with self.assertRaises(InvalidData) as caught:
            apply_patch(self.group, {"name": "x" * 151})
        self.assertIn("name", caught.exception.extra["errors"])
        self.assertEqual(Group.objects.get(pk=self.group.pk).name, "red")

    def test_unique_violation_rejected(self):
        """Renaming to an existing group name -> InvalidData from full_clean."""
        Group.objects.create(name="blue")
        with self.assertRaises(InvalidData):
            apply_patch(self.group, {"name": "blue"})


class PricedTestItem(models.Model):
    """Concrete row with a decimal field, used only by these tests."""

    name = models.CharField(max_length=20)
    price = models.DecimalField(max_digits=8, decimal_places=2)

    class Meta:
        app_label = "djkit"


class ApplyPatchDecimalTests(TestCase):
    """A decimal equal to the stored one but written differently is not a change."""

    @classmethod
    def setUpClass(cls):
        """Create the table of PricedTestItem (removed by the class rollback)."""
        super().setUpClass()
        with connection.schema_editor() as editor:
            editor.create_model(PricedTestItem)

    def setUp(self):
        """An item 'lamp' at 650.00, read back from the database."""
        self.item = PricedTestItem.objects.create(name="lamp", price=Decimal("650"))
        self.item.refresh_from_db()

    def test_same_decimal_written_differently_gives_empty_diff(self):
        """price 650 on a stored 650.00 -> {} (nothing to log)."""
        self.assertEqual(apply_patch(self.item, {"price": Decimal("650")}), {})

    def test_diff_lists_only_the_fields_really_changed(self):
        """price 650 and name 'desk' -> diff {'name': ['lamp', 'desk']} only."""
        changes = apply_patch(self.item, {"price": Decimal("650"), "name": "desk"})
        self.assertEqual(changes, {"name": ["lamp", "desk"]})
