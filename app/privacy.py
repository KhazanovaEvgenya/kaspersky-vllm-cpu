import logging
import time
import uuid


class SafeFormatter(logging.Formatter):
    def format(self, record):
        # Не форматируем исходное сообщение, args и traceback: они могут
        # содержать текст запроса даже при отключённом request logging.
        if record.name == "inference.audit":
            return (
                f"request id={record.audit_id} status={record.audit_status} "
                f"duration_ms={record.audit_duration:.1f}"
            )
        return f"{record.levelname} {record.name}: event"


class AuditMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["path"] not in {
            "/v1/chat/completions", "/v1/completions"
        }:
            return await self.app(scope, receive, send)

        started = time.perf_counter()
        request_id = uuid.uuid4().hex
        status = 500

        async def capture(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, capture)
        finally:
            logging.getLogger("inference.audit").info(
                "request",
                extra={
                    "audit_id": request_id,
                    "audit_status": status,
                    "audit_duration": (time.perf_counter() - started) * 1000,
                },
            )
