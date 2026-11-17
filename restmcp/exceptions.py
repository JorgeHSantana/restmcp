class RestMCPException(Exception):
    """Base exception for restmcp. Carries an HTTP status code alongside the message.

    ``code`` is an optional machine-readable identifier (e.g. ``"session_expired"``)
    that clients can branch on without parsing the message; it travels in the
    error envelope as ``code`` and is ``None`` when the raiser does not set it.
    """

    def __init__(self, message: str, status_code: int = 500, code: str | None = None):
        self.message = message
        self.status_code = status_code
        self.code = code
        super().__init__(message)


class ValidationError(RestMCPException):
    def __init__(self, message: str, code: str | None = None):
        super().__init__(message, status_code=400, code=code)


class NotFoundError(RestMCPException):
    def __init__(self, message: str, code: str | None = None):
        super().__init__(message, status_code=404, code=code)


class PayloadTooLargeError(RestMCPException):
    def __init__(self, message: str, code: str | None = None):
        super().__init__(message, status_code=413, code=code)


class UnauthorizedError(RestMCPException):
    """Missing or unknown API key — raised by the framework's auth layer."""

    def __init__(self, message: str = "Unauthorized", code: str | None = "invalid_api_key"):
        super().__init__(message, status_code=401, code=code)


class ForbiddenError(RestMCPException):
    def __init__(self, message: str, code: str | None = None):
        super().__init__(message, status_code=403, code=code)
