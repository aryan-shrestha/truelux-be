import re
import uuid
from collections.abc import Callable

import structlog
from django.http import HttpRequest, HttpResponse

REQUEST_ID_HEADER = "X-Request-ID"
REQUEST_ID_MAX_LENGTH = 64
# The inbound value is echoed into a response header and into every log line for
# the request, so it is constrained to characters that cannot forge either.
VALID_REQUEST_ID = re.compile(rf"\A[A-Za-z0-9._-]{{1,{REQUEST_ID_MAX_LENGTH}}}\Z")


class RequestIDMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        request_id = self._resolve(request)

        # Context variables outlive a request on a reused worker thread, so the
        # binding is cleared on both sides rather than only afterwards.
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)
        try:
            response = self.get_response(request)
        finally:
            structlog.contextvars.clear_contextvars()

        response[REQUEST_ID_HEADER] = request_id
        return response

    def _resolve(self, request: HttpRequest) -> str:
        # An upstream proxy may already have assigned one; reusing it keeps a trace
        # intact across services.
        supplied = request.headers.get(REQUEST_ID_HEADER, "")
        if VALID_REQUEST_ID.match(supplied):
            return supplied
        return uuid.uuid4().hex
