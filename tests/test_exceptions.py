import pytest
from restmcp.exceptions import ValidationError, NotFoundError, RestMCPException


def test_validation_error_status_code():
    err = ValidationError("invalid field")
    assert err.status_code == 400


def test_validation_error_message():
    err = ValidationError("invalid field")
    assert err.message == "invalid field"


def test_not_found_error_status_code():
    err = NotFoundError("resource not found")
    assert err.status_code == 404


def test_not_found_error_message():
    err = NotFoundError("resource not found")
    assert err.message == "resource not found"


def test_validation_error_is_restmcp_exception():
    assert issubclass(ValidationError, RestMCPException)


def test_not_found_error_is_restmcp_exception():
    assert issubclass(NotFoundError, RestMCPException)


def test_exceptions_are_raiseable():
    with pytest.raises(ValidationError) as exc_info:
        raise ValidationError("validation error")
    assert exc_info.value.status_code == 400
