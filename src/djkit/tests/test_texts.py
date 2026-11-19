"""
Tests for djkit.texts (TextCatalog, catalog_response, typescript_keys) and
the export_text_types command, on a small catalog defined here.

Run with: python manage.py test djkit.tests.test_texts
"""

import tempfile
from io import StringIO
from pathlib import Path

from django.core.management import call_command
from django.test import RequestFactory, SimpleTestCase, override_settings

from djkit.texts import (
    MissingTextParameter,
    TextCatalog,
    UnknownTextKey,
    catalog_response,
    placeholders,
    typescript_keys,
)

# Catalog used by these tests (and by export_text_types through the setting).
SAMPLE = TextCatalog(
    {
        "api": {"order": {"not_found": "Order not found.", "too_many": "At most {limit} orders."}},
        "ui": {"common": {"save": "Save"}, "cart": {"items": {"one": "{count} item", "other": "{count} items"}}},
        "value": {"OrderStatus": {"OPEN": "Open", "CLOSED": "Closed"}},
    }
)


class TextCatalogTests(SimpleTestCase):
    """TextCatalog finds texts by dotted key and fails loudly on mistakes."""

    def test_text_by_dotted_key_with_placeholders(self):
        """'api.order.not_found' -> its text; 'api.order.too_many' with limit=3 -> 'At most 3 orders.'."""
        self.assertEqual(SAMPLE.text("api.order.not_found"), "Order not found.")
        self.assertEqual(SAMPLE.text("api.order.too_many", limit=3), "At most 3 orders.")

    def test_unknown_key_and_missing_placeholder_raise(self):
        """Unknown key -> UnknownTextKey; too_many without limit -> MissingTextParameter."""
        with self.assertRaises(UnknownTextKey):
            SAMPLE.text("api.order.missing")
        with self.assertRaises(MissingTextParameter):
            SAMPLE.text("api.order.too_many")

    def test_plural_leaf_chooses_by_count(self):
        """count 1 -> '1 item'; count 0 and 2 -> 'items'; no count -> MissingTextParameter."""
        self.assertEqual(SAMPLE.text("ui.cart.items", count=1), "1 item")
        self.assertEqual(SAMPLE.text("ui.cart.items", count=0), "0 items")
        self.assertEqual(SAMPLE.text("ui.cart.items", count=2), "2 items")
        with self.assertRaises(MissingTextParameter):
            SAMPLE.text("ui.cart.items")

    def test_group_key_is_not_a_text(self):
        """'ui.common' (a group, not a leaf) -> UnknownTextKey."""
        with self.assertRaises(UnknownTextKey):
            SAMPLE.text("ui.common")

    def test_invalid_leaf_is_rejected_at_build_time(self):
        """A number, an empty group or a plural with a non-text form -> TypeError when the catalog is built."""
        for data in ({"a": 1}, {"a": {}}, {"a": {"one": "x", "other": 2}}):
            with self.subTest(data=data), self.assertRaises(TypeError):
                TextCatalog(data)

    def test_keys_by_section(self):
        """keys(["value"]) -> the two OrderStatus keys; keys() -> all 6, sorted."""
        self.assertEqual(SAMPLE.keys(["value"]), ["value.OrderStatus.CLOSED", "value.OrderStatus.OPEN"])
        self.assertEqual(len(SAMPLE.keys()), 6)
        self.assertEqual(SAMPLE.keys(), sorted(SAMPLE.keys()))

    def test_public_data_has_only_the_public_sections_and_a_version(self):
        """public_data(["ui", "value"]) -> version + ui + value, no api; same data -> same version."""
        data = SAMPLE.public_data(["ui", "value"])
        self.assertEqual(set(data), {"version", "ui", "value"})
        self.assertEqual(data["version"], SAMPLE.public_data(["ui", "value"])["version"])

    def test_placeholders(self):
        """'{count} items in {place}' -> {'count', 'place'}."""
        self.assertEqual(placeholders("{count} items in {place}"), {"count", "place"})


class CatalogResponseTests(SimpleTestCase):
    """catalog_response sends JSON with an ETag and answers 304 when unchanged."""

    def test_etag_and_not_modified(self):
        """First call 200 with ETag; same ETag in If-None-Match -> 304; another ETag -> 200."""
        data = SAMPLE.public_data(["ui"])
        first = catalog_response(RequestFactory().get("/texts"), data)
        self.assertEqual(first.status_code, 200)
        etag = first["ETag"]
        again = catalog_response(RequestFactory().get("/texts", HTTP_IF_NONE_MATCH=etag), data)
        self.assertEqual((again.status_code, again["ETag"]), (304, etag))
        other = catalog_response(RequestFactory().get("/texts", HTTP_IF_NONE_MATCH='"old"'), data)
        self.assertEqual(other.status_code, 200)


@override_settings(DJKIT_TEXT_CATALOG="djkit.tests.test_texts.SAMPLE", DJKIT_TEXT_PUBLIC_SECTIONS=["ui", "value"])
class TypescriptExportTests(SimpleTestCase):
    """typescript_keys and export_text_types write the union type of the public keys."""

    def test_module_lists_public_keys_only(self):
        """The module has 'ui.common.save' and 'value.OrderStatus.OPEN', not 'api.order.not_found'."""
        source = typescript_keys(SAMPLE)
        self.assertIn('| "ui.common.save"', source)
        self.assertIn('"value.OrderStatus.OPEN",', source)
        self.assertNotIn("api.order", source)
        self.assertTrue(source.startswith("// Generated by `manage.py export_text_types`"))

    def test_command_writes_the_file_or_prints_it(self):
        """--output writes the module; without it the module is printed."""
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "texts" / "keys.ts"
            call_command("export_text_types", output=str(target), stdout=StringIO())
            self.assertEqual(target.read_text(encoding="utf-8"), typescript_keys(SAMPLE))
        printed = StringIO()
        call_command("export_text_types", stdout=printed)
        self.assertEqual(printed.getvalue(), typescript_keys(SAMPLE))
