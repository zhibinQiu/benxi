from typing import Any

from fastapi import HTTPException, status


class AppError(HTTPException):
    def __init__(
        self,
        code: int,
        message: str,
        status_code: int = 400,
        **extra: Any,
    ):
        detail: dict[str, Any] = {"code": code, "message": message, **extra}
        super().__init__(status_code=status_code, detail=detail)


def not_found(message: str = "Resource not found") -> AppError:
    return AppError(404, message, status.HTTP_404_NOT_FOUND)


def forbidden(message: str = "Forbidden") -> AppError:
    return AppError(403, message, status.HTTP_403_FORBIDDEN)


def unauthorized(message: str = "Unauthorized", *, reason: str | None = None) -> AppError:
    extra = {"reason": reason} if reason else {}
    return AppError(401, message, status.HTTP_401_UNAUTHORIZED, **extra)


def service_unavailable(message: str = "Service unavailable") -> AppError:
    return AppError(503, message, status.HTTP_503_SERVICE_UNAVAILABLE)


def bad_request(message: str) -> AppError:
    return AppError(400, message, status.HTTP_400_BAD_REQUEST)
