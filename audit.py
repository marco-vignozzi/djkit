"""
Audit log: who changed what, and when.

    - AuditAction: CREATE / UPDATE / DELETE / NOTIFY.
    - AuditEntryBase: abstract model of one log entry; the project inherits
      it and adds its own context fields (e.g. the group or main resource the
      changed object belongs to).
    - snapshot / diff / to_json_value: JSON-serializable view of an object
      and of the changes between two views.
    - log_write: create one entry; call it inside the same database
      transaction as the write, so the log and the data never diverge.
    - last_logged_at: newest entry of each object in a set of entries
      (e.g. to space out the reminders sent about it).
    - rate_limit_until: at most N actions in a time window (e.g. accounts
      created from one client), counted on log entries.
    - cooldown_until / ensure_cooldown: short, hard anti-spam block for
      outbound communications (emails, SMS, webhooks...), based on the log
      itself, so it needs no table of its own. Optional: a project that
      uses it must write a log entry for every send (e.g. a NOTIFY), in the
      same transaction as the send, with the row it is about locked.
      Interval: DJKIT_COOLDOWN_SECONDS (default DEFAULT_COOLDOWN_SECONDS).

Who made an entry: a user (actor_kind USER, actor = the user, or None when
the user was later deleted) or an automatic job (actor_kind BATCH, actor
always None).

Fields listed in the DJKIT_AUDIT_EXCLUDED_FIELDS setting (default
{"password"}) never appear in snapshots or diffs. Fields listed in
DJKIT_AUDIT_MASKED_FIELDS (default: none; e.g. personal data such as
"email" or "phone") appear in the log, but log_write stores their values
as the "audit_masked" message: the entry still says that the field was
set or changed, never its value.
"""

import datetime
import uuid
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import models
from django.db.models import Q
from django.utils import timezone

from .errors import TooManyRequests

from .fields import choice_field, choices_constraint
from .messages import get_message

# Fields never written to the log (secrets), unless the setting overrides it.
DEFAULT_EXCLUDED_FIELDS = frozenset({"password"})

# Fields whose values are masked in the log, unless the setting overrides it.
DEFAULT_MASKED_FIELDS = frozenset()

# Minimum seconds between two sends about the same object (ensure_cooldown),
# unless DJKIT_COOLDOWN_SECONDS overrides it. 60 s is the most common resend
# cooldown of email/OTP services (no official standard exists).
DEFAULT_COOLDOWN_SECONDS = 60


class AuditAction(models.TextChoices):
    """
    Kind of operation recorded in the audit log: a write on a row, or a
    message sent about it (NOTIFY, e.g. an email reminder: the row does not
    change, but the users want to know it was sent).
    """

    CREATE = "CREATE", "Create"
    UPDATE = "UPDATE", "Update"
    DELETE = "DELETE", "Delete"
    NOTIFY = "NOTIFY", "Notify"


class ActorKind(models.TextChoices):
    """
    Who made a log entry: a user, or an automatic job (e.g. a daily command
    that sends reminders), which has no user.
    """

    USER = "USER", "User"
    BATCH = "BATCH", "Batch"


