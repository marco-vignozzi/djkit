"""
Text catalog: every user-facing text of a project, looked up by key.

A project keeps all the texts its interface shows in one nested dict and
wraps it in a TextCatalog; code refers to a text only by its dotted key, so
no sentence is written in services, models or frontend:

    CATALOG = TextCatalog({
        "api": {"order": {"not_found": "Order not found."}},
        "ui": {"common": {"save": "Save"}},
        "value": {"OrderStatus": {"OPEN": "Open"}},
    })
    CATALOG.text("api.order.not_found")             # -> "Order not found."
    CATALOG.text("api.cart.items", count=1)         # plural leaf, see below

Rules (fail loudly: a mistake shows up at once, never as an empty text):
    - an unknown key raises UnknownTextKey;
    - a placeholder without a value raises MissingTextParameter;
    - a leaf is a string, or a plural leaf {"one": "...", "other": "..."}
      chosen by the "count" parameter (1 -> "one", anything else -> "other").

Serving a catalog to a frontend:
    - catalog_response(request, data) -> HttpResponse: the data as JSON with
      an ETag; answers 304 when the client already has that version.
    - typescript_keys(catalog, sections) -> str: a TypeScript module with
      the union type of the keys (manage.py export_text_types).

Settings:
    DJKIT_TEXT_CATALOG          dotted path of the project's TextCatalog
                                (used by export_text_types).
    DJKIT_TEXT_PUBLIC_SECTIONS  top-level sections sent to the frontend and
                                exported as types (default: ["ui", "value"]).
"""

import hashlib
import json
import string
from collections.abc import Iterable

from django.conf import settings
from django.http import HttpResponse, HttpResponseNotModified, JsonResponse
from django.utils.module_loading import import_string

# Keys of a plural leaf.
PLURAL_FORMS = frozenset({"one", "other"})

# Default sections of a catalog that the frontend receives.
DEFAULT_PUBLIC_SECTIONS = ("ui", "value")


class UnknownTextKey(KeyError):
    """A text key that is not in the catalog (a bug of the caller)."""


class MissingTextParameter(KeyError):
    """A placeholder of a text called without its value (a bug of the caller)."""


def is_plural(value) -> bool:
    """
    Whether a catalog value is a plural leaf.

    Args:
        value: a value of the catalog.

    Returns:
        True for a dict whose keys are exactly "one" and "other".
    """
    return isinstance(value, dict) and set(value) == PLURAL_FORMS


def placeholders(text: str) -> set[str]:
    """
    Names of the str.format placeholders of a text.

    Args:
        text: e.g. "{count} items in {place}".

    Returns:
        {"count", "place"}.
    """
    return {name for _, name, _, _ in string.Formatter().parse(text) if name}


class TextCatalog:
    """
    A nested dict of texts with dotted keys.

    Args:
        data: {section: {group: {name: text or plural leaf}}}, any depth.
            Keys are English identifiers; texts are in the project's
            language.

    Raises:
        TypeError: a leaf that is neither a string nor a plural leaf of two
            strings.
    """

    def __init__(self, data: dict):
        self._data = data
        self._flat: dict[str, str | dict] = {}
        self._flatten(data, "")

    def _flatten(self, node: dict, prefix: str) -> None:
        """Fill self._flat with "a.b.c" -> leaf, checking every leaf."""
        for name, value in node.items():
            key = f"{prefix}{name}"
            if isinstance(value, str) or (is_plural(value) and all(isinstance(v, str) for v in value.values())):
                self._flat[key] = value
            elif isinstance(value, dict) and value:
                self._flatten(value, f"{key}.")
            else:
                raise TypeError(f"Invalid text at {key!r}: expected a string or a plural leaf")

    def text(self, key: str, **params) -> str:
        """
        One text, with its placeholders filled in.

        Args:
            key: dotted key, e.g. "api.order.not_found".
            **params: values of the placeholders; "count" also chooses the
                form of a plural leaf.

        Returns:
            The text.

        Raises:
            UnknownTextKey: the key is not in the catalog.
            MissingTextParameter: a placeholder has no value (or a plural
                leaf is used without count).
        """
        try:
            value = self._flat[key]
        except KeyError:
            raise UnknownTextKey(key) from None
        if isinstance(value, dict):
            if "count" not in params:
                raise MissingTextParameter(f"{key}: plural text needs 'count'")
            value = value["one"] if params["count"] == 1 else value["other"]
        missing = placeholders(value) - set(params)
        if missing:
            raise MissingTextParameter(f"{key}: missing {', '.join(sorted(missing))}")
        return value.format(**params)

    def keys(self, sections: Iterable[str] | None = None) -> list[str]:
        """
        Every key of the catalog, sorted.

        Args:
            sections: top-level sections to keep; None keeps all.

        Returns:
            The dotted keys of the leaves.
        """
        wanted = None if sections is None else tuple(f"{s}." for s in sections)
        return sorted(k for k in self._flat if wanted is None or k.startswith(wanted))

    def section(self, name: str) -> dict:
        """
        One top-level section, as nested data.

        Args:
            name: e.g. "ui".

        Returns:
            The nested dict of that section.

        Raises:
            UnknownTextKey: no such section.
        """
        try:
            return self._data[name]
        except KeyError:
            raise UnknownTextKey(name) from None

    def public_data(self, sections: Iterable[str] | None = None) -> dict:
        """
        The sections sent to the frontend, with their version.

        Args:
            sections: section names; None uses DJKIT_TEXT_PUBLIC_SECTIONS.

        Returns:
            {"version": short hash of the content, <section>: data, ...}.
        """
        names = public_sections() if sections is None else list(sections)
        data = {name: self.section(name) for name in names}
        return {"version": content_hash(data), **data}


