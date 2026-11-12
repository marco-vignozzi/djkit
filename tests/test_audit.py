"""
Tests for djkit.audit.

A concrete entry model (AuditTestEntry) is defined here, so djkit itself
keeps no concrete model and no migration. Its table is created in
setUpClass, inside the class transaction (PostgreSQL DDL is transactional,
so the rollback removes it).

Run with: python manage.py test djkit.tests.test_audit
"""

import datetime
import uuid
from decimal import Decimal
from unittest import mock

from django.apps import apps
from django.contrib.auth.models import AnonymousUser, Group, Permission
from django.db import connection, models
from django.test import SimpleTestCase, TestCase, override_settings

from djkit.audit import AuditAction, AuditEntryBase, diff, log_write, snapshot, to_json_value
from djkit.testing.api import make_user


class AuditTestEntry(AuditEntryBase):
    """
    Concrete audit entry used only by these tests, with one context field.
    It coexists with the project's own entry model without redefining
    `actor`: each subclass gets its own reverse accessor name.
    """

    team_id = models.PositiveBigIntegerField(null=True)

    class Meta(AuditEntryBase.Meta):
        app_label = "djkit"


class JsonValueTests(SimpleTestCase):
    """to_json_value makes field values JSON-serializable."""

    def test_conversions(self):
        """Decimal, date, datetime, UUID, nested containers -> strings and lists."""
        moment = datetime.datetime(2026, 3, 15, 10, 30)
        key = uuid.UUID("12345678-1234-5678-1234-567812345678")
        self.assertEqual(to_json_value(Decimal("650.00")), "650.00")
        self.assertEqual(to_json_value(datetime.date(2026, 3, 15)), "2026-03-15")
        self.assertEqual(to_json_value(moment), "2026-03-15T10:30:00")
        self.assertEqual(to_json_value(key), str(key))
        self.assertEqual(to_json_value({"a": (Decimal("1.5"), None)}), {"a": ["1.5", None]})
        self.assertEqual(to_json_value(7), 7)


class DiffTests(SimpleTestCase):
    """diff lists only the keys whose value changed."""

    def test_changed_added_and_removed_keys(self):
        """name changed, note added, code removed, size unchanged."""
        before = {"name": "A", "code": "x", "size": 1}
        after = {"name": "B", "note": "n", "size": 1}
        self.assertEqual(diff(before, after), {"code": ["x", None], "name": ["A", "B"], "note": [None, "n"]})

    def test_identical_snapshots(self):
        """Same values -> {}."""
        self.assertEqual(diff({"a": 1}, {"a": 1}), {})


class SnapshotTests(TestCase):
    """snapshot gives a JSON view of the concrete fields."""

    def test_foreign_keys_by_attname_and_no_primary_key(self):
        """A Permission -> name, codename and content_type_id; no id."""
        permission = Permission.objects.select_related("content_type").first()
        data = snapshot(permission)
        self.assertEqual(set(data), {"name", "codename", "content_type_id"})
        self.assertEqual(data["content_type_id"], permission.content_type_id)

    def test_selected_fields_by_name_or_attname(self):
        """fields=['codename', 'content_type'] -> those two only."""
        permission = Permission.objects.first()
        self.assertEqual(set(snapshot(permission, ["codename", "content_type"])), {"codename", "content_type_id"})

    def test_password_never_included(self):
        """A user's snapshot has no 'password' key (DJKIT_AUDIT_EXCLUDED_FIELDS default)."""
        self.assertNotIn("password", snapshot(make_user()))

    @override_settings(DJKIT_AUDIT_EXCLUDED_FIELDS={"codename"})
    def test_excluded_fields_setting(self):
        """DJKIT_AUDIT_EXCLUDED_FIELDS={'codename'} -> codename dropped."""
        self.assertNotIn("codename", snapshot(Permission.objects.first()))


class LogWriteTests(TestCase):
    """log_write stores who did what on which object, with context fields."""

    @classmethod
    def setUpClass(cls):
        """Create the table of AuditTestEntry (removed by the class rollback)."""
        super().setUpClass()
        with connection.schema_editor() as editor:
            editor.create_model(AuditTestEntry)

    def setUp(self):
        """A user and a group to log changes about."""
        self.user = make_user()
        self.group = Group.objects.create(name="red")

    def test_create_stores_snapshot_and_context(self):
        """CREATE without changes -> full snapshot; actor, model, id, label and team_id stored."""
        entry = log_write(AuditTestEntry, self.user, AuditAction.CREATE, self.group, team_id=7)
        entry.refresh_from_db()
        self.assertEqual(entry.actor, self.user)
        self.assertEqual((entry.action, entry.model, entry.object_id), ("CREATE", "Group", self.group.pk))
        self.assertEqual(entry.object_label, "red")
        self.assertEqual(entry.changes, {"name": "red"})
        self.assertEqual(entry.team_id, 7)

    def test_update_stores_given_diff(self):
        """UPDATE with a diff -> the diff; without -> {}."""
        changed = log_write(AuditTestEntry, self.user, AuditAction.UPDATE, self.group, {"name": ["red", "blue"]})
        empty = log_write(AuditTestEntry, self.user, AuditAction.UPDATE, self.group)
        self.assertEqual(changed.changes, {"name": ["red", "blue"]})
        self.assertEqual(empty.changes, {})

    def test_anonymous_actor_stored_as_none(self):
        """AnonymousUser or None -> actor None."""
        self.assertIsNone(log_write(AuditTestEntry, AnonymousUser(), AuditAction.DELETE, self.group).actor)
        self.assertIsNone(log_write(AuditTestEntry, None, AuditAction.DELETE, self.group).actor)

    def test_values_made_json_serializable(self):
        """Decimal and date in the changes -> stored as strings."""
        entry = log_write(
            AuditTestEntry, self.user, AuditAction.UPDATE, self.group,
            {"amount": [Decimal("600.00"), Decimal("650.00")], "due": [None, datetime.date(2026, 4, 1)]},
        )
        entry.refresh_from_db()
        self.assertEqual(entry.changes, {"amount": ["600.00", "650.00"], "due": [None, "2026-04-01"]})

    def test_long_label_truncated(self):
        """A str(obj) of 400 characters is cut to the 300 of object_label."""
        with mock.patch.object(Group, "__str__", lambda group: "x" * 400):
            entry = log_write(AuditTestEntry, self.user, AuditAction.UPDATE, self.group)
        self.assertEqual(entry.object_label, "x" * 300)

    def test_reverse_accessor_is_unique_per_subclass(self):
        """actor's related_name -> 'djkit_audittestentry_entries', usable from the user."""
        self.assertEqual(AuditTestEntry._meta.get_field("actor").remote_field.related_name, "djkit_audittestentry_entries")
        entry = log_write(AuditTestEntry, self.user, AuditAction.UPDATE, self.group)
        self.assertQuerySetEqual(self.user.djkit_audittestentry_entries.all(), [entry])

    def test_several_entry_models_do_not_clash(self):
        """This test model and the project's own entry model coexist: no E304/E305 clash on actor."""
        entry_models = [m for m in apps.get_models() if issubclass(m, AuditEntryBase)]
        self.assertGreaterEqual(len(entry_models), 1)
        for model in entry_models:
            with self.subTest(model=model._meta.label):
                self.assertEqual(model.check(), [])

    def test_action_check_constraint_inherited(self):
        """The abstract base adds the 'djkit_audittestentry_action_valid' constraint."""
        names = {constraint.name for constraint in AuditTestEntry._meta.constraints}
        self.assertIn("djkit_audittestentry_action_valid", names)
