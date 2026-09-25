from apps.payments.models import Payment


def get_payment_by_pidx(*, pidx: str) -> Payment:
    return Payment.objects.select_related("order").get(pidx=pidx)
