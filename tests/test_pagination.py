"""
Tests for djkit.pagination (page_of, PageNumber).

Run with: python manage.py test djkit.tests.test_pagination
"""

from django.contrib.auth.models import Group
from django.test import TestCase, override_settings

from djkit.errors import InvalidData
from djkit.pagination import default_page_size, page_of
from djkit.testing.api import ApiTestCase


@override_settings(DJKIT_MESSAGES={})
class PageOfTests(TestCase):
    """page_of: one page of a list or of an ordered QuerySet, loud errors otherwise."""

    def test_pages_of_a_list(self):
        """60 rows, size 25: page 1 = 1..25, page 3 = 51..60, 3 pages, count 60."""
        rows = list(range(1, 61))
        first = page_of(rows, 1, 25)
        last = page_of(rows, 3, 25)
        self.assertEqual((first.items, first.count, first.pages), (list(range(1, 26)), 60, 3))
        self.assertEqual((last.items, last.page, last.size), (list(range(51, 61)), 3, 25))

    def test_default_size_and_empty_list(self):
        """No size -> DJKIT_PAGE_SIZE (25); an empty list has page 1 of 1."""
        page = page_of([])
        self.assertEqual((page.items, page.count, page.page, page.size, page.pages), ([], 0, 1, 25, 1))

    def test_size_not_allowed_is_invalid_data_on_size(self):
        """size 30 -> InvalidData on "size" listing the allowed sizes."""
        with self.assertRaises(InvalidData) as caught:
            page_of([1, 2, 3], 1, 30)
        self.assertEqual(caught.exception.extra["errors"], {"size": ["Rows per page must be one of: 10, 25, 50, 100."]})

    def test_page_out_of_range_is_invalid_data_on_page(self):
        """3 rows, size 10: page 2 and page 0 -> InvalidData on "page"."""
        for page in (0, 2):
            with self.subTest(page=page), self.assertRaises(InvalidData) as caught:
                page_of([1, 2, 3], page, 10)
            self.assertEqual(caught.exception.extra["errors"], {"page": ["This page does not exist: the pages are 1."]})

    def test_ordered_queryset_one_query_per_page_plus_count(self):
        """12 groups by name, size 10: page 2 has the last 2; an unordered QuerySet -> ValueError."""
        Group.objects.bulk_create(Group(name=f"g{n:02}") for n in range(12))
        page = page_of(Group.objects.order_by("name"), 2, 10)
        self.assertEqual([group.name for group in page.items], ["g10", "g11"])
        self.assertEqual((page.count, page.pages), (12, 2))
        with self.assertRaises(ValueError):
            page_of(Group.objects.all(), 1, 10)

    @override_settings(DJKIT_PAGE_SIZES=(5, 20), DJKIT_PAGE_SIZE=5)
    def test_sizes_from_the_settings(self):
        """DJKIT_PAGE_SIZES (5, 20) and DJKIT_PAGE_SIZE 5: default 5, 20 allowed, 25 refused."""
        self.assertEqual(page_of(list(range(30))).size, 5)
        self.assertEqual(page_of(list(range(30)), 1, 20).size, 20)
        with self.assertRaises(InvalidData):
            page_of(list(range(30)), 1, 25)

    @override_settings(DJKIT_PAGE_SIZES=(10, 50), DJKIT_PAGE_SIZE=25)
    def test_default_size_outside_the_sizes_is_a_wrong_setting(self):
        """DJKIT_PAGE_SIZE 25 not in (10, 50) -> ValueError (a wrong configuration, not a user error)."""
        with self.assertRaises(ValueError):
            default_page_size()


@override_settings(ROOT_URLCONF="djkit.tests.urls", DJKIT_MESSAGES={})
class PageNumberApiTests(ApiTestCase):
    """PageNumber on a Ninja endpoint: ?page= and ?size=, answer {items, count, page, size, pages}."""

    def test_page_and_size_from_the_query(self):
        """?page=2&size=50 on 60 numbers -> items 51..60, count 60, page 2, size 50, pages 2."""
        response = self.client.get("/api/public/numbers?page=2&size=50")
        self.assertStatus(response, 200)
        self.assertEqual(response.json(), {"items": list(range(51, 61)), "count": 60, "page": 2, "size": 50, "pages": 2})

    def test_defaults(self):
        """No parameters -> page 1 of 25 rows."""
        body = self.client.get("/api/public/numbers").json()
        self.assertEqual((body["items"][0], len(body["items"]), body["size"], body["pages"]), (1, 25, 25, 3))

    def test_wrong_values_are_422_on_their_field(self):
        """size 7 -> 422 on "size"; page 9 -> 422 on "page"; page "x" -> 422 (schema)."""
        for query, field in (("size=7", "size"), ("page=9", "page"), ("page=x", "page")):
            with self.subTest(query=query):
                response = self.client.get(f"/api/public/numbers?{query}")
                self.assertStatus(response, 422)
                self.assertIn(field, response.json()["errors"])
