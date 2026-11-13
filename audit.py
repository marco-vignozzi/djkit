"""
Audit log: who changed what, and when.

    - AuditAction: CREATE / UPDATE / DELETE.
    - AuditEntryBase: abstract model of one log entry; the project inherits
      it and adds its own context fields (e.g. the group or main resource the
      changed object belongs to).
    - snapshot / diff / to_json_value: JSON-serializable view of an object
      and of the changes between two views.
    - log_write: create one entry; call it inside the same database
      transaction as the write, so the log and the data never diverge.

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
from django.db import models

from .fields import choice_field, choices_constraint
from .messages import get_message

# Fields never written to the log (secrets), unless the setting overrides it.
DEFAULT_EXCLUDED_FIELDS = frozenset({"password"})

# Fields whose values are masked in the log, unless the setting overrides it.
DEFAULT_MASKED_FIELDS = frozenset()


class AuditAction(models.TextChoices):
    """Kind of write operation recorded in the audit log."""

    CREATE = "CREATE", "Create"
    UPDATE = "UPDATE", "Update"
    DELETE = "DELETE", "Delete"


class AuditEntryBase(models.Model):
    """
    One write operation (create / update / delete) made by a user. Entries
    are written only through log_write and never modified.

    Fields:
        actor        -> the user who made the change (None if later deleted
                        or if the change was not made by a logged-in user).
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

    Meta: newest first; a CHECK constraint named
    "<app>_<class>_action_valid" limits `action` to AuditAction (a subclass
    that redefines Meta.constraints must include it again, e.g. with
    AuditEntryBase.action_constraint(name)).
    """

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="%(app_label)s_%(class)s_entries",
        verbose_name="actor",
    )
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
        constraints = [choices_constraint("action", AuditAction.values, "%(app_label)s_%(class)s_action_valid")]

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

    def __str__(self) -> str:
        """Readable label: "<timestamp> <actor> UPDATE Invoice #12"."""
        return f"{self.timestamp:%Y-%m-%d %H:%M} {self.actor} {self.action} {self.model} #{self.object_id}"


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
            None).
        action: an AuditAction value.
        obj: the created, updated or deleted instance.
        changes: what to store; when None, the full snapshot for CREATE and
            DELETE and {} for UPDATE (for updates pass diff(before, after),
            e.g. the value returned by djkit.updates.apply_patch). Masked
            fields are masked before saving.
        **context: values of the extra fields of entry_model.

    Returns:
        The saved entry.
    """
    if changes is None:
        changes = {} if action == AuditAction.UPDATE else snapshot(obj)
    label_length = entry_model._meta.get_field("object_label").max_length
    return entry_model.objects.create(
        actor=actor if getattr(actor, "is_authenticated", False) else None,
        action=action,
        model=type(obj).__name__,
        object_id=obj.pk,
        object_label=str(obj)[:label_length],
        changes=to_json_value(mask_changes(changes)),
        **context,
    )
