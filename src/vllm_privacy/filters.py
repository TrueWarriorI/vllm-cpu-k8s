import logging

REQUEST_LOGGER = "vllm.entrypoints.serve.utils.request_logger"
RESPONSE_LOGGER = "vllm.entrypoints.serve.middleware.log_response"
ENGINE_DUMP_LOGGER = "vllm.logging_utils.dump_input"
ENGINE_DUMP_SAFE = ("Dumping input data for V1 LLM engine", "Dumping scheduler stats", "Error preparing object to dump")


class RedactRequestContent(logging.Filter):
    """Removes prompts, request parameters and generated text from vLLM log records.

    The fact of a request is kept: "Received request <id>" and "Generated response <id>: finish_reason=...".
    Any other parametrized record of the request logger is dropped, so a new message format in a future
    vLLM release fails closed instead of leaking content.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.__dict__.pop("color_message", None)
        if record.name == RESPONSE_LOGGER:
            return False
        if record.name == ENGINE_DUMP_LOGGER:
            return isinstance(record.msg, str) and record.msg.startswith(ENGINE_DUMP_SAFE)
        if record.name != REQUEST_LOGGER:
            return True

        message = record.msg if isinstance(record.msg, str) else ""
        args = record.args if isinstance(record.args, tuple) else ()
        if message.startswith("Received request %s:") and args:
            record.msg, record.args = "Received request %s", (args[0],)
            return True
        if message.startswith("Generated response %s%s:") and len(args) == 4:
            request_id, stream_info, _output, finish_reason = args
            if stream_info == " (streaming delta)":
                return False
            record.msg, record.args = (
                "Generated response %s%s: finish_reason=%s",
                (request_id, stream_info, finish_reason),
            )
            return True
        return not args
