"""
Partial update of a model instance (PATCH semantics).

apply_patch assigns only the fields the client sent (typically
`payload.dict(exclude_unset=True)` of an all-optional Ninja schema),
validates the whole object, saves only what changed and returns the diff
ready for the audit log.
"""

from django.core.exceptions import FieldDoesNotExist, ValidationError
from django.db import models

from .audit import diff, snapshot
from .errors import InvalidData
from .messages import get_message


def apply_patch(obj: models.Model, data: dict, allowed: set[str] | None = None) -> dict:
    """
    Apply a partial update to a model instance and save it.

    Args:
        obj: the instance to change (already loaded, e.g. with
            djkit.access.get_accessible_or_404(..., for_update=True)).
        data: {field name: new value}; for a foreign key the value may be
            the related instance or its primary key.
        allowed: field names the caller may change; None allows every
            concrete, non-primary-key field.

    Returns:
        The diff {"attname": [old, new]} of the changed fields, without the
        excluded fields of djkit.audit (e.g. "password"); {} when nothing
        changed (nothing is saved then). A value equal to the current one
        but written differently (Decimal("650") for a stored 650.00) is
        not a change.

    Raises:
        InvalidData: unknown or not allowed field (errors keyed by field),
            or full_clean() failure (field validators, choices, unique
            constraints, model clean()).
    """
    fields = {}
    rejected = {}
    for name in data:
        try:
            field = obj._meta.get_field(name)
        except FieldDoesNotExist:
            field = None
        if field is None or not field.concrete or field.primary_key or (allowed is not None and name not in allowed):
            rejected[name] = [get_message("field_not_editable")]
        else:
            fields[name] = field
    if rejected:
        raise InvalidData(errors=rejected)

    before = snapshot(obj)
    raw_before = {name: getattr(obj, field.attname) for name, field in fields.items()}
    for name, field in fields.items():
        value = data[name]
        if field.is_relation and not isinstance(value, models.Model):
            setattr(obj, field.attname, value)
        else:
            setattr(obj, name, value)

    try:
        obj.full_clean()
    except ValidationError as error:
        raise InvalidData.from_validation_error(error) from error

    changed = [field.attname for name, field in fields.items() if getattr(obj, field.attname) != raw_before[name]]
    if not changed:
        return {}
    obj.save(update_fields=changed)
    # Only the fields whose value really changed: an equal value written
    # differently (Decimal("650") for a stored 650.00) is not a change,
    # although its JSON form differs.
    return {key: values for key, values in diff(before, snapshot(obj)).items() if key in changed}
