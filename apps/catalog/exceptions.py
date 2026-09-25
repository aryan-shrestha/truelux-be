from apps.core.exceptions import DomainError


class VariantUnavailable(DomainError):
    code = "variant_unavailable"
    message = "One or more of the selected items is no longer available."


class InsufficientStock(DomainError):
    code = "insufficient_stock"
    message = "Not enough stock to fulfil this order."
