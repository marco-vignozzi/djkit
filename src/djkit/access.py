"""
Access control: who may read or change which rows.

One policy decides everything. A project writes its rules in a subclass of
AccessPolicy and names it in the DJKIT_ACCESS_POLICY setting (dotted path);
services and endpoints never write access filters themselves, they ask:

    scope(principal, Invoice, Action.READ)        -> the rows it may see
    check(principal, Action.WRITE, invoice)       -> NotFound / Forbidden
    get_accessible_or_404(Invoice, principal, pk, action=Action.WRITE)

A principal is whoever acts: today a logged-in user; a project may pass
anything its policy understands (a tenant of an app, a role, an automatic
job). Rules:
    - a row outside scope(READ) does not exist for the principal: NotFound,
      never revealing that it exists;
    - a row inside scope(READ) but outside scope(WRITE) is read-only:
      Forbidden (403) on any change.
Without DJKIT_ACCESS_POLICY the default AccessPolicy is used: read and
write both follow the model's accessible_by (djkit.db.AccessibleQuerySet).
"""

from functools import lru_cache

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.module_loading import import_string

from .errors import Forbidden, NotFound


class Action(models.TextChoices):
    """What a principal wants to do with a row."""

    READ = "read", "read"  # see it (lists, detail, reports)
    WRITE = "write", "write"  # create, change or delete it


class AccessLevel(models.TextChoices):
    """How far a principal may go with a row it can see (shown in outputs)."""

    FULL = "FULL", "full"  # read and write
    READ_ONLY = "READ_ONLY", "read only"  # read only (writes -> Forbidden)


def _queryset(source) -> models.QuerySet:
    """
    A QuerySet from a model class, a manager or a QuerySet.

    Args:
        source: the model, manager or QuerySet.

    Returns:
        A QuerySet (a copy: the caller's one is not changed).
    """
    if isinstance(source, type) and issubclass(source, models.Model):
        return source._default_manager.all()
    return source.all()


class AccessPolicy:
    """
    The rules of a project. Subclass it and override scope (and, for
    something finer than a QuerySet filter, level).

    The default rules: READ and WRITE both give the rows of
    accessible_by(principal) (djkit.db.AccessibleQuerySet and
    SoftDeleteQuerySet).
    """

    def scope(self, principal, queryset: models.QuerySet, action: str, include_deleted: bool = False) -> models.QuerySet:
        """
        The rows of a QuerySet the principal may access for an action.

        Args:
            principal: who acts (e.g. request.user).
            queryset: the rows to restrict (any filters already applied).
            action: an Action value.
            include_deleted: also the rows deleted logically (consultation;
                djkit.db.SoftDeleteQuerySet).

        Returns:
            The restricted QuerySet.
        """
        # Only a SoftDeleteQuerySet knows about deleted rows; on any other
        # QuerySet every row is "alive" and include_deleted changes nothing.
        if include_deleted and hasattr(queryset, "filter_deleted"):
            return queryset.accessible_by(principal, include_deleted=True)
        return queryset.accessible_by(principal)

    def level(self, principal, obj, source=None) -> str | None:
        """
        How far the principal may go with one row.

        Args:
            principal: who acts.
            obj: a model instance.
            source: where to look for it (model, manager or QuerySet); the
                model's default manager when None.

        Returns:
            AccessLevel.FULL when it may write it, READ_ONLY when it may
            only read it, None when it may not even see it.
        """
        rows = _queryset(source if source is not None else type(obj)).filter(pk=obj.pk)
        if self.scope(principal, rows, Action.WRITE, include_deleted=True).exists():
            return AccessLevel.FULL
        if self.scope(principal, rows, Action.READ, include_deleted=True).exists():
            return AccessLevel.READ_ONLY
        return None


@lru_cache(maxsize=None)
def _load_policy(path: str | None) -> AccessPolicy:
    """
    Build the policy named by a dotted path (cached per path).

    Args:
        path: dotted path of an AccessPolicy subclass, or None.

    Returns:
        An instance of it, or of AccessPolicy when path is None.
    """
    return import_string(path)() if path else AccessPolicy()


def get_policy() -> AccessPolicy:
    """The project's policy (setting DJKIT_ACCESS_POLICY), or the default AccessPolicy."""
    return _load_policy(getattr(settings, "DJKIT_ACCESS_POLICY", None))


def scope(principal, source, action: str = Action.READ, include_deleted: bool = False) -> models.QuerySet:
    """
    The rows a principal may access for an action (see AccessPolicy.scope).

    Args:
        principal: who acts.
        source: a model class, manager or QuerySet.
        action: an Action value (READ by default).
        include_deleted: also the rows deleted logically.

    Returns:
        The restricted QuerySet.
    """
    return get_policy().scope(principal, _queryset(source), action, include_deleted)


def level(principal, obj, source=None) -> str | None:
    """The AccessLevel of a principal on a row, or None when it cannot see it (AccessPolicy.level; source as there)."""
    return get_policy().level(principal, obj, source)


def check(
    principal, action: str, obj, detail: str | None = None, read_only_detail: str | None = None, source=None
) -> None:
    """
    Stop an action on a row the principal may not perform.

    Args:
        principal: who acts.
        action: an Action value.
        obj: the row.
        detail: message of the NotFound.
        read_only_detail: message of the Forbidden (default: "read_only").
        source: where to look for the row (see AccessPolicy.level).

    Raises:
        NotFound: the principal cannot see the row.
        Forbidden: it can see it, but the action is WRITE and the row is
            read-only for it.
    """
    found = level(principal, obj, source)
    if found is None:
        raise NotFound(detail)
    if action == Action.WRITE and found != AccessLevel.FULL:
        raise Forbidden(read_only_detail)


def get_accessible_or_404(
    source,
    user,
    pk,
    *,
    action: str = Action.READ,
    for_update: bool = False,
    include_deleted: bool = False,
    detail: str | None = None,
    read_only_detail: str | None = None,
):
    """
    Load one object by primary key among those the principal may access.

    Args:
        source: a model class, manager or QuerySet; a QuerySet may carry
            extra filters or select_related.
        user: the principal (usually the user making the request).
        pk: primary key sent by the client (an invalid value, e.g. "abc"
            for an integer key, also gives NotFound).
        action: READ (default) or WRITE: with WRITE a row the principal can
            only read gives Forbidden instead of the object.
        for_update: lock the row with SELECT ... FOR UPDATE (call inside
            transaction.atomic()).
        include_deleted: also find rows deleted logically (needs a
            djkit.db.SoftDeleteQuerySet); before a write, follow it with
            djkit.db.ensure_not_deleted.
        detail: user-facing message of the NotFound.
        read_only_detail: user-facing message of the Forbidden (default:
            "read_only").

    Returns:
        The instance.

    Raises:
        NotFound: the object does not exist or is not visible.
        Forbidden: action WRITE on an object the principal can only read.
    """
    base = _queryset(source)
    queryset = scope(user, base, Action.READ, include_deleted)
    if for_update:
        queryset = queryset.select_for_update()
    try:
        obj = queryset.get(pk=pk)
    except (queryset.model.DoesNotExist, ValueError, TypeError, ValidationError):
        raise NotFound(detail) from None
    if action == Action.WRITE and not scope(user, base.filter(pk=obj.pk), Action.WRITE, include_deleted).exists():
        raise Forbidden(read_only_detail)
    return obj
