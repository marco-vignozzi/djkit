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
"""

from datetime import date
from decimal import Decimal

from django.db import models
from django.db.models import DecimalField, F, Func, IntegerField, Q, Subquery, Value
from django.db.models.functions import Coalesce

from .errors import Conflict

# Message of ensure_unique for a field without a custom message.
DEFAULT_UNIQUE_MESSAGE = "This value is already used."


def ensure_unique(model: type[models.Model], values: dict, exclude_pk=None, messages: dict | None = None) -> None:
    """
    Check that no other row already uses the given values.

    Each field is checked on its own (e.g. email and tax code are two
    separate unique fields), and every field already taken is reported.

    Args:
        model: the model class (or a QuerySet's model) to search.
        values: {field name: value}, already normalized as they will be
            saved; None values are skipped.
        exclude_pk: primary key of the row being updated, which may keep
            its own values; None when creating.
        messages: optional {field name: message} replacing
            DEFAULT_UNIQUE_MESSAGE.

    Raises:
        Conflict: errors={field: [message]} for every value already used;
            `detail` joins the distinct messages.
    """
    messages = messages or {}
    others = model._default_manager.all()
    if exclude_pk is not None:
        others = others.exclude(pk=exclude_pk)
    taken = {
        field: [messages.get(field, DEFAULT_UNIQUE_MESSAGE)]
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


def date_filter(field: str, as_of: date | None) -> Q:
    """
    Restrict rows to those dated on or before a reference date.

    Args:
        field: name of the date field, e.g. "due_date".
        as_of: reference date; None means "every date" (no restriction).

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
    """

    def accessible_by(self, user) -> "AccessibleQuerySet":
        """
        Restrict the rows to those the user may access (data isolation).

        Args:
            user: the user making the request.

        Returns:
            A QuerySet with only the rows the user may see and change.
        """
        return self.filter(**{self.model.ACCESS_PATH: user})

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
