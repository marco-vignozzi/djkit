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
"""

from datetime import date
from decimal import Decimal

from django.db import models
from django.db.models import DecimalField, F, Func, IntegerField, Q, Subquery, Value
from django.db.models.functions import Coalesce


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
