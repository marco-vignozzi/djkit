"""
Tests for djkit.workspaces: memberships, the active workspace, switching
and acting in another workspace.

Use concrete models defined only for these tests (app_label "djkit"; their
tables are created in setUpClass, inside the class transaction, like
SoftDeleteTestItem in test_soft_delete). WsTestUser plays the role of the
user model.

Run with: python manage.py test djkit.tests.test_workspaces
"""

from datetime import datetime, timezone as dt_timezone

from django.db import IntegrityError, connection, models, transaction
from django.test import TestCase

from djkit.errors import NotFound
from djkit.workspaces import (
    MembershipModel,
    WorkspaceModel,
    acting_in,
    active_membership,
    active_workspace,
    forget_active,
    is_workspace_admin,
    memberships,
    switch_workspace,
)

GONE = datetime(2026, 3, 1, 9, 0, tzinfo=dt_timezone.utc)


class WsTestWorkspace(WorkspaceModel):
    """Concrete workspace used only by these tests."""

    name = models.CharField(max_length=20)

    class Meta:
        app_label = "djkit"
        constraints = [WorkspaceModel.deleted_state_constraint("wstestworkspace_deleted_state")]


class WsTestUser(models.Model):
    """Minimal user with the current_workspace of the contract."""

    name = models.CharField(max_length=20)
    current_workspace = models.ForeignKey(WsTestWorkspace, null=True, on_delete=models.SET_NULL, related_name="+")
    is_authenticated = True

    class Meta:
        app_label = "djkit"


class WsTestMembership(MembershipModel):
    """Concrete membership used only by these tests."""

    user = models.ForeignKey(WsTestUser, on_delete=models.CASCADE, related_name="memberships")
    workspace = models.ForeignKey(WsTestWorkspace, on_delete=models.CASCADE, related_name="memberships")

    class Meta:
        app_label = "djkit"
        constraints = [
            MembershipModel.one_admin_constraint("wstestmembership_one_admin"),
            MembershipModel.one_membership_constraint("wstestmembership_one_membership"),
            MembershipModel.deleted_state_constraint("wstestmembership_deleted_state"),
        ]