def public_sections() -> list[str]:
    """The sections of DJKIT_TEXT_PUBLIC_SECTIONS (default ["ui", "value"])."""
    return list(getattr(settings, "DJKIT_TEXT_PUBLIC_SECTIONS", DEFAULT_PUBLIC_SECTIONS))


def project_catalog() -> TextCatalog:
    """
    The project's catalog, from the DJKIT_TEXT_CATALOG setting.

    Returns:
        The TextCatalog the setting points to.

    Raises:
        AttributeError: the setting is missing (the project must give it).
        ImportError: the dotted path is wrong.
    """
    return import_string(settings.DJKIT_TEXT_CATALOG)


def content_hash(data) -> str:
    """
    Short, stable hash of JSON-serializable data (catalog version, ETag).

    Args:
        data: the data.

    Returns:
        The first 16 hex digits of the SHA-256 of its sorted JSON.
    """
    encoded = json.dumps(data, sort_keys=True, ensure_ascii=False).encode()
    return hashlib.sha256(encoded).hexdigest()[:16]


def catalog_response(request, data: dict) -> HttpResponse:
    """
    Serve catalog data as JSON with an ETag, so browsers (and an offline
    app) keep it in cache and download it again only when it changes.

    Args:
        request: the HttpRequest (its If-None-Match header is checked).
        data: the data to send, e.g. TextCatalog.public_data().

    Returns:
        200 with the JSON and the ETag, or 304 when If-None-Match matches.
    """
    etag = f'"{content_hash(data)}"'
    if request.headers.get("If-None-Match") == etag:
        response = HttpResponseNotModified()
    else:
        response = JsonResponse(data, json_dumps_params={"ensure_ascii": False})
    response["ETag"] = etag
    response["Cache-Control"] = "no-cache"  # always revalidate with the ETag
    return response


def typescript_keys(catalog: TextCatalog, sections: Iterable[str] | None = None) -> str:
    """
    A TypeScript module with the keys of the catalog, so a frontend that
    uses a missing key fails at compile time.

    Args:
        catalog: the catalog.
        sections: sections to export; None uses DJKIT_TEXT_PUBLIC_SECTIONS.

    Returns:
        The source of the module: `export type TextKey = "a.b" | ...;`
        and `export const TEXT_KEYS: readonly TextKey[]`.
    """
    keys = catalog.keys(public_sections() if sections is None else sections)
    union = "\n".join(f'  | "{key}"' for key in keys) or '  never'
    listed = "\n".join(f'  "{key}",' for key in keys)
    return (
        "// Generated by `manage.py export_text_types`: do not edit by hand.\n"
        "// Keys of the text catalog served by the backend.\n\n"
        f"export type TextKey =\n{union};\n\n"
        f"export const TEXT_KEYS: readonly TextKey[] = [\n{listed}\n];\n"
    )
