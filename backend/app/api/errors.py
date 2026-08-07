"""Domain-specific API errors mapped to HTTP responses."""
from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status


class ApiError(Exception):
    status_code: int = status.HTTP_400_BAD_REQUEST
    code: str = "error"

    def __init__(self, message: str, details: Any | None = None) -> None:
        self.message = message
        self.details = details
        super().__init__(message)


class OtpVerificationFailed(ApiError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "otp_invalid"


class RateLimitedError(ApiError):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    code = "rate_limited"


class UnauthorizedError(ApiError):
    status_code = status.HTTP_401_UNAUTHORIZED
    code = "unauthorized"


class ForbiddenError(ApiError):
    status_code = status.HTTP_403_FORBIDDEN
    code = "forbidden"


class NotFoundError(ApiError):
    status_code = status.HTTP_404_NOT_FOUND
    code = "not_found"


class ConflictError(ApiError):
    status_code = status.HTTP_409_CONFLICT
    code = "conflict"


class BadRequestError(ApiError):
    status_code = status.HTTP_400_BAD_REQUEST
    code = "bad_request"


def as_http_exception(exc: ApiError) -> HTTPException:
    return HTTPException(
        status_code=exc.status_code,
        detail={"code": exc.code, "message": exc.message},
    )
