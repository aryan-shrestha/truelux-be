from apps.core.exceptions import DomainError


class PaymentAlreadyProcessed(DomainError):
    code = "payment_already_processed"
    message = "This payment has already been processed."


class PaymentNotCompleted(DomainError):
    code = "payment_not_completed"
    message = "The payment was not completed."


class PaymentAmountMismatch(DomainError):
    code = "payment_amount_mismatch"
    message = "The amount paid does not match the order total."


class PaymentGatewayUnavailable(DomainError):
    code = "payment_gateway_unavailable"
    message = "The order was placed but payment could not be started."
