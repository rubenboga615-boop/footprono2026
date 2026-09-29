import json
import logging

from footprono.core.logging import JsonFormatter, request_id_var


def _record(msg: str, **extra: object) -> logging.LogRecord:
    record = logging.makeLogRecord({"name": "t", "levelname": "INFO", "msg": msg})
    record.__dict__.update(extra)
    return record


def test_json_formatter_includes_request_id_and_extras() -> None:
    token = request_id_var.set("req-42")
    try:
        line = JsonFormatter().format(_record("bonjour", match_id=7))
    finally:
        request_id_var.reset(token)
    payload = json.loads(line)
    assert payload["message"] == "bonjour"
    assert payload["request_id"] == "req-42"
    assert payload["match_id"] == 7
    assert payload["level"] == "INFO"


def test_json_formatter_without_request_context() -> None:
    payload = json.loads(JsonFormatter().format(_record("hors requête")))
    assert "request_id" not in payload
