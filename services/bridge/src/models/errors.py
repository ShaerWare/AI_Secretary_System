"""OpenAI-compatible error models."""

from typing import Literal
from pydantic import BaseModel


class ErrorDetail(BaseModel):
    """Error detail."""

    message: str
    type: Literal[
        "invalid_request_error",
        "authentication_error",
        "permission_error",
        "not_found_error",
        "rate_limit_error",
        "server_error",
        "timeout_error",
    ]
    param: str | None = None
    code: str | None = None


class ErrorResponse(BaseModel):
    """OpenAI-compatible error response."""

    error: ErrorDetail


def create_error(
    message: str,
    error_type: str = "server_error",
    param: str | None = None,
    code: str | None = None,
) -> ErrorResponse:
    """Create an error response."""
    return ErrorResponse(
        error=ErrorDetail(
            message=message,
            type=error_type,
            param=param,
            code=code,
        )
    )
