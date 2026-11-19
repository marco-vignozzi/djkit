"""
Tests for the logical deletion helpers of djkit.db (SoftDeleteModel,
SoftDeleteQuerySet, DeletedFilter, ensure_not_deleted) and for
get_accessible_or_404(include_deleted=True).

Use a concrete model defined only for these tests (app_label "djkit"; its
table is created in setUpClass, inside the class transaction, like
AuditTestEntry in test_audit), owned by a Django
Permission that plays the role of the user (projects may swap the user
model).

Run with: python manage.py test djkit.tests.test_soft_delete
"""

from datetime import datetime, timezone as dt_timezone

from django.contrib.auth.models import Permission
from django.db import IntegrityError, connection, models, transaction
from django.test import TestCase, override_settings

from djkit.access import get_accessible_or_404
from djkit.db import DeletedFilter, SoftDeleteModel, SoftDeleteQuerySet, ensure_not_deleted
from djkit.errors import Conflict, NotFound

# Deletion time used by the rows deleted in setUp.
DELETED_AT = datetime(2026, 3, 1, 9, 0, tzinfo=dt_timezone.utc)


class SoftDeleteTestItem(SoftDeleteModel):
    """Concrete soft-deletable row used only by these tests."""

    ACCESS_PATH = "owner"

    name = models.CharField(max_length=20)
    owner = models.ForeignKey(Permission, on_delete=models.CASCADE, related_name="+")

    objects = SoftDeleteQuerySet.as_manager()

    class Meta:
        app_label = "djkit"
        constraints = [SoftDeleteModel.deleted_state_constraint("softdeletetestitem_deleted_state")]


# The framework's default rules, whatever policy the project configures.
@override_settings(DJKIT_ACCESS_POLICY=None)
class SoftDeleteQuerySetTests(TestCase):
    """Deleted rows stay in the table, are hidden by accessible_by and can still be read on request."""

    @classmethod
    def setUpClass(cls):
        """Create the table of SoftDeleteTestItem (removed by the class rollback)."""
        super().setUpClass()
        with connection.schema_editor() as editor:
            editor.create_model(SoftDeleteTestItem)

    def setUp(self):
        """Anna owns 'kept' and 'gone' ('gone' deleted logically); Bruno owns 'other'."""
        self.anna, self.bruno = Permission.objects.order_by("pk")[:2]
        self.kept = SoftDeleteTestItem.objects.create(name="kept", owner=self.anna)
        self.gone = SoftDeleteTestItem.objects.create(name="gone", owner=self.anna, is_deleted=True, deleted_at=DELETED_AT)
        self.other = SoftDeleteTestItem.objects.create(name="other", owner=self.bruno)

    def test_new_row_is_not_deleted(self):
        """is_deleted defaults to False, deleted_at to None."""
        self.assertFalse(self.kept.is_deleted)
        self.assertIsNone(self.kept.deleted_at)

    def test_database_keeps_the_two_fields_consistent(self):
        """is_deleted true without deleted_at, or deleted_at without is_deleted -> IntegrityError."""
        for fields in ({"is_deleted": True}, {"deleted_at": DELETED_AT}):
            with self.subTest(**fields), self.assertRaises(IntegrityError), transaction.atomic():
                SoftDeleteTestItem.objects.create(name="bad", owner=self.anna, **fields)

    def test_filter_deleted_modes(self):
        """exclude -> kept, other; include -> all 3; only -> gone; unknown value -> ValueError."""
        rows = SoftDeleteTestItem.objects.order_by("name")
        self.assertQuerySetEqual(rows.filter_deleted(DeletedFilter.EXCLUDE), [self.kept, self.other])
        self.assertQuerySetEqual(rows.filter_deleted(DeletedFilter.INCLUDE), [self.gone, self.kept, self.other])
        self.assertQuerySetEqual(rows.filter_deleted("only"), [self.gone])
        with self.assertRaises(ValueError):
            rows.filter_deleted("everything")

    def test_alive_and_deleted_split_the_rows(self):
        """alive -> kept, other; deleted -> gone."""
        self.assertQuerySetEqual(SoftDeleteTestItem.objects.alive().order_by("name"), [self.kept, self.other])
        self.assertQuerySetEqual(SoftDeleteTestItem.objects.deleted(), [self.gone])

    def test_default_manager_still_returns_deleted_rows(self):
        """objects.all() -> 3 rows: history and admin keep seeing them."""
        self.assertEqual(SoftDeleteTestItem.objects.count(), 3)

    def test_accessible_by_hides_deleted_rows(self):
        """Anna -> only 'kept'; with include_deleted=True -> 'gone' and 'kept', never Bruno's row."""
        self.assertQuerySetEqual(SoftDeleteTestItem.objects.accessible_by(self.anna), [self.kept])
        self.assertQuerySetEqual(
            SoftDeleteTestItem.objects.accessible_by(self.anna, include_deleted=True).order_by("name"),
            [self.gone, self.kept],
        )

    def test_deleted_row_is_not_found(self):
        """get_accessible_or_404 on a deleted row -> NotFound, like a missing one."""
        with self.assertRaises(NotFound):
            get_accessible_or_404(SoftDeleteTestItem, self.anna, self.gone.pk)
        self.assertEqual(get_accessible_or_404(SoftDeleteTestItem, self.anna, self.kept.pk), self.kept)

    def test_deleted_row_found_with_include_deleted(self):
        """include_deleted=True -> the deleted row of Anna; Bruno still gets NotFound on it."""
        self.assertEqual(get_accessible_or_404(SoftDeleteTestItem, self.anna, self.gone.pk, include_deleted=True), self.gone)
        with self.assertRaises(NotFound):
            get_accessible_or_404(SoftDeleteTestItem, self.bruno, self.gone.pk, include_deleted=True)

    @override_settings(DJKIT_MESSAGES={})
    def test_ensure_not_deleted(self):
        """Deleted row -> Conflict with the 'deleted_read_only' message (or the given detail); live row -> nothing."""
        ensure_not_deleted(self.kept)
        with self.assertRaisesMessage(Conflict, "This item has been deleted: it can only be consulted."):
            ensure_not_deleted(self.gone)
        with self.assertRaisesMessage(Conflict, "Read only."):
            ensure_not_deleted(self.gone, detail="Read only.")

    def test_instance_mark_deleted(self):
        """kept.mark_deleted(when) -> is_deleted true and deleted_at = when, saved in the database."""
        self.kept.mark_deleted(DELETED_AT)
        self.kept.refresh_from_db()
        self.assertEqual((self.kept.is_deleted, self.kept.deleted_at), (True, DELETED_AT))

    def test_mark_deleted_counts_only_rows_not_yet_deleted(self):
        """mark_deleted on Anna's 2 rows -> 1 ('kept' gets deleted_at now); 'gone' keeps its date; both still in the table."""
        changed = SoftDeleteTestItem.objects.filter(owner=self.anna).mark_deleted()
        self.assertEqual(changed, 1)
        self.kept.refresh_from_db()
        self.gone.refresh_from_db()
        self.assertTrue(self.kept.is_deleted)
        self.assertIsNotNone(self.kept.deleted_at)
        self.assertEqual(self.gone.deleted_at, DELETED_AT)
        self.assertEqual(SoftDeleteTestItem.objects.filter(owner=self.anna).count(), 2)