class AuditEntryBase(models.Model):
    """
    One write operation (create / update / delete) made by a user. Entries
    are written only through log_write and never modified.

    Fields:
        actor        -> the user who made the change (None if later deleted
                        or if the change was not made by a logged-in user;
                        always None for BATCH).
        actor_kind   -> USER or BATCH (ActorKind); a database check forbids
                        an actor on a BATCH entry.
                        Reverse accessor on the user: "<app>_<class>_entries"
                        (e.g. user.shop_orderlog_entries), unique for every
                        subclass, so several entry models never clash.
        action       -> CREATE, UPDATE or DELETE.
        model        -> name of the changed model, e.g. "Invoice".
        object_id    -> primary key of the changed row.
        object_label -> readable label of the row at the time (str(obj)).
        changes      -> JSON {"field": [old, new], ...} for UPDATE, the full
                        snapshot for CREATE / DELETE.
        timestamp    -> when it happened.

    Meta: newest first; CHECK constraints "<app>_<class>_action_valid"
    (`action` in AuditAction), "<app>_<class>_actor_kind_valid" (`actor_kind`
    in ActorKind) and "<app>_<class>_batch_without_actor" (a subclass that
    redefines Meta.constraints must include them again, with
    AuditEntryBase.action_constraint(name) and
    AuditEntryBase.actor_kind_constraints(prefix)).
    """

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="%(app_label)s_%(class)s_entries",
        verbose_name="actor",
    )
    actor_kind = choice_field("actor kind", ActorKind, default=ActorKind.USER)
    action = choice_field("action", AuditAction)
    model = models.CharField("model", max_length=100)
    object_id = models.PositiveBigIntegerField("object id", null=True, blank=True)
    object_label = models.CharField("object", max_length=300, blank=True)
    changes = models.JSONField("changes", default=dict, blank=True)
    timestamp = models.DateTimeField("timestamp", auto_now_add=True)

    class Meta:
        abstract = True
        verbose_name = "audit log entry"
        verbose_name_plural = "audit log"
        ordering = ["-timestamp", "-id"]
        constraints = [
            choices_constraint("action", AuditAction.values, "%(app_label)s_%(class)s_action_valid"),
            choices_constraint("actor_kind", ActorKind.values, "%(app_label)s_%(class)s_actor_kind_valid"),
            models.CheckConstraint(
                condition=~Q(actor_kind=ActorKind.BATCH) | Q(actor__isnull=True),
                name="%(app_label)s_%(class)s_batch_without_actor",
            ),
        ]

    @staticmethod
    def action_constraint(name: str) -> models.CheckConstraint:
        """
        CHECK constraint limiting `action` to AuditAction, for subclasses
        that redefine Meta.constraints.

        Args:
            name: constraint name (may use "%(app_label)s" and "%(class)s").

        Returns:
            The CheckConstraint.
        """
        return choices_constraint("action", AuditAction.values, name)

    @staticmethod
    def actor_kind_constraints(prefix: str) -> list[models.CheckConstraint]:
        """
        CHECK constraints on actor_kind, for subclasses that redefine
        Meta.constraints: the value is in ActorKind, and a BATCH entry has
        no actor.

        Args:
            prefix: start of the constraint names (e.g. "auditlog"):
                "<prefix>_actor_kind_valid" and "<prefix>_batch_without_actor".

        Returns:
            The two CheckConstraints.
        """
        return [
            choices_constraint("actor_kind", ActorKind.values, f"{prefix}_actor_kind_valid"),
            models.CheckConstraint(
                condition=~Q(actor_kind=ActorKind.BATCH) | Q(actor__isnull=True),
                name=f"{prefix}_batch_without_actor",
            ),
        ]

    def __str__(self) -> str:
        """Readable label: "<timestamp> <actor> UPDATE Invoice #12" (BATCH instead of the actor for a job)."""
        who = ActorKind.BATCH.value if self.actor_kind == ActorKind.BATCH else self.actor
        return f"{self.timestamp:%Y-%m-%d %H:%M} {who} {self.action} {self.model} #{self.object_id}"


def excluded_fields() -> frozenset[str]:
    """
    Field names never written to the log.

    Returns:
        settings.DJKIT_AUDIT_EXCLUDED_FIELDS, or DEFAULT_EXCLUDED_FIELDS.
    """
    return frozenset(getattr(settings, "DJKIT_AUDIT_EXCLUDED_FIELDS", DEFAULT_EXCLUDED_FIELDS))


def masked_fields() -> frozenset[str]:
    """
    Field names whose values are masked in the log.

    Returns:
        settings.DJKIT_AUDIT_MASKED_FIELDS, or DEFAULT_MASKED_FIELDS. Names
        are matched in every model (e.g. "email" masks the email of every
        model that has one).
    """
    return frozenset(getattr(settings, "DJKIT_AUDIT_MASKED_FIELDS", DEFAULT_MASKED_FIELDS))


def mask_value(value):
    """
    Masked form of one value of a masked field.

    Args:
        value: the value (already JSON-serializable or not).

    Returns:
        The value unchanged when empty (None or ""), so the log still shows
        that the field was empty; otherwise the "audit_masked" message.
    """
    return value if value in (None, "") else get_message("audit_masked")


