import asyncio
import io
import json
import logging
import logging.config
from pathlib import Path

import pytest

from vllm_privacy.filters import ENGINE_DUMP_LOGGER, REQUEST_LOGGER, RESPONSE_LOGGER, RedactRequestContent
from vllm_privacy.middleware import AccessLogMiddleware, BearerAuthMiddleware

SECRET = "SECRET-PROMPT-42"


def emit(name, level, msg, *args):
    record = logging.LogRecord(name, level, __file__, 1, msg, args, None)
    keep = RedactRequestContent().filter(record)
    return record.getMessage() if keep else None


@pytest.mark.parametrize(
    ("logger", "level", "msg", "args", "expected"),
    [
        (
            REQUEST_LOGGER,
            logging.INFO,
            "Received request %s: params: %s, lora_request: %s.",
            ("req-1", f"SamplingParams(stop=['{SECRET}'])", None),
            "Received request req-1",
        ),
        (
            REQUEST_LOGGER,
            logging.DEBUG,
            "Request %s details: prompt: %r, prompt_token_ids: %s, prompt_embeds shape: %s.",
            ("req-1", SECRET, [1, 2], None),
            None,
        ),
        (REQUEST_LOGGER, logging.DEBUG, "Request %s JSON body: %s", ("req-1", SECRET), None),
        (
            REQUEST_LOGGER,
            logging.INFO,
            "Generated response %s%s: output: %r, finish_reason: %s",
            ("req-1", "", SECRET, "stop"),
            "Generated response req-1: finish_reason=stop",
        ),
        (
            REQUEST_LOGGER,
            logging.INFO,
            "Generated response %s%s: output: %r, finish_reason: %s",
            ("req-1", " (streaming delta)", SECRET, None),
            None,
        ),
        (REQUEST_LOGGER, logging.INFO, "Some future format %s", (SECRET,), None),
        (
            REQUEST_LOGGER,
            logging.WARNING,
            "`--enable-log-requests` is set but the minimum log level is higher",
            (),
            "`--enable-log-requests` is set but the minimum log level is higher",
        ),
        (RESPONSE_LOGGER, logging.INFO, "response_body={%s}", (SECRET,), None),
        (ENGINE_DUMP_LOGGER, logging.ERROR, "Dumping scheduler output for model execution: %s", (SECRET,), None),
        (
            ENGINE_DUMP_LOGGER,
            logging.ERROR,
            "Dumping input data for V1 LLM engine (%s) with config: %s",
            ("v0.29.0", "model=qwen"),
            "Dumping input data for V1 LLM engine (v0.29.0) with config: model=qwen",
        ),
        ("vllm.v1.engine.core", logging.INFO, "Engine started in %s s", (3,), "Engine started in 3 s"),
    ],
)
def test_filter(logger, level, msg, args, expected):
    assert emit(logger, level, msg, *args) == expected


def test_logging_config_redacts_at_debug_level():
    config = json.loads((Path(__file__).parents[1] / "config" / "logging.json").read_text())
    stream = io.StringIO()
    config["handlers"]["stdout"]["stream"] = stream
    config["loggers"]["vllm"]["level"] = "DEBUG"
    config["formatters"]["json"]["fmt"] = "%(levelname)s %(name)s %(message)s"
    logging.config.dictConfig(config)

    log = logging.getLogger(REQUEST_LOGGER)
    log.debug("Request %s details: prompt: %r, prompt_token_ids: %s, prompt_embeds shape: %s.", "r", SECRET, [], None)
    log.info("Received request %s: params: %s, lora_request: %s.", "r", SECRET, None)
    log.info("Generated response %s%s: output: %r, finish_reason: %s", "r", "", SECRET, "length")

    output = stream.getvalue()
    assert SECRET not in output
    assert "Received request r" in output
    assert "finish_reason=length" in output


def run_asgi(app, path, headers=()):
    sent = []

    async def receive():
        return {"type": "http.request", "body": b""}

    async def send(message):
        sent.append(message)

    scope = {"type": "http", "method": "POST", "path": path, "headers": list(headers), "client": ("10.0.0.1", 1)}
    asyncio.run(app(scope, receive, send))
    return sent[0]["status"]


async def ok_app(scope, receive, send):
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"{}"})


@pytest.fixture
def auth_app(monkeypatch):
    monkeypatch.setenv("API_BEARER_TOKEN", "token-1")
    return BearerAuthMiddleware(ok_app)


@pytest.mark.parametrize("path", ["/v1/chat/completions", "/invocations", "/metrics", "/v1/models"])
def test_auth_required(auth_app, path):
    assert run_asgi(auth_app, path) == 401
    assert run_asgi(auth_app, path, [(b"authorization", b"Bearer wrong")]) == 401
    assert run_asgi(auth_app, path, [(b"authorization", b"Bearer token-1")]) == 200


def test_health_is_public(auth_app):
    assert run_asgi(auth_app, "/health") == 200


def test_auth_requires_token(monkeypatch):
    monkeypatch.delenv("API_BEARER_TOKEN", raising=False)
    with pytest.raises(RuntimeError):
        BearerAuthMiddleware(ok_app)


def test_access_log_has_metadata_only(caplog):
    caplog.set_level(logging.INFO, logger="vllm_privacy.access")
    run_asgi(
        AccessLogMiddleware(ok_app), "/v1/chat/completions", [(b"x-request-id", b"abc"), (b"content-length", b"42")]
    )
    record = caplog.records[-1]
    assert (record.request_id, record.path, record.status, record.request_bytes) == (
        "abc",
        "/v1/chat/completions",
        200,
        42,
    )
