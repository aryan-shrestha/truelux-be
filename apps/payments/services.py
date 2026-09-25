from django.db import transaction

from apps.core.logging import get_logger
from apps.orders.constants import PaymentMethod
from apps.orders.models import Order
from apps.orders.services import mark_order_paid
from apps.payments import client
from apps.payments.exceptions import (
    PaymentAlreadyProcessed,
    PaymentAmountMismatch,
    PaymentGatewayUnavailable,
    PaymentNotCompleted,
)
from apps.payments.models import Payment, PaymentStatus
from apps.payments.selectors import get_payment_by_pidx

logger = get_logger(__name__)


def record_cod_payment(*, order: Order) -> Payment:
    """Records the money a courier will collect, without claiming it has been.

    The order stays unpaid until a merchant confirms the cash through
    `complete_cod_payment`.
    """
    payment = Payment.objects.create(
        order=order,
        method=PaymentMethod.COD,
        status=PaymentStatus.PENDING,
        amount=order.total,
    )

    logger.info(
        "payment.cod_recorded",
        payment_id=str(payment.pk),
        order_number=order.order_number,
    )
    return payment


def complete_cod_payment(*, payment: Payment) -> Payment:
    """Raises PaymentAlreadyProcessed if the payment is not still pending.

    Marks the order paid. The order row is written by `apps.orders.services`, never
    from here.
    """
    with transaction.atomic():
        # The status check guards a state change on another table, so it is a
        # read-then-write on shared state and needs the row lock. Two merchants
        # confirming the same cash at once would otherwise both pass the check.
        locked = Payment.objects.select_for_update().get(pk=payment.pk)

        if locked.status != PaymentStatus.PENDING:
            raise PaymentAlreadyProcessed(
                details={"payment_id": str(locked.pk), "status": locked.status}
            )

        locked.status = PaymentStatus.COMPLETED
        locked.save(update_fields=["status", "updated_at"])

        mark_order_paid(order=locked.order)

    logger.info(
        "payment.cod_completed",
        payment_id=str(locked.pk),
        order_number=locked.order.order_number,
    )
    return locked


def initiate_khalti_payment(*, order: Order) -> str:
    """Raises PaymentGatewayUnavailable when Khalti cannot be reached or refuses.

    Returns the payment URL to send the customer to. Records a pending payment
    carrying the `pidx`, which is what makes verification idempotent later.
    """
    try:
        body = client.initiate(
            amount=order.total,
            purchase_order_id=order.order_number,
            # Khalti calls this the product name and shows it to the customer. A
            # multi-line cart has no single product, so the order identifies itself.
            purchase_order_name=f"Order {order.order_number}",
            customer_name=order.full_name,
            customer_email=order.email,
            customer_phone=order.phone,
        )
    except client.KhaltiError as exc:
        # The order is already committed and holding stock -- ADR 0005 puts this
        # call outside that transaction. Naming the order lets the storefront tell
        # the customer it exists, so they do not check out again and decrement the
        # same stock twice.
        raise PaymentGatewayUnavailable(details={"order_number": order.order_number}) from exc

    payment = Payment.objects.create(
        order=order,
        method=PaymentMethod.KHALTI,
        status=PaymentStatus.PENDING,
        amount=order.total,
        pidx=body["pidx"],
    )

    logger.info(
        "payment.khalti_initiated",
        payment_id=str(payment.pk),
        order_number=order.order_number,
    )
    return str(body["payment_url"])


def verify_khalti_payment(*, pidx: str) -> Payment:
    """Raises PaymentNotCompleted for any status other than Completed, and
    PaymentAmountMismatch when Khalti reports a different amount from the order's.

    Lookup is the only source of truth (ADR 0005); nothing the customer's browser
    carried back is read here.
    """
    # Ours before Khalti's: an unknown pidx raises DoesNotExist here, which the
    # handler turns into the documented 404, rather than spending an outbound call
    # on an identifier this system never issued.
    payment = get_payment_by_pidx(pidx=pidx)
    if payment.status == PaymentStatus.COMPLETED:
        # Idempotent rather than an error: a refreshed or bookmarked return is the
        # customer doing nothing wrong, and Khalti has nothing left to tell us.
        return payment

    # Outside the transaction: an external call of unbounded duration must not be
    # made while holding a row lock (ADR 0005).
    try:
        body = client.lookup(pidx=pidx)
    except client.KhaltiError as exc:
        # Translated rather than allowed to propagate: the caller is a customer's
        # browser returning from a payment, and an unhandled KhaltiError would reach
        # the handler as a 500 JSON page for someone who has just paid. As a
        # DomainError it becomes the failure redirect the return view is built on.
        raise PaymentGatewayUnavailable(
            details={"order_number": payment.order.order_number}
        ) from exc

    gateway_status = str(body["status"])

    # Recorded before any branch, and outside the transaction below, so that what
    # Khalti reported survives whichever way this ends. Written inside a block that
    # then raises, it would roll back and leave no trace of the refusal.
    payment.raw_status = gateway_status
    payment.transaction_id = str(body.get("transaction_id") or "")
    payment.save(update_fields=["raw_status", "transaction_id", "updated_at"])

    if gateway_status != client.COMPLETED_STATUS:
        payment.status = PaymentStatus.FAILED
        payment.save(update_fields=["status", "updated_at"])
        logger.info(
            "payment.khalti_not_completed",
            payment_id=str(payment.pk),
            gateway_status=gateway_status,
        )
        raise PaymentNotCompleted(details={"gateway_status": gateway_status})

    # The order total cannot change after placement, so comparing it here rather
    # than under the lock is safe; only fulfilment needs serialising.
    if client.to_rupees(int(body["total_amount"])) != payment.order.total:
        # Either an integration bug or an attack, and both need a human.
        logger.error(
            "payment.amount_mismatch",
            payment_id=str(payment.pk),
            order_number=payment.order.order_number,
        )
        raise PaymentAmountMismatch(details={"order_number": payment.order.order_number})

    with transaction.atomic():
        # Locked for the same reason complete_cod_payment locks: the status check
        # guards a state change on the order. The return URL is a plain GET that
        # customers refresh, so concurrent verifications of one pidx are ordinary.
        locked = Payment.objects.select_for_update().get(pk=payment.pk)

        if locked.status == PaymentStatus.COMPLETED:
            # Another request won the race between the read above and this lock.
            return locked

        locked.status = PaymentStatus.COMPLETED
        locked.save(update_fields=["status", "updated_at"])

        mark_order_paid(order=locked.order)

    logger.info(
        "payment.khalti_verified",
        payment_id=str(locked.pk),
        order_number=locked.order.order_number,
    )
    return locked
