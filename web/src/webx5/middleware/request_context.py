"""Middleware to set request context variables for observability."""

import os
import time
import uuid

import structlog
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from webx5.utils.contextvars_utils import (
    request_id_context,
    service_name_context,
    procedure_state_context,
)

log = structlog.get_logger("webx5.http")


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Sets request context for structlog and tracing, logs each HTTP request lifecycle."""

    async def dispatch(self, request: Request, call_next):
        structlog.contextvars.clear_contextvars()

        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        service_name = os.getenv("SERVICE_NAME", "webx5")
        procedure_name = f"{request.method} {request.url.path}"

        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            service_name=service_name,
            procedure_name=procedure_name,
            procedure_state="started",
        )

        request_id_context.set(request_id)
        service_name_context.set(service_name)
        procedure_state_context.set("started")

        start_time = time.monotonic()

        log.info("request.started", method=request.method, path=request.url.path)

        try:
            response = await call_next(request)
            duration_ms = round((time.monotonic() - start_time) * 1000, 2)

            structlog.contextvars.bind_contextvars(procedure_state="completed")
            procedure_state_context.set("completed")

            log.info(
                "request.completed",
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                duration_ms=duration_ms,
            )
            return response

        except Exception as exc:
            duration_ms = round((time.monotonic() - start_time) * 1000, 2)
            structlog.contextvars.bind_contextvars(procedure_state="failed")
            procedure_state_context.set("failed")

            log.error(
                "request.failed",
                method=request.method,
                path=request.url.path,
                error_type=type(exc).__name__,
                error_message=str(exc),
                duration_ms=duration_ms,
                exc_info=True,
            )
            raise
