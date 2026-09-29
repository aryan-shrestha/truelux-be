from rest_framework import status

from apps.core.exceptions import DomainError


class VariantUnavailable(DomainError):
    code = "variant_unavailable"
    message = "One or more of the selected items is no longer available."


class InsufficientStock(DomainError):
    code = "insufficient_stock"
    message = "Not enough stock to fulfil this order."


class ProductHasNoVariants(DomainError):
    code = "product_has_no_variants"
    message = "A product needs at least one variant before it can be published."


class CompareAtNotAbovePrice(DomainError):
    """A field error in the envelope's shape, so the admin app shows it on the field."""

    code = "validation_error"
    message = "The compare-at price must be greater than the price."
    status_code = status.HTTP_400_BAD_REQUEST

    def __init__(self) -> None:
        super().__init__(details={"compare_at_price": [self.message]})
