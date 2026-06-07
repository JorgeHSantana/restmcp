import logging
from pythia.logging import Logger


def test_logger_instantiation():
    logger = Logger(__name__)
    assert logger is not None


def test_logger_has_info_method():
    logger = Logger(__name__)
    assert callable(logger.info)


def test_logger_has_warning_method():
    logger = Logger(__name__)
    assert callable(logger.warning)


def test_logger_has_error_method():
    logger = Logger(__name__)
    assert callable(logger.error)


def test_logger_has_debug_method():
    logger = Logger(__name__)
    assert callable(logger.debug)


def test_logger_does_not_raise_on_use(caplog):
    logger = Logger("test.logger")
    with caplog.at_level(logging.INFO, logger="test.logger"):
        logger.info("mensagem de teste")
    assert "mensagem de teste" in caplog.text


def test_logger_default_level_is_info(monkeypatch):
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    logger = Logger("test.level")
    assert logger._logger.level == logging.INFO
