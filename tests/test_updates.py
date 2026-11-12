"""
Tests for djkit.updates (apply_patch), on Django's own auth models.

Run with: python manage.py test djkit.tests.test_updates
"""

from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
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
