"""
Reading one object the current user may access.

get_accessible_or_404 is the single entry point for "load by id" in
services: it applies the data isolation filter (accessible_by) and turns
"missing" and "not yours" into the same NotFound, so the API never reveals
that an object of another user exists.
"""

from django.core.exceptions import ValidationError
from django.db import models

from .errors import NotFound


def get_accessible_or_404(
    source, user, pk, *, for_update: bool = False, include_deleted: bool = False, detail: str | None = None
):
    """
    Load one object by primary key among those the user may access.

    Args:
        source: a model class, manager or QuerySet whose QuerySet has
            accessible_by(user) (see djkit.db.AccessibleQuerySet); a
            QuerySet may carry extra filters or select_related.
        user: the user making the request.
        pk: primary key sent by the client (an invalid value, e.g. "abc"
            for an integer key, also gives NotFound).
        for_update: lock the row with SELECT ... FOR UPDATE (call inside
            transaction.atomic()).
        include_deleted: also find rows deleted logically (needs a
            djkit.db.SoftDeleteQuerySet); before a write, follow it with
            djkit.db.ensure_not_deleted.
        detail: user-facing message of the NotFound.

    Returns:
        The instance.

    Raises:
        NotFound: the object does not exist or is not accessible.
    """
    if isinstance(source, type) and issubclass(source, models.Model):
        queryset = source._default_manager.all()
    else:
        queryset = source.all()
    queryset = queryset.accessible_by(user, include_deleted=True) if include_deleted else queryset.accessible_by(user)
    if for_update:
        queryset = queryset.select_for_update()
    try:
        return queryset.get(pk=pk)
    except (queryset.model.DoesNotExist, ValueError, TypeError, ValidationError):
        raise NotFound(detail) from None
