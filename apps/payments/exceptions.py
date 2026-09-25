from apps.core.exceptions import DomainError


class PaymentAlreadyProcessed(DomainError):
    code = "payment_already_processed"
    message = "This payment has already been processed."
