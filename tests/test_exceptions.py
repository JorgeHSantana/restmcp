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


# --- machine-readable ``code`` (0.7.0): optional, None unless the raiser sets it ---

def test_code_defaults_to_none():
    assert RestMCPException("x").code is None
    assert ValidationError("x").code is None


def test_code_is_kept():
    err = RestMCPException("x", 503, code="session_expired")
    assert err.code == "session_expired"
    assert err.status_code == 503


def test_unauthorized_error_defaults():
    from restmcp.exceptions import UnauthorizedError

    err = UnauthorizedError()
    assert err.status_code == 401
    assert err.code == "invalid_api_key"
    assert err.message == "Unauthorized"


def test_forbidden_error_accepts_code():
    from restmcp.exceptions import ForbiddenError

    assert ForbiddenError("x", code="forbidden_scope").code == "forbidden_scope"
    assert ForbiddenError("x").code is None
