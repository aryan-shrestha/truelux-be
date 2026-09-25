from django.db import transaction

from apps.core.logging import get_logger
from apps.orders.constants import PaymentMethod
from apps.orders.models import Order
from apps.payments.exceptions import PaymentAlreadyProcessed
from apps.payments.models import Payment, PaymentStatus

logger = get_logger(__name__)


def record_cod_payment(*, order: Order) -> Payment:
    """Records the cash the courier will collect, without claiming it has been."""
    payment = Payment.objects.create(
        order=order,
        method=PaymentMethod.COD,
        status=PaymentStatus.PENDING,
        amount=order.total,
    )

    logger.info("payment.cod_recorded", payment_id=str(payment.pk), order_number=order.order_number)
    return payment


def complete_cod_payment(*, payment: Payment) -> Payment:
    """Raises PaymentAlreadyProcessed if the payment is not still pending.

    Records that the courier handed over the cash. The order's status is not
    touched: under ADR 0011 confirmation and delivery are order transitions.
    """
    with transaction.atomic():
        # Locked so two staff recording the same cash cannot both pass the check.
        locked = Payment.objects.select_for_update().get(pk=payment.pk)

        if locked.status != PaymentStatus.PENDING:
            raise PaymentAlreadyProcessed(
                details={"payment_id": str(locked.pk), "status": locked.status}
            )

        locked.status = PaymentStatus.COMPLETED
        locked.save(update_fields=["status", "updated_at"])

    logger.info("payment.cod_completed", payment_id=str(locked.pk))
    return locked
