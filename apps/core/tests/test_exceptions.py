import pytest
from django.core.exceptions import ObjectDoesNotExist, TooManyFieldsSent
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from rest_framework import status
from rest_framework.exceptions import (
    APIException,
    AuthenticationFailed,
    MethodNotAllowed,
    NotAcceptable,
    NotAuthenticated,
    NotFound,
    ParseError,
    PermissionDenied,
    Throttled,
    UnsupportedMediaType,
    ValidationError,
)

from apps.core.exceptions import DomainError, api_exception_handler


class OutOfStock(DomainError):
    code = "out_of_stock"
    message = "Not enough stock to fulfil this order."


def _handle(exc):
    return api_exception_handler(exc, {})


def test_domain_error_maps_to_422_and_its_own_code():
    response = _handle(OutOfStock(details={"available": 2}))

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert response.data["error"]["code"] == "out_of_stock"
    assert response.data["error"]["details"] == {"available": 2}


def test_domain_error_message_can_be_overridden_per_raise():
    response = _handle(OutOfStock(message="Only 2 left."))

    assert response.data["error"]["message"] == "Only 2 left."


def test_validation_error_uses_the_documented_code_not_drf_default():
    response = _handle(ValidationError({"email": ["Enter a valid email address."]}))

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.data["error"]["code"] == "validation_error"
    assert response.data["error"]["details"] == {"email": ["Enter a valid email address."]}


def test_validation_error_message_is_the_first_field_error():
    response = _handle(ValidationError({"email": ["Enter a valid email address."]}))

    assert response.data["error"]["message"] == "Enter a valid email address."


def test_missing_credentials_map_to_401_authentication_failed():
    response = _handle(NotAuthenticated())

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.data["error"]["code"] == "authentication_failed"


def test_throttled_maps_to_429():
    response = _handle(Throttled())

    assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    assert response.data["error"]["code"] == "throttled"


def test_django_validation_error_is_translated_into_the_envelope():
    response = _handle(DjangoValidationError({"name": ["This field cannot be blank."]}))

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.data["error"]["details"] == {"name": ["This field cannot be blank."]}


def test_not_found_maps_to_404_with_a_flat_message():
    response = _handle(NotFound())

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.data["error"]["code"] == "not_found"
    assert response.data["error"]["details"] == {}


def test_a_missing_object_maps_to_404_so_selectors_need_not_catch_it():
    response = _handle(ObjectDoesNotExist())

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.data["error"]["code"] == "not_found"


def test_a_missing_object_response_carries_no_lookup_detail():
    response = _handle(ObjectDoesNotExist("Product matching query does not exist."))

    assert "Product" not in str(response.data)


def test_a_suspicious_request_body_maps_to_400_parse_error_without_detail(caplog):
    response = _handle(TooManyFieldsSent("The number of GET/POST parameters exceeded 1000."))

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.data["error"]["code"] == "parse_error"
    assert "parameters" not in str(response.data)
    assert "request.suspicious_operation" in caplog.text
    assert "request.unhandled_exception" not in caplog.text


def test_permission_denied_maps_to_403():
    response = _handle(PermissionDenied())

    assert response.data["error"]["code"] == "permission_denied"


def test_integrity_error_maps_to_409_conflict():
    response = _handle(IntegrityError("duplicate key value violates unique constraint"))

    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.data["error"]["code"] == "conflict"


def test_integrity_error_response_carries_no_database_detail():
    response = _handle(IntegrityError("Key (email)=(leak@example.com) already exists."))

    assert "leak@example.com" not in str(response.data)


def test_unhandled_exception_maps_to_500_server_error_without_detail():
    response = _handle(RuntimeError("connection string postgres://user:pw@host"))

    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert response.data["error"]["code"] == "server_error"
    assert "postgres://" not in str(response.data)


def test_unhandled_exception_is_logged_with_its_traceback(caplog):
    _handle(RuntimeError("boom"))

    assert "request.unhandled_exception" in caplog.text


@pytest.mark.parametrize(
    "exc",
    [OutOfStock(), ValidationError("bad"), NotFound(), IntegrityError("x"), RuntimeError("x")],
)
def test_every_failure_shares_one_envelope_shape(exc):
    response = _handle(exc)

    assert set(response.data) == {"error"}
    assert set(response.data["error"]) == {"code", "message", "details"}


# Every row of the status/code table in docs/architecture.md that a DRF exception
# produces. The 409, 422 and 500 rows arrive by other paths and are covered above.
@pytest.mark.parametrize(
    ("exc", "expected_status", "expected_code"),
    [
        (ParseError(), 400, "parse_error"),
        (ValidationError("bad"), 400, "validation_error"),
        (NotAuthenticated(), 401, "authentication_failed"),
        (AuthenticationFailed(), 401, "authentication_failed"),
        (PermissionDenied(), 403, "permission_denied"),
        (NotFound(), 404, "not_found"),
        (MethodNotAllowed("POST"), 405, "method_not_allowed"),
        (NotAcceptable(), 406, "not_acceptable"),
        (UnsupportedMediaType("text/csv"), 415, "unsupported_media_type"),
        (Throttled(), 429, "throttled"),
    ],
)
def test_published_codes_do_not_depend_on_drf_internals(exc, expected_status, expected_code):
    response = _handle(exc)

    assert response.status_code == expected_status
    assert response.data["error"]["code"] == expected_code


def test_an_unpublished_api_exception_keeps_its_status_and_reports_a_generic_code():
    class Unpublished(APIException):
        status_code = 418
        default_code = "drf_internal_name"
        default_detail = "Nope."

    response = _handle(Unpublished())

    assert response.status_code == 418
    assert response.data["error"]["code"] == "error"
