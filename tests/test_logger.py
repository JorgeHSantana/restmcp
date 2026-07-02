import logging
from restmcp.logging import Logger


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
    # Logger sets propagate=False, so records never reach caplog's root
    # handler; attach caplog's handler to the logger directly to capture.
    logger._logger.addHandler(caplog.handler)
    caplog.set_level(logging.INFO, logger="test.logger")
    logger.info("mensagem de teste")
    assert "mensagem de teste" in caplog.text


def test_logger_default_level_is_info(monkeypatch):
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    logger = Logger("test.level")
    assert logger._logger.level == logging.INFO


def test_logger_level_from_env(monkeypatch):
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    logger = Logger("test.env.level")
    assert logger._logger.level == logging.DEBUG


def test_logger_warning(caplog):
    logger = Logger("test.warning")
    logger._logger.addHandler(caplog.handler)
    caplog.set_level(logging.WARNING, logger="test.warning")
    logger.warning("warn msg")
    assert "warn msg" in caplog.text


def test_logger_error(caplog):
    logger = Logger("test.error")
    logger._logger.addHandler(caplog.handler)
    caplog.set_level(logging.ERROR, logger="test.error")
    logger.error("error msg")
    assert "error msg" in caplog.text


def test_logger_debug(caplog):
    logger = Logger("test.debug")
    logger._logger.addHandler(caplog.handler)
    caplog.set_level(logging.DEBUG, logger="test.debug")
    logger.debug("debug msg")
    assert "debug msg" in caplog.text


def test_logger_does_not_propagate_to_root():
    from restmcp.logging import Logger

    # Without propagate=False, an app that configures the root logger
    # (logging.basicConfig) sees every message twice.
    assert Logger("propagate_check")._logger.propagate is False
