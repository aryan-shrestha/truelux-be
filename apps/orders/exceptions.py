from apps.core.exceptions import DomainError


class InvalidStatusTransition(DomainError):
    code = "invalid_status_transition"
    message = "The order cannot move to that status from where it is."


class OrderAlreadyShipped(DomainError):
    code = "order_already_shipped"
    message = "The order has already left the warehouse."


class OrderNotCancellable(DomainError):
    code = "order_not_cancellable"
    message = "The order cannot be cancelled."


class EmptyCart(DomainError):
    code = "empty_cart"
    message = "The cart is empty."
