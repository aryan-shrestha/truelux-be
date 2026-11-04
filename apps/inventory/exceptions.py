from rest_framework import status

from apps.core.exceptions import DomainError


class InvalidStockAdjustment(DomainError):
    """A field error in the envelope's shape, so the admin app shows it on the field."""

    code = "validation_error"
    status_code = status.HTTP_400_BAD_REQUEST

    def __init__(self, message: str) -> None:
        super().__init__(message=message, details={"quantity_change": [message]})
