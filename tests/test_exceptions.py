import pytest
from pythia.exceptions import ValidationError, NotFoundError, PythiaException


def test_validation_error_status_code():
    err = ValidationError("campo inválido")
    assert err.status_code == 400


def test_validation_error_message():
    err = ValidationError("campo inválido")
    assert err.message == "campo inválido"


def test_not_found_error_status_code():
    err = NotFoundError("recurso não encontrado")
    assert err.status_code == 404


def test_not_found_error_message():
    err = NotFoundError("recurso não encontrado")
    assert err.message == "recurso não encontrado"


def test_validation_error_is_pythia_exception():
    assert issubclass(ValidationError, PythiaException)


def test_not_found_error_is_pythia_exception():
    assert issubclass(NotFoundError, PythiaException)


def test_exceptions_are_raiseable():
    with pytest.raises(ValidationError) as exc_info:
        raise ValidationError("erro de validação")
    assert exc_info.value.status_code == 400