class WorkspaceTests(TestCase):
    """Anna administers 'anna' and is a member of 'bruno'; the active workspace follows her choice."""

    @classmethod
    def setUpClass(cls):
        """Create the three test tables (removed by the class rollback)."""
        super().setUpClass()
        with connection.schema_editor() as editor:
            for model in (WsTestWorkspace, WsTestUser, WsTestMembership):
                editor.create_model(model)

    def setUp(self):
        """Workspaces 'anna' (Anna admin) and 'bruno' (Bruno admin, Anna member since later)."""
        self.ws_anna = WsTestWorkspace.objects.create(name="anna")
        self.ws_bruno = WsTestWorkspace.objects.create(name="bruno")
        self.anna = WsTestUser.objects.create(name="Anna")
        self.bruno = WsTestUser.objects.create(name="Bruno")
        self.bruno_admin = WsTestMembership.objects.create(user=self.bruno, workspace=self.ws_bruno, role="ADMIN", joined_at=datetime(2026, 1, 1, tzinfo=dt_timezone.utc))
        self.anna_member = WsTestMembership.objects.create(user=self.anna, workspace=self.ws_bruno, role="MEMBER", joined_at=datetime(2026, 1, 2, tzinfo=dt_timezone.utc))
        self.anna_admin = WsTestMembership.objects.create(user=self.anna, workspace=self.ws_anna, role="ADMIN", joined_at=datetime(2026, 1, 3, tzinfo=dt_timezone.utc))

    def fresh(self, user):
        """The user reloaded (no cached membership)."""
        return WsTestUser.objects.get(pk=user.pk)

    def test_memberships_are_oldest_first(self):
        """Anna: 'bruno' (2/1) then 'anna' (3/1)."""
        self.assertEqual([m.workspace.name for m in memberships(self.anna)], ["bruno", "anna"])

    def test_without_a_choice_the_admin_workspace_is_active(self):
        """No current_workspace -> the one she administers ('anna'), and she is its admin."""
        self.assertEqual(active_workspace(self.anna), self.ws_anna)
        self.assertTrue(is_workspace_admin(self.anna))

    def test_the_chosen_workspace_is_active(self):
        """current_workspace 'bruno' -> active 'bruno', role MEMBER, not admin."""
        self.anna.current_workspace = self.ws_bruno
        self.assertEqual(active_membership(self.anna), self.anna_member)
        self.assertFalse(is_workspace_admin(self.anna))

    def test_a_deleted_membership_or_workspace_gives_no_access(self):
        """Membership in 'bruno' deleted -> not listed; 'anna' closed too -> no active workspace."""
        WsTestMembership.objects.filter(pk=self.anna_member.pk).update(is_deleted=True, deleted_at=GONE)
        self.assertEqual([m.workspace.name for m in memberships(self.anna)], ["anna"])
        WsTestWorkspace.objects.filter(pk=self.ws_anna.pk).update(is_deleted=True, deleted_at=GONE)
        self.assertIsNone(active_workspace(self.fresh(self.anna)))

    def test_a_member_without_admin_role_gets_the_oldest(self):
        """A user only member of 'bruno' (no choice) -> 'bruno'."""
        carla = WsTestUser.objects.create(name="Carla")
        WsTestMembership.objects.create(user=carla, workspace=self.ws_bruno, role="MEMBER")
        self.assertEqual(active_workspace(carla), self.ws_bruno)

    def test_switch_saves_the_choice(self):
        """switch to 'bruno' -> active now and after a reload (current_workspace saved)."""
        switch_workspace(self.anna, self.ws_bruno.pk)
        self.assertEqual(active_workspace(self.anna), self.ws_bruno)
        self.assertEqual(active_workspace(self.fresh(self.anna)), self.ws_bruno)

    def test_switch_to_a_foreign_workspace_is_not_found(self):
        """Bruno switching to 'anna' (not his) -> NotFound; his choice is unchanged."""
        with self.assertRaises(NotFound):
            switch_workspace(self.bruno, self.ws_anna.pk)
        self.assertIsNone(self.fresh(self.bruno).current_workspace_id)

    def test_acting_in_restores_the_previous_membership(self):
        """Inside acting_in(member of 'bruno') the active one is 'bruno'; after it 'anna' again."""
        self.assertEqual(active_workspace(self.anna), self.ws_anna)
        with acting_in(self.anna, self.anna_member):
            self.assertEqual(active_workspace(self.anna), self.ws_bruno)
        self.assertEqual(active_workspace(self.anna), self.ws_anna)

    def test_forget_active_reads_again(self):
        """Cached 'anna'; current_workspace changed by hand -> still 'anna' until forget_active."""
        self.assertEqual(active_workspace(self.anna), self.ws_anna)
        self.anna.current_workspace = self.ws_bruno
        self.assertEqual(active_workspace(self.anna), self.ws_anna)
        forget_active(self.anna)
        self.assertEqual(active_workspace(self.anna), self.ws_bruno)

    def test_one_admin_and_one_membership_per_workspace(self):
        """A second ADMIN of 'bruno', or a second alive membership of Anna there -> IntegrityError."""
        for user, role in ((self.anna, "ADMIN"), (self.anna, "MEMBER")):
            with self.subTest(role=role), self.assertRaises(IntegrityError), transaction.atomic():
                if role == "ADMIN":
                    WsTestMembership.objects.filter(pk=self.anna_member.pk).update(role="ADMIN")
                else:
                    WsTestMembership.objects.create(user=user, workspace=self.ws_bruno, role=role)

    def test_anonymous_has_no_workspace(self):
        """None or an unauthenticated user -> None."""
        self.assertIsNone(active_membership(None))
