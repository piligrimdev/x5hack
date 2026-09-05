"""Context variables management for observability instrumentation.

Provides context variables for request tracing (user_id, request_id, etc.)
that are used by structlog, Prometheus metrics, and Langfuse SDK.
"""

from contextvars import ContextVar

# Mandatory labels for structured logging and tracing
user_id_context: ContextVar[str | None] = ContextVar('user_id', default=None)
request_id_context: ContextVar[str | None] = ContextVar('request_id', default=None)
procedure_name_context: ContextVar[str | None] = ContextVar('procedure_name', default=None)
procedure_state_context: ContextVar[str | None] = ContextVar('procedure_state', default=None)
service_name_context: ContextVar[str | None] = ContextVar('service_name', default=None)
