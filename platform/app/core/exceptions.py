from fastapi import HTTPException, status


class AppError(HTTPException):
    def __init__(self, code: int, message: str, status_code: int = 400):
        super().__init__(status_code=status_code, detail={"code": code, "message": message})


def not_found(message: str = "Resource not found") -> AppError:
    return AppError(404, message, status.HTTP_404_NOT_FOUND)


def forbidden(message: str = "Forbidden") -> AppError:
    return AppError(403, message, status.HTTP_403_FORBIDDEN)


def unauthorized(message: str = "Unauthorized") -> AppError:
    return AppError(401, message, status.HTTP_401_UNAUTHORIZED)


def bad_request(message: str) -> AppError:
    return AppError(400, message, status.HTTP_400_BAD_REQUEST)
