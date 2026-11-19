"""
Pagination by page number for Django Ninja lists.

Purpose:
    One way to page every long list, matching what a user interface shows:
    "page 3, 25 rows per page" instead of raw limit / offset, with a fixed
    set of page sizes and loud errors for what can only be a bug of the
    caller.

Public API:
    - PageNumber: a Django Ninja paginator. Query parameters ?page= (from 1,
      default 1) and ?size= (one of DJKIT_PAGE_SIZES, default
      DJKIT_PAGE_SIZE); answer {items, count, page, size, pages}.
        @router.get("", response=list[ItemOut])
        @paginate(PageNumber)
        def list_items(request): return Item.objects.order_by("-created", "pk")
    - page_of(rows, page, size) -> Page: the same slicing for a service or a
      command, without Ninja.
    - Page: dataclass with items, count, page, size, pages.

Rules (fail loudly):
    - a size outside DJKIT_PAGE_SIZES -> InvalidData on "size"
      (message key "page_size_not_allowed");
    - a page after the last one (with at least one row) -> InvalidData on
      "page" ("page_out_of_range"); page 1 of an empty list is fine;
    - an unordered QuerySet -> ValueError: its pages would overlap or skip
      rows (a bug of the caller, never a user error).

Settings:
    DJKIT_PAGE_SIZES  allowed page sizes (default (10, 25, 50, 100))
    DJKIT_PAGE_SIZE   default page size (default 25; must be in DJKIT_PAGE_SIZES)
"""

from dataclasses import dataclass
from math import ceil
from typing import Any

from django.conf import settings
from django.db.models import QuerySet
from ninja import Field, Schema
from ninja.pagination import PaginationBase

from .errors import InvalidData
from .messages import get_message

DEFAULT_PAGE_SIZES = (10, 25, 50, 100)
DEFAULT_PAGE_SIZE = 25


def page_sizes() -> tuple[int, ...]:
    """The allowed page sizes (DJKIT_PAGE_SIZES)."""
    return tuple(getattr(settings, "DJKIT_PAGE_SIZES", DEFAULT_PAGE_SIZES))


def default_page_size() -> int:
    """
    The default page size (DJKIT_PAGE_SIZE).

    Raises:
        ValueError: when it is not one of the allowed sizes (a wrong setting).
    """
    size = getattr(settings, "DJKIT_PAGE_SIZE", DEFAULT_PAGE_SIZE)
    if size not in page_sizes():
        raise ValueError(f"DJKIT_PAGE_SIZE {size} is not one of DJKIT_PAGE_SIZES {page_sizes()}")
    return size


@dataclass(frozen=True)
class Page:
    """
    One page of a list.

    Attributes:
        items: the rows of the page (a sliced QuerySet or a list).
        count: rows in the whole list.
        page: number of this page, from 1.
        size: rows per page.
        pages: number of pages (at least 1).
    """

    items: Any
    count: int
    page: int
    size: int
    pages: int


def _count(rows) -> int:
    """Rows of a QuerySet (one COUNT query) or of a list."""
    return rows.count() if isinstance(rows, QuerySet) else len(rows)


def page_of(rows, page: int = 1, size: int | None = None) -> Page:
    """
    Cut one page out of a list.

    Args:
        rows: an ordered QuerySet, or a list.
        page: the page wanted, from 1.
        size: rows per page (None = DJKIT_PAGE_SIZE); one of DJKIT_PAGE_SIZES.

    Returns:
        The Page.

    Raises:
        InvalidData: on "size" for a size not allowed, on "page" for a page
            below 1 or after the last one.
        ValueError: for an unordered QuerySet.
    """
    size = default_page_size() if size is None else size
    if size not in page_sizes():
        sizes = ", ".join(str(value) for value in page_sizes())
        raise InvalidData(errors={"size": [get_message("page_size_not_allowed", sizes=sizes)]})
    if isinstance(rows, QuerySet) and not rows.ordered:
        raise ValueError(f"page_of needs an ordered QuerySet ({rows.model.__name__}): add order_by()")
    count = _count(rows)
    pages = max(1, ceil(count / size))
    if page < 1 or page > pages:
        raise InvalidData(errors={"page": [get_message("page_out_of_range", pages=pages)]})
    start = (page - 1) * size
    return Page(items=rows[start : start + size], count=count, page=page, size=size, pages=pages)


class PageNumber(PaginationBase):
    """
    Django Ninja paginator by page number (see the module docstring).

    DJKIT_PAGE_SIZE / DJKIT_PAGE_SIZES are read on every request (no
    value is frozen at import), so override_settings works in tests.
    """

    class Input(Schema):
        """Query parameters: ?page= and ?size= (checked by page_of)."""

        page: int = Field(1)
        size: int | None = Field(None)

    class Output(Schema):
        """The page: rows, total, page number, size, number of pages."""

        items: list[Any]
        count: int
        page: int
        size: int
        pages: int

    def paginate_queryset(self, queryset, pagination: Input, request, **params) -> dict:
        """
        One page of the view's rows.

        Args:
            queryset: what the view returned (an ordered QuerySet or a list).
            pagination: the parsed ?page= and ?size=.
            request: the HttpRequest (unused).

        Returns:
            A dict with the fields of Output.
        """
        result = page_of(queryset, pagination.page, pagination.size)
        return {
            self.items_attribute: result.items,
            "count": result.count,
            "page": result.page,
            "size": result.size,
            "pages": result.pages,
        }
