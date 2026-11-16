"""
Query helpers.

    - AccessibleQuerySet: base QuerySet that restricts rows to those a user
      may access, following a lookup declared on the model (ACCESS_PATH).
      This is the generic "data isolation" layer: every read or write that
      starts from `Model.objects.accessible_by(user)` can never leak rows of
      other users or groups.
    - sum_subquery / count_subquery: correlated subqueries for annotate(),
      returning 0 instead of NULL when there are no rows.
    - date_filter: optional "on or before a date" filter.
    - ensure_unique: raise Conflict when values are already used by other
      rows (checked before saving, to answer 409 instead of 422).
    - SoftDeleteModel / SoftDeleteQuerySet / DeletedFilter: logical
      deletion ("soft delete"): the row stays with is_deleted = True and
      deleted_at set, so every reference to it keeps working and it can
      still be consulted; accessible_by hides it unless asked otherwise.
    - ensure_not_deleted: raise Conflict on a write to a deleted row (it is
      read-only).
"""

from datetime import date
from decimal import Decimal

from datetime import datetime

from django.db import models
from django.db.models import DecimalField, F, Func, IntegerField, OuterRef, Q, Subquery, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from .errors import Conflict
from .messages import get_message


def ensure_unique(
    source: "type[models.Model] | models.QuerySet", values: dict, exclude_pk=None, messages: dict | None = None
) -> None:
    """
    Check that no other row already uses the given values.

    Each field is checked on its own (e.g. email and tax code are two
    separate unique fields), and every field already taken is reported.

    Args:
        source: the model class (every row is searched), or a QuerySet
            when the values must be unique only inside a subset of rows
            (e.g. a partial unique constraint: only the active rows).
        values: {field name: value}, already normalized as they will be
            saved; None values are skipped.
        exclude_pk: primary key of the row being updated, which may keep
            its own values; None when creating.
        messages: optional {field name: message} replacing the generic
            "unique" message of djkit.messages.

    Raises:
        Conflict: errors={field: [message]} for every value already used;
            `detail` joins the distinct messages.
    """
    messages = messages or {}
    if isinstance(source, type) and issubclass(source, models.Model):
        others = source._default_manager.all()
    else:
        others = source.all()
    if exclude_pk is not None:
        others = others.exclude(pk=exclude_pk)
    taken = {
        field: [messages[field] if field in messages else get_message("unique")]
        for field, value in values.items()
        if value is not None and others.filter(**{field: value}).exists()
    }
    if taken:
        distinct = dict.fromkeys(message for field_messages in taken.values() for message in field_messages)
        raise Conflict(" ".join(distinct), errors=taken)


def sum_subquery(
    queryset: models.QuerySet,
    field: str = "amount",
    max_digits: int = 14,
    decimal_places: int = 2,
) -> Coalesce:
    """
    Turn a queryset into a correlated subquery returning the sum of a field,
    to be used inside annotate().

    Args:
        queryset: rows to add up, usually filtered with OuterRef("pk").
        field: name of the numeric field to sum.
        max_digits: precision of the resulting DecimalField.
        decimal_places: scale of the resulting DecimalField (also used for
            the zero returned when there are no rows).

    Returns:
        An expression equal to SUM(field) of the rows, or 0 (with
        `decimal_places` decimals) when there are none.
    """
    summed = queryset.order_by().annotate(_total=Func(F(field), function="SUM")).values("_total")[:1]
    zero = Decimal(0).quantize(Decimal(1).scaleb(-decimal_places))  # e.g. Decimal("0.00")
    return Coalesce(
        Subquery(summed),
        Value(zero),
        output_field=DecimalField(max_digits=max_digits, decimal_places=decimal_places),
    )


def count_subquery(queryset: models.QuerySet) -> Coalesce:
    """
    Turn a queryset into a correlated subquery returning its number of rows.

    Args:
        queryset: rows to count, usually filtered with OuterRef("pk").

    Returns:
        An expression equal to COUNT(*) of the rows (0 when there are none).
    """
    counted = queryset.order_by().annotate(_count=Func(Value(1), function="COUNT")).values("_count")[:1]
    return Coalesce(Subquery(counted), Value(0), output_field=IntegerField())


def date_filter(field: str, as_of: "date | models.Expression | OuterRef | None") -> Q:
    """
    Restrict rows to those dated on or before a reference date.

    Args:
        field: name of the date field, e.g. "due_date".
        as_of: reference date; an expression or OuterRef for a date that
            changes from row to row (e.g. OuterRef("reference_date") inside
            a correlated subquery); None means "every date" (no restriction).

    Returns:
        Q(field__lte=as_of), or an empty Q when as_of is None.
    """
    return Q(**{f"{field}__lte": as_of}) if as_of is not None else Q()


class AccessibleQuerySet(models.QuerySet):
    """
    Base QuerySet for models whose rows belong to a set of users.

    The model declares ACCESS_PATH, the lookup from the row to the users who
    may see and change it, e.g. "members" or "team__members":

        class Invoice(models.Model):
            ACCESS_PATH = "team__members"
            objects = AccessibleQuerySet.as_manager()

    Optionally it declares ACCESS_CONDITIONS, extra lookups applied in the
    same filter() call as ACCESS_PATH, so on a multi-valued relation they
    test the same related row (the membership that grants access), e.g.
    only memberships not deleted:

        ACCESS_PATH = "team__memberships__user"
        ACCESS_CONDITIONS = {"team__memberships__is_deleted": False}
    """

    def accessible_by(self, user) -> "AccessibleQuerySet":
        """
        Restrict the rows to those the user may access (data isolation).

        Args:
            user: the user making the request.

        Returns:
            A QuerySet with only the rows the user may see and change.
        """
        conditions = getattr(self.model, "ACCESS_CONDITIONS", {})
        return self.filter(**{self.model.ACCESS_PATH: user, **conditions})

    def _model(self, name: str):
        """
        Return another model of the same app as this QuerySet's model,
        without importing it (avoids circular imports between models and
        querysets modules).

        Args:
            name: model class name, e.g. "Invoice".

        Returns:
            The model class.
        """
        return self.model._meta.apps.get_model(self.model._meta.app_label, name)


