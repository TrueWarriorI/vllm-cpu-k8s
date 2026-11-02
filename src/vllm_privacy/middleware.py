import hmac
import json
import logging
import os
import time
import uuid

PUBLIC_PATHS = frozenset({"/health", "/ping", "/version"})
QUIET_PATHS = frozenset({"/health", "/ping", "/metrics"})

access_logger = logging.getLogger("vllm_privacy.access")


def _header(scope, name: bytes) -> bytes:
    return next((value for key, value in scope["headers"] if key == name), b"")


class BearerAuthMiddleware:
    """Requires `Authorization: Bearer <API_BEARER_TOKEN>` on every HTTP path except health probes.

    vLLM's own `--api-key` protects only /v1, /v2 and /inference, leaving /invocations open.
    """

    def __init__(self, app):
        self.app = app
        token = os.environ.get("API_BEARER_TOKEN", "")
        if not token:
            raise RuntimeError("API_BEARER_TOKEN is not set")
        self.expected = b"Bearer " + token.encode()

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["path"] in PUBLIC_PATHS or scope["method"] == "OPTIONS":
            return await self.app(scope, receive, send)
        if hmac.compare_digest(_header(scope, b"authorization"), self.expected):
            return await self.app(scope, receive, send)

        body = json.dumps({"error": {"message": "Unauthorized", "type": "authentication_error"}}).encode()
        await send(
            {
                "type": "http.response.start",
                "status": 401,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                    (b"www-authenticate", b"Bearer"),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})


class AccessLogMiddleware:
    """Logs the fact of each request: id, method, path, status, sizes and duration. Never touches bodies."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        request_id = _header(scope, b"x-request-id").decode(errors="replace")[:64] or uuid.uuid4().hex
        started = time.perf_counter()
        state = {"status": 500, "bytes": 0, "first_byte": None}

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                state["status"] = message["status"]
            elif message["type"] == "http.response.body":
                if state["first_byte"] is None:
                    state["first_byte"] = time.perf_counter()
                state["bytes"] += len(message.get("body", b""))
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            if scope["path"] not in QUIET_PATHS or state["status"] >= 400:
                first = state["first_byte"]
                access_logger.info(
                    "request",
                    extra={
                        "request_id": request_id,
                        "method": scope["method"],
                        "path": scope["path"],
                        "status": state["status"],
                        "request_bytes": int(length) if (length := _header(scope, b"content-length")).isdigit() else 0,
                        "response_bytes": state["bytes"],
                        "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                        "first_byte_ms": round((first - started) * 1000, 1) if first else None,
                        "client": (scope.get("client") or ("-",))[0],
                    },
                )
