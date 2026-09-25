from rest_framework.pagination import LimitOffsetPagination


class DefaultLimitOffsetPagination(LimitOffsetPagination):
    default_limit = 25
    # Without a ceiling a caller can request the whole table in one query.
    max_limit = 100
