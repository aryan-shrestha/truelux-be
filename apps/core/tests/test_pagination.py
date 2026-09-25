from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

from apps.core.pagination import DefaultLimitOffsetPagination


def _paginate(query: str, queryset: range):
    paginator = DefaultLimitOffsetPagination()
    request = Request(APIRequestFactory().get(f"/?{query}"))
    page = paginator.paginate_queryset(list(queryset), request)
    return paginator, page


def test_default_limit_applies_when_the_caller_asks_for_none():
    _, page = _paginate("", range(100))

    assert len(page) == DefaultLimitOffsetPagination.default_limit


def test_limit_above_the_ceiling_is_clamped():
    _, page = _paginate("limit=5000", range(500))

    assert len(page) == DefaultLimitOffsetPagination.max_limit


def test_offset_skips_the_requested_number_of_rows():
    _, page = _paginate("limit=5&offset=10", range(100))

    assert page == list(range(10, 15))


def test_paginated_response_reports_the_full_count_and_a_next_link():
    paginator, page = _paginate("limit=5", range(100))

    body = paginator.get_paginated_response(page).data

    assert body["count"] == 100
    assert body["next"] is not None
    assert body["previous"] is None
