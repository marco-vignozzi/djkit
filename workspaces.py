"""
Workspaces: separate sets of data inside one database (multi-tenancy).

Every user may belong to several workspaces, each through a membership
with a role; one membership is the *active* one, and the project's access
rules restrict every query to the active workspace. One role (by default
"ADMIN") is the workspace's administrator: at most one per workspace.

Contract with the project:
    - a concrete workspace model, subclass of WorkspaceModel;
    - a concrete membership model, subclass of MembershipModel, with the
      foreign keys `user` (related_name="memberships") and `workspace`
      (related_name="memberships"); its Meta may use
      MembershipModel.one_admin_constraint / one_membership_constraint;
    - the user model has `current_workspace` (nullable foreign key to the
      workspace model): the workspace the user chose last, remembered
      across sessions (switch_workspace sets it).

Settings:
    DJKIT_WORKSPACE_ADMIN_ROLE  role of the administrator (default "ADMIN").

Functions:
    memberships(user)                -> the alive memberships of alive
                                        workspaces, oldest first
    active_membership(user)          -> the active membership, or None
    active_workspace(user)           -> its workspace, or None
    is_workspace_admin(user)         -> whether the active role is the admin one
    switch_workspace(user, id)       -> make another workspace active
    acting_in(user, membership)      -> context manager: act in a given
                                        membership (jobs that serve every
                                        workspace of a user)
    forget_active(user)              -> drop the cached active membership
"""

from contextlib import contextmanager

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone

from .db import SoftDeleteModel
from .errors import NotFound
from .messages import get_message

# Attribute of the user instance where the active membership is cached
# (the user object lives one request or one job iteration).
_CACHE = "_djkit_active_membership"
_MISSING = object()


def admin_role() -> str:
    """The role of a workspace's administrator (DJKIT_WORKSPACE_ADMIN_ROLE, default "ADMIN")."""
    return getattr(settings, "DJKIT_WORKSPACE_ADMIN_ROLE", "ADMIN")


class WorkspaceModel(SoftDeleteModel):
    """
    Abstract workspace: a separate set of data (soft-deletable: a closed
    workspace keeps its rows until the project purges them).

    Fields:
        created_at -> when it was created.
    """

    created_at = models.DateTimeField("created at", default=timezone.now)

    class Meta:
        abstract = True


class MembershipModel(SoftDeleteModel):
    """
    Abstract membership of a user in a workspace, with a role. A deleted
    membership (the user left, or was removed) gives no access.

    The concrete model adds `user` and `workspace` (see the module
    docstring).

    Fields:
        role      -> the project's role code (e.g. "ADMIN", "MEMBER").
        joined_at -> when the user joined.
    """

    role = models.CharField("role", max_length=20)
    joined_at = models.DateTimeField("joined at", default=timezone.now)

    class Meta:
        abstract = True

    @staticmethod
    def one_admin_constraint(name: str) -> models.UniqueConstraint:
        """
        At most one alive administrator per workspace.

        Args:
            name: constraint name.

        Returns:
            A partial UniqueConstraint on "workspace".
        """
        return models.UniqueConstraint(fields=["workspace"], condition=Q(role=admin_role(), is_deleted=False), name=name)

    @staticmethod
    def one_membership_constraint(name: str) -> models.UniqueConstraint:
        """
        At most one alive membership per user and workspace.

        Args:
            name: constraint name.

        Returns:
            A partial UniqueConstraint on ("user", "workspace").
        """
        return models.UniqueConstraint(fields=["user", "workspace"], condition=Q(is_deleted=False), name=name)


def memberships(user) -> models.QuerySet:
    """
    The memberships that give access: not deleted, of a workspace not
    deleted.

    Args:
        user: the user.

    Returns:
        A QuerySet with the workspace loaded, oldest first.
    """
    return (
        user.memberships.filter(is_deleted=False, workspace__is_deleted=False)
        .select_related("workspace")
        .order_by("joined_at", "pk")
    )


def active_membership(user):
    """
    The membership the user acts in: the one of `current_workspace` when
    it still gives access, else the one where the user is administrator,
    else the oldest. Cached on the user instance.

    Args:
        user: the user (anonymous or None -> None).

    Returns:
        The membership, or None when the user belongs to no workspace.
    """
    if user is None or not getattr(user, "is_authenticated", False):
        return None
    cached = getattr(user, _CACHE, _MISSING)
    if cached is not _MISSING:
        return cached
    rows = list(memberships(user))
    chosen = next((row for row in rows if row.workspace_id == user.current_workspace_id), None)
    if chosen is None:
        chosen = next((row for row in rows if row.role == admin_role()), rows[0] if rows else None)
    setattr(user, _CACHE, chosen)
    return chosen


def active_workspace(user):
    """
    The workspace the user acts in.

    Args:
        user: the user.

    Returns:
        The workspace of active_membership, or None.
    """
    membership = active_membership(user)
    return membership.workspace if membership is not None else None


def is_workspace_admin(user) -> bool:
    """
    Whether the user is the administrator of the active workspace.

    Args:
        user: the user.

    Returns:
        True when the active membership has the admin role.
    """
    membership = active_membership(user)
    return membership is not None and membership.role == admin_role()


def switch_workspace(user, workspace_id):
    """
    Make another workspace of the user the active one, also for the next
    sessions (saves user.current_workspace).

    Args:
        user: the user.
        workspace_id: id of a workspace the user belongs to.

    Returns:
        The new active membership.

    Raises:
        NotFound: the user has no membership giving access to it
            (message "workspace_not_found").
    """
    membership = memberships(user).filter(workspace_id=workspace_id).first()
    if membership is None:
        raise NotFound(get_message("workspace_not_found"))
    user.current_workspace_id = membership.workspace_id
    user.save(update_fields=["current_workspace"])
    setattr(user, _CACHE, membership)
    return membership


@contextmanager
def acting_in(user, membership):
    """
    Act in a given membership for a block of code, then restore what was
    cached before (e.g. a job that serves every workspace of a user).

    Args:
        user: the user.
        membership: one of the user's memberships.

    Yields:
        The membership.
    """
    previous = getattr(user, _CACHE, _MISSING)
    setattr(user, _CACHE, membership)
    try:
        yield membership
    finally:
        if previous is _MISSING:
            delattr(user, _CACHE)
        else:
            setattr(user, _CACHE, previous)


def forget_active(user) -> None:
    """
    Drop the cached active membership (after a membership changes).

    Args:
        user: the user.
    """
    if hasattr(user, _CACHE):
        delattr(user, _CACHE)
