"""
Deadline notices: tell each user, by email, about the deadlines coming in
the next days (read from a djkit.deadlines.DeadlineRegistry), with
per-user preferences and without repeating what was already notified.

Pieces (the project writes the concrete models, the email and the job):

    - NoticePreferenceBase: abstract model, one row per user and kind of
      deadline: notify it or not, and how many days before.
    - DeadlineNoticeBase: abstract model, one row per user and deadline
      already notified (kind + subject + subject_id), with the due date it
      was notified for. A new due date of the same deadline (a yearly
      renewal, a due date moved) overwrites the row and is notified again;
      prune() deletes the rows of deadlines already passed, so the table
      holds only the deadlines of the notice windows.
    - NoticeRule, rules(defaults, saved): the preferences in force, the
      project defaults filled in for the kinds the user never set.
    - to_notify(registry, user, today, rules, sent): the deadlines to put in
      today's notice.
    - sent_for(model, user): what was already notified to a user.
    - record(model, user, deadlines, when), prune(model, today).

Example of the daily job:

    prune(DeadlineNotice, today)
    for user in recipients:
        found = to_notify(REGISTRY, user, today, rules(DEFAULTS, saved_of(user)), sent_for(DeadlineNotice, user))
        if found:
            send the summary email, then record(DeadlineNotice, user, found, timezone.now())
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta

from django.conf import settings
from django.db import models

from .deadlines import Deadline, DeadlineRegistry

# Upper limit of days_before: a notice more than a year before is a mistake.
MAX_DAYS_BEFORE = 366


@dataclass(frozen=True)
class NoticeRule:
    """
    Whether and how early a kind of deadline is notified to a user.

    Fields:
        enabled     -> notify it.
        days_before -> the notice covers the deadlines due from today to
                       today + days_before (0 = only those due today).
    """

    enabled: bool
    days_before: int


def deadline_key(deadline: Deadline) -> tuple[str, str, int]:
    """
    What identifies a deadline across days: its kind, subject and subject id
    (not the due date, which may move or come back every year).

    Args:
        deadline: the Deadline.

    Returns:
        (kind, subject, subject_id).
    """
    return deadline.kind, deadline.subject, deadline.subject_id


def rules(defaults: dict[str, NoticeRule], saved: Iterable[tuple[str, bool, int]]) -> dict[str, NoticeRule]:
    """
    The preferences in force for a user.

    Args:
        defaults: {kind: NoticeRule} for every kind of the registry.
        saved: (kind, enabled, days_before) the user chose; kinds missing
            from defaults are ignored (a kind no longer registered).

    Returns:
        {kind: NoticeRule}: the defaults, replaced by what the user saved.
    """
    result = dict(defaults)
    for kind, enabled, days_before in saved:
        if kind in result:
            result[kind] = NoticeRule(enabled, days_before)
    return result


def to_notify(
    registry: DeadlineRegistry,
    user,
    today: date,
    notice_rules: dict[str, NoticeRule],
    sent: dict[tuple[str, str, int], date],
) -> list[Deadline]:
    """
    The deadlines of today's notice for a user: those of every enabled kind
    due from today to today + days_before, minus those already notified for
    the same due date.

    Args:
        registry: the deadline registry.
        user: the user (the providers apply their access rules).
        today: reference date.
        notice_rules: {kind: NoticeRule} (rules()).
        sent: {deadline_key: due date notified} (sent_for()).

    Returns:
        The deadlines, by date, then kind and subject id.
    """
    found = []
    for kind, rule in notice_rules.items():
        if not rule.enabled:
            continue
        for deadline in registry.collect(user, today, today + timedelta(days=rule.days_before), kinds=[kind]):
            if sent.get(deadline_key(deadline)) != deadline.due_date:
                found.append(deadline)
    return sorted(found, key=lambda d: (d.due_date, d.kind, d.subject_id))


def sent_for(model: type[models.Model], user) -> dict[tuple[str, str, int], date]:
    """
    What was already notified to a user.

    Args:
        model: a concrete DeadlineNoticeBase subclass.
        user: the user.

    Returns:
        {(kind, subject, subject_id): due date notified}.
    """
    rows = model.objects.filter(user=user).values_list("kind", "subject", "subject_id", "due_date")
    return {(kind, subject, subject_id): due for kind, subject, subject_id, due in rows}


def record(model: type[models.Model], user, deadlines: Iterable[Deadline], when) -> None:
    """
    Remember that deadlines were notified to a user: one row per deadline,
    overwritten when it already exists (new due date, new time).

    Args:
        model: a concrete DeadlineNoticeBase subclass.
        user: the user.
        deadlines: the deadlines notified.
        when: time of the notice.
    """
    for deadline in deadlines:
        kind, subject, subject_id = deadline_key(deadline)
        model.objects.update_or_create(
            user=user,
            kind=kind,
            subject=subject,
            subject_id=subject_id,
            defaults={"due_date": deadline.due_date, "notified_at": when},
        )


def prune(model: type[models.Model], today: date) -> int:
    """
    Forget the notices of deadlines already passed (the table keeps only the
    deadlines of the notice windows).

    Args:
        model: a concrete DeadlineNoticeBase subclass.
        today: reference date.

    Returns:
        The number of rows deleted.
    """
    deleted, _ = model.objects.filter(due_date__lt=today).delete()
    return deleted


class NoticePreferenceBase(models.Model):
    """
    A user's preference for one kind of deadline.

    Fields:
        user        -> the user (PROTECT: delete the rows first).
        kind        -> the kind of deadline (a code of the registry).
        enabled     -> notify it.
        days_before -> how many days before (0..MAX_DAYS_BEFORE).

    Meta: unique (user, kind), constraint "<app>_<class>_unique_kind"; a
    subclass that redefines Meta.constraints must include it again
    (NoticePreferenceBase.unique_constraint(name)), plus usually a check of
    the allowed kinds.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="%(app_label)s_%(class)s_set",
        verbose_name="user",
    )
    kind = models.CharField("kind", max_length=50)
    enabled = models.BooleanField("enabled")
    days_before = models.PositiveSmallIntegerField("days before")

    class Meta:
        abstract = True
        constraints = [
            models.UniqueConstraint(fields=["user", "kind"], name="%(app_label)s_%(class)s_unique_kind"),
        ]

    @staticmethod
    def unique_constraint(name: str) -> models.UniqueConstraint:
        """
        The unique (user, kind) constraint, for subclasses that redefine
        Meta.constraints.

        Args:
            name: constraint name (may use "%(app_label)s" and "%(class)s").

        Returns:
            The UniqueConstraint.
        """
        return models.UniqueConstraint(fields=["user", "kind"], name=name)


