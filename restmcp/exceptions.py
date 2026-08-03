class RestMCPException(Exception):
    """Base exception for restmcp. Carries an HTTP status code alongside the message."""

    def __init__(self, message: str, status_code: int = 500):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class ValidationError(RestMCPException):
    def __init__(self, message: str):
        super().__init__(message, status_code=400)


class NotFoundError(RestMCPException):
    def __init__(self, message: str):
        super().__init__(message, status_code=404)


class PayloadTooLargeError(RestMCPException):
    def __init__(self, message: str):
        super().__init__(message, status_code=413)


class ForbiddenError(RestMCPException):
    def __init__(self, message: str):
        super().__init__(message, status_code=403)
