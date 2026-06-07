class PythiaException(Exception):
    def __init__(self, message: str, status_code: int = 500):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class ValidationError(PythiaException):
    def __init__(self, message: str):
        super().__init__(message, status_code=400)


class NotFoundError(PythiaException):
    def __init__(self, message: str):
        super().__init__(message, status_code=404)