class DeadlineNoticeBase(models.Model):
    """
    A deadline already notified to a user (see the module docstring).

    Fields:
        user        -> the user (PROTECT: delete the rows first).
        kind, subject, subject_id -> the deadline (deadline_key).
        due_date    -> the due date it was notified for.
        notified_at -> when.

    Meta: unique (user, kind, subject, subject_id), constraint
    "<app>_<class>_unique_deadline"; a subclass that redefines
    Meta.constraints must include it again
    (DeadlineNoticeBase.unique_constraint(name)).
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="%(app_label)s_%(class)s_set",
        verbose_name="user",
    )
    kind = models.CharField("kind", max_length=50)
    subject = models.CharField("subject", max_length=50)
    subject_id = models.PositiveBigIntegerField("subject id")
    due_date = models.DateField("due date")
    notified_at = models.DateTimeField("notified at")

    class Meta:
        abstract = True
        constraints = [
            models.UniqueConstraint(
                fields=["user", "kind", "subject", "subject_id"], name="%(app_label)s_%(class)s_unique_deadline"
            ),
        ]

    @staticmethod
    def unique_constraint(name: str) -> models.UniqueConstraint:
        """
        The unique (user, kind, subject, subject_id) constraint, for
        subclasses that redefine Meta.constraints.

        Args:
            name: constraint name (may use "%(app_label)s" and "%(class)s").

        Returns:
            The UniqueConstraint.
        """
        return models.UniqueConstraint(fields=["user", "kind", "subject", "subject_id"], name=name)
