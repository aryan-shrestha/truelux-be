from typing import Any

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

from apps.core.logging import get_logger

logger = get_logger(__name__)


def send_email(
    *,
    to: str,
    subject: str,
    template_name: str,
    context: dict[str, Any],
    reference: str,
) -> bool:
    """Renders and sends one message, and never raises.

    `template_name` is a stem: `<stem>.txt` is the body and `<stem>.html` the
    alternative. Returns whether it sent, so a caller that reports to a human can.

    ADR 0006 sends inside the request that caused the state change, with no queue
    and no retry, so a failure here must not take that request down with it -- a
    customer whose order was placed must not see an error because SMTP was slow.
    `reference` identifies the thing being mailed about in the log, because
    convention.md forbids logging the recipient's address.
    """
    try:
        # Rendering is inside the try, not before it. A TemplateSyntaxError or a
        # missing attribute would otherwise raise out of the on_commit callback --
        # and the transaction has already committed by then, so the customer would
        # get a 500 for an order that was placed successfully, with its stock gone.
        message = EmailMultiAlternatives(
            subject=subject,
            # Stripped: a template that opens with a tag renders a leading blank
            # line, and the customer reads the result. Done here rather than in
            # each template so the next one cannot reintroduce it.
            body=render_to_string(f"{template_name}.txt", context).strip() + "\n",
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[to],
        )
        message.attach_alternative(render_to_string(f"{template_name}.html", context), "text/html")
        message.send()
    except Exception:
        # The only trace this failure leaves. Nothing retries, nothing alerts, and
        # the customer sees a successful order page -- so this line is what a
        # merchant chasing a complaint has to find.
        logger.exception("email.send_failed", template=template_name, reference=reference)
        return False

    logger.info("email.sent", template=template_name, reference=reference)
    return True