def mask_changes(changes: dict) -> dict:
    """
    Mask the values of the masked fields in a snapshot or a diff.

    Args:
        changes: {field: value} (snapshot) or {field: [old, new]} (diff);
            other keys (e.g. extra information added by the caller) are
            kept as they are.

    Returns:
        A new dict where every masked field has its value (or both values
        of a diff pair) replaced by mask_value.
    """
    masked = masked_fields()
    result = {}
    for key, value in changes.items():
        if key not in masked:
            result[key] = value
        elif isinstance(value, (list, tuple)):
            result[key] = [mask_value(item) for item in value]
        else:
            result[key] = mask_value(value)
    return result


def to_json_value(value):
    """
    Convert a field value into a JSON-serializable value.

    Args:
        value: any value read from a model field.

    Returns:
        Decimal -> str ("650.00", no precision lost); date / datetime /
        time -> ISO string; UUID -> str; model instance -> its pk; list,
        tuple, set and dict -> converted element by element; anything else
        unchanged.
    """
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (datetime.date, datetime.datetime, datetime.time)):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, models.Model):
        return value.pk
    if isinstance(value, dict):
        return {key: to_json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [to_json_value(item) for item in value]
    return value


def snapshot(obj: models.Model, fields=None) -> dict:
    """
    JSON-serializable view of an object's concrete fields.

    Args:
        obj: a model instance.
        fields: optional names to keep (field name or attname, e.g.
            "team" or "team_id"); None keeps every field.

    Returns:
        {attname: value} for every concrete field except the primary key and
        the excluded fields (DJKIT_AUDIT_EXCLUDED_FIELDS); foreign keys
        appear as "<name>_id" with the related pk.
    """
    skip = excluded_fields()
    wanted = set(fields) if fields is not None else None
    data = {}
    for field in obj._meta.concrete_fields:
        if field.primary_key or field.name in skip or field.attname in skip:
            continue
        if wanted is not None and field.name not in wanted and field.attname not in wanted:
            continue
        data[field.attname] = to_json_value(getattr(obj, field.attname))
    return data


def diff(before: dict, after: dict) -> dict:
    """
    Changes between two snapshots.

    Args:
        before: snapshot taken before the change.
        after: snapshot taken after the change.

    Returns:
        {"field": [old, new]} for every key whose value differs (a key
        missing on one side counts as None).
    """
    return {
        key: [before.get(key), after.get(key)]
        for key in sorted(before.keys() | after.keys())
        if before.get(key) != after.get(key)
    }


def log_write(
    entry_model: type[AuditEntryBase],
    actor,
    action: str,
    obj: models.Model,
    changes: dict | None = None,
    *,
    actor_kind: str = ActorKind.USER,
    **context,
) -> AuditEntryBase:
    """
    Record one write operation.

    Call it inside the same transaction as the write. For DELETE call it
    before obj.delete(), while obj.pk is still set. The values of the
    masked fields (DJKIT_AUDIT_MASKED_FIELDS) are masked here, so callers
    pass real snapshots and diffs (a diff computed on masked values would
    miss the changes).

    Args:
        entry_model: the project's concrete subclass of AuditEntryBase.
        actor: the user making the change (anonymous users are stored as
            None); must be None when actor_kind is BATCH.
        action: an AuditAction value.
        obj: the created, updated or deleted instance.
        changes: what to store; when None, the full snapshot for CREATE and
            DELETE and {} for UPDATE and NOTIFY (for updates pass diff(before, after),
            e.g. the value returned by djkit.updates.apply_patch). Masked
            fields are masked before saving.
        actor_kind: ActorKind.USER (default) or ActorKind.BATCH for an
            automatic job.
        **context: values of the extra fields of entry_model.

    Returns:
        The saved entry.

    Raises:
        ValueError: actor_kind is BATCH but an actor was given (a bug: the
            entry would say both "a job" and "this user").
    """
    if actor_kind == ActorKind.BATCH and actor is not None:
        raise ValueError("A BATCH audit entry has no actor: pass actor=None.")
    if changes is None:
        changes = snapshot(obj) if action in (AuditAction.CREATE, AuditAction.DELETE) else {}
    label_length = entry_model._meta.get_field("object_label").max_length
    return entry_model.objects.create(
        actor=actor if getattr(actor, "is_authenticated", False) else None,
        actor_kind=actor_kind,
        action=action,
        model=type(obj).__name__,
        object_id=obj.pk,
        object_label=str(obj)[:label_length],
        changes=to_json_value(mask_changes(changes)),
        **context,
    )


def last_logged_at(entries: models.QuerySet, object_ids) -> dict:
    """
    When each object was last mentioned in a set of log entries, in one
    query: e.g. the last reminder sent to each customer, to space them out.

    Args:
        entries: entries of a concrete AuditEntryBase subclass, already
            filtered by the caller (model, action, changes...).
        object_ids: the primary keys to look for.

    Returns:
        {object_id: timestamp of its newest entry}; objects without entries
        are missing.
    """
    rows = (
        entries.filter(object_id__in=list(object_ids))
        .values("object_id")
        .annotate(last=models.Max("timestamp"))
        .values_list("object_id", "last")
        .order_by()
    )
    return dict(rows)


def rate_limit_until(entries: models.QuerySet, limit: int, window_seconds: int):
    """
    Until when a new action is blocked by a rate limit: at most `limit`
    actions in any `window_seconds`, the actions being the given entries
    (e.g. the CREATE entries of the accounts made from one client).

    Args:
        entries: the entries that count, already filtered by the caller.
        limit: actions allowed in the window (>= 1).
        window_seconds: the window.

    Returns:
        The time the oldest entry that still counts leaves the window, or
        None when an action is allowed now (fewer than `limit` entries in
        the last window_seconds).
    """
    since = timezone.now() - datetime.timedelta(seconds=window_seconds)
    recent = list(entries.filter(timestamp__gt=since).order_by("-timestamp").values_list("timestamp", flat=True)[:limit])
    if len(recent) < limit:
        return None
    return recent[-1] + datetime.timedelta(seconds=window_seconds)


def cooldown_seconds() -> int:
    """
    Minimum seconds between two sends about the same object.

    Returns:
        settings.DJKIT_COOLDOWN_SECONDS, or DEFAULT_COOLDOWN_SECONDS.

    Raises:
        ImproperlyConfigured: the setting is negative.
    """
    seconds = getattr(settings, "DJKIT_COOLDOWN_SECONDS", DEFAULT_COOLDOWN_SECONDS)
    if seconds < 0:
        raise ImproperlyConfigured("DJKIT_COOLDOWN_SECONDS must be 0 or more.")
    return seconds


def cooldown_until(entries: models.QuerySet, object_id: int, seconds: int | None = None):
    """
    Until when a new send about an object is blocked by the cooldown.

    Args:
        entries: the entries that count as sends (e.g. the NOTIFY entries of
            one model), already filtered by the caller.
        object_id: primary key of the object the send is about.
        seconds: the interval; cooldown_seconds() when None (0 = no block).

    Returns:
        The time the block ends, or None when a send is allowed now (no
        entry, or the newest one is old enough).
    """
    seconds = cooldown_seconds() if seconds is None else seconds
    last = last_logged_at(entries, [object_id]).get(object_id)
    if last is None or seconds == 0:
        return None
    end = last + datetime.timedelta(seconds=seconds)
    return end if timezone.now() < end else None


def ensure_cooldown(entries: models.QuerySet, object_id: int, seconds: int | None = None) -> None:
    """
    Stop a send that comes too soon after the previous one about the same
    object (double click, retry, two users at the same moment).

    Call it inside the transaction that sends and logs, with the object's
    row locked (select_for_update), so two simultaneous requests cannot
    both pass the check.

    Args:
        entries, object_id, seconds: see cooldown_until.

    Raises:
        TooManyRequests: within the interval; `retry_at` says when it ends.
    """
    end = cooldown_until(entries, object_id, seconds)
    if end is not None:
        raise TooManyRequests(end)
