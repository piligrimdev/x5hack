"""Prometheus metrics middleware for FastAPI."""

import time
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.routing import Match

from webx5.utils.metrics import REQUEST_COUNT, REQUEST_LATENCY, ERROR_COUNT


class PrometheusMiddleware(BaseHTTPMiddleware):
    """Middleware to collect Prometheus metrics for HTTP requests."""

    async def dispatch(self, request: Request, call_next):
        # Get endpoint name for labeling
        endpoint = self._get_endpoint_name(request)
        method = request.method

        start_time = time.time()

        try:
            response = await call_next(request)
            status_code = response.status_code

            # Record metrics
            duration = time.time() - start_time
            REQUEST_COUNT.labels(method=method, endpoint=endpoint, status=str(status_code)).inc()
            REQUEST_LATENCY.labels(method=method, endpoint=endpoint).observe(duration)

            return response

        except Exception as e:
            duration = time.time() - start_time
            error_type = type(e).__name__

            REQUEST_COUNT.labels(method=method, endpoint=endpoint, status="500").inc()
            REQUEST_LATENCY.labels(method=method, endpoint=endpoint).observe(duration)
            ERROR_COUNT.labels(method=method, endpoint=endpoint, error_type=error_type).inc()

            raise

    def _get_endpoint_name(self, request: Request) -> str:
        """Extract endpoint name from request path."""
        for route in request.app.routes:
            match, _ = route.matches(request.scope)
            if match == Match.FULL:
                return getattr(route, "path", request.url.path)
        return request.url.path
