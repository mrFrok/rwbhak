"""Точка входа API."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from .db import init_db
from .errors import handle_http_error, handle_validation_error
from .routers import analytics, catalog, contract, orders, stock, trips


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="RWB Mesh MVP",
    description=(
        "Прототип mesh-доставки с хранением в ПВЗ. Все числа — допущения команды, "
        "не тарифы RWB. Идемпотентность: заголовок Idempotency-Key на изменяющих запросах."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

for router in (catalog.router, stock.router, orders.router, trips.router, analytics.router):
    app.include_router(router, prefix="/api")
app.include_router(contract.router)
app.add_exception_handler(StarletteHTTPException, handle_http_error)
app.add_exception_handler(RequestValidationError, handle_validation_error)


@app.get("/api/health", tags=["system"])
@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok"}


if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    uvicorn.run(
        "api.main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8000")),
        reload=os.getenv("RELOAD", "0") == "1",
    )
