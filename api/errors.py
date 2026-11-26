"""Машиночитаемые ошибки нового API; на /api сохранён прежний формат."""

from fastapi import HTTPException, Request
from fastapi.exception_handlers import http_exception_handler, request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class DomainError(HTTPException):
    def __init__(self, status_code: int, code: str, detail: str, **context):
        super().__init__(status_code, detail)
        self.code = code
        self.context = context


async def handle_http_error(request: Request, exc: StarletteHTTPException):
    if request.url.path.startswith("/api/"):
        return await http_exception_handler(request, exc)
    if isinstance(exc, DomainError):
        code, context = exc.code, exc.context
    else:
        code = {
            400: "BAD_REQUEST", 404: "NOT_FOUND", 409: "CONFLICT",
            422: "VALIDATION_ERROR", 503: "MODEL_UNAVAILABLE",
        }.get(exc.status_code, "HTTP_ERROR")
        context = {}
    return JSONResponse(
        {"error": code, "detail": exc.detail, "context": context},
        status_code=exc.status_code, headers=exc.headers,
    )


async def handle_validation_error(request: Request, exc: RequestValidationError):
    if request.url.path.startswith("/api/"):
        return await request_validation_exception_handler(request, exc)
    fields = [{"location": item["loc"], "message": item["msg"]} for item in exc.errors()]
    return JSONResponse(
        {"error": "VALIDATION_ERROR", "detail": "Некорректные параметры запроса", "context": {"fields": fields}},
        status_code=422,
    )