class DeletedFilter(models.TextChoices):
    """
    Which rows a list returns with respect to logical deletion; use it as
    the type of a query parameter (invalid values -> 422).

    Values:
        EXCLUDE -> only the rows not deleted (the default of the interface).
        INCLUDE -> every row, deleted ones included.
        ONLY    -> only the deleted rows.
    """

    EXCLUDE = "exclude", "exclude"
    INCLUDE = "include", "include"
    ONLY = "only", "only"


class SoftDeleteModel(models.Model):
    """
    Abstract base for models deleted logically ("soft delete"): deleting a
    row marks it instead of removing it, so foreign keys that point to it
    stay valid and the history stays complete and can be consulted.

    Use it with SoftDeleteQuerySet (or a subclass) as manager, and add
    deleted_state_constraint to the model's constraints:

        class Customer(SoftDeleteModel):
            ACCESS_PATH = "team__members"
            objects = SoftDeleteQuerySet.as_manager()

            class Meta:
                constraints = [SoftDeleteModel.deleted_state_constraint("customer_deleted_state")]

    The default manager still returns every row (deleted ones included), so
    admin pages, related objects and history queries see them; queries for
    the interface start from accessible_by(user), which hides them unless
    asked otherwise. A deleted row is read-only (ensure_not_deleted).

    Fields:
        is_deleted -> True once the row has been deleted logically.
        deleted_at -> when it was deleted; empty while not deleted.
    """

    is_deleted = models.BooleanField("deleted", default=False)
    deleted_at = models.DateTimeField("deleted at", null=True, blank=True)

    class Meta:
        abstract = True

    @staticmethod
    def deleted_state_constraint(name: str) -> models.CheckConstraint:
        """
        Database check that keeps the two fields consistent: a deleted row
        has deleted_at, a row not deleted has none.

        Args:
            name: constraint name, unique in the database.

        Returns:
            The CheckConstraint to put in the model's Meta.constraints.
        """
        return models.CheckConstraint(
            condition=Q(is_deleted=False, deleted_at__isnull=True) | Q(is_deleted=True, deleted_at__isnull=False),
            name=name,
        )

    def mark_deleted(self, when: datetime | None = None) -> None:
        """
        Delete this row logically and save only the two deletion fields.

        Args:
            when: deletion time; None means now. Pass the same value to
                every row deleted by one operation.
        """
        self.is_deleted = True
        self.deleted_at = when or timezone.now()
        self.save(update_fields=["is_deleted", "deleted_at"])


class SoftDeleteQuerySet(AccessibleQuerySet):
    """
    AccessibleQuerySet for SoftDeleteModel subclasses: deleted rows are
    hidden from accessible_by unless explicitly requested.
    """

    def alive(self) -> "SoftDeleteQuerySet":
        """
        Rows not deleted.

        Returns:
            The rows with is_deleted = False.
        """
        return self.filter(is_deleted=False)

    def deleted(self) -> "SoftDeleteQuerySet":
        """
        Rows deleted logically.

        Returns:
            The rows with is_deleted = True.
        """
        return self.filter(is_deleted=True)

    def filter_deleted(self, mode: str) -> "SoftDeleteQuerySet":
        """
        Apply a DeletedFilter.

        Args:
            mode: a DeletedFilter value ("exclude", "include", "only").

        Returns:
            alive(), every row, or deleted().

        Raises:
            ValueError: unknown mode (a programming error: the API validates
                the parameter before).
        """
        if mode == DeletedFilter.EXCLUDE:
            return self.alive()
        if mode == DeletedFilter.INCLUDE:
            return self.all()
        if mode == DeletedFilter.ONLY:
            return self.deleted()
        raise ValueError(f"Unknown DeletedFilter value: {mode!r}")

    def accessible_by(self, user, include_deleted: bool = False) -> "SoftDeleteQuerySet":
        """
        Restrict the rows to those the user may access, hiding the deleted
        ones (a deleted row then behaves as missing: get_accessible_or_404
        gives NotFound).

        Args:
            user: the user making the request.
            include_deleted: True also returns deleted rows (consultation;
                combine with filter_deleted).

        Returns:
            The accessible rows, without the deleted ones by default.
        """
        rows = super().accessible_by(user)
        return rows if include_deleted else rows.alive()

    def mark_deleted(self, when: datetime | None = None) -> int:
        """
        Delete the rows logically, in one UPDATE (no save() or signals).
        Rows already deleted keep their original deleted_at.

        Args:
            when: deletion time; None means now.

        Returns:
            The number of rows that were not deleted yet and are now.
        """
        return self.alive().update(is_deleted=True, deleted_at=when or timezone.now())


def ensure_not_deleted(obj: SoftDeleteModel, detail: str | None = None) -> None:
    """
    Stop a write to a row deleted logically: it can still be consulted, but
    is read-only.

    Args:
        obj: the row about to be changed.
        detail: user-facing message; the "deleted_read_only" message when
            None.

    Raises:
        Conflict: the row is deleted (409, more telling than a 404 for a row
            the client can see).
    """
    if obj.is_deleted:
        raise Conflict(detail or get_message("deleted_read_only"))
