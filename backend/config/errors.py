class DomainError(Exception):
    """Business-rule violation, rendered by the API as {code, detail, ...}."""

    status_code = 400
    code = 'domain_error'

    def __init__(self, message, code=None, status_code=None, extra=None):
        super().__init__(message)
        self.message = message
        if code:
            self.code = code
        if status_code:
            self.status_code = status_code
        self.extra = extra or {}


class ConflictError(DomainError):
    status_code = 409
    code = 'conflict'


class UploadRejected(DomainError):
    """Blocking upload errors E-01 / E-02: the upload is refused with HTTP 400."""

    status_code = 400
