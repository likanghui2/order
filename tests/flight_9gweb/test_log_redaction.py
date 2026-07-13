import json
import importlib

import pytest

from common.decorators.http_log_decorator import http_log_decorator
from common.model.response_info_model import ResponseInfoModel
from common.utils.log_redaction import redact_sensitive


def response():
    return ResponseInfoModel(data_bytes=b"{}", status=200, headers={}, url="https://example.com")


def test_trace_tokens_are_redacted_from_headers_and_payloads():
    redacted = redact_sensitive({
        "headers": {"Spa-Trace-Id": "trace-secret"},
        "trace_id": "trace-secret-2",
    })

    assert redacted["headers"]["Spa-Trace-Id"] == "[REDACTED]"
    assert redacted["trace_id"] == "[REDACTED]"
    assert "trace-secret" not in str(redacted)


@pytest.mark.parametrize(
    ("value", "token", "expected"),
    [
        (
            '{"Spa-Trace-Id": "trace-json-secret"}',
            "trace-json-secret",
            '{"Spa-Trace-Id": "[REDACTED]"}',
        ),
        (
            "Spa-Trace-Id=trace-form-secret",
            "trace-form-secret",
            "Spa-Trace-Id=[REDACTED]",
        ),
        (
            "Spa-Trace-Id: trace-header-secret",
            "trace-header-secret",
            "Spa-Trace-Id: [REDACTED]",
        ),
        (
            "trace_id: trace-header-secret-2",
            "trace-header-secret-2",
            "trace_id: [REDACTED]",
        ),
        (
            "traceId: trace-header-secret-3",
            "trace-header-secret-3",
            "traceId: [REDACTED]",
        ),
    ],
    ids=["json", "form", "spa-header", "snake-header", "camel-header"],
)
def test_trace_tokens_are_redacted_from_string_formats(value, token, expected):
    redacted = redact_sensitive(value)

    assert redacted == expected
    assert "[REDACTED]" in redacted
    assert token not in redacted


def test_http_logger_redacts_card_and_authentication_data(monkeypatch):
    captured = []
    monkeypatch.setattr(
        "common.decorators.http_log_decorator.lob_object.info",
        lambda message, *args, **kwargs: captured.append(str(message)),
    )

    @http_log_decorator()
    def send(_, **kwargs):
        return response()

    send(
        object(),
        url="https://example.com/pay",
        headers={"authorization": "Bearer secret-token", "x-d-token": "risk-token"},
        data=json.dumps({"pan": "4111111111111111", "CVV": "123"}),
    )

    output = " ".join(captured)
    assert "4111111111111111" not in output
    assert '"CVV": "123"' not in output
    assert "secret-token" not in output
    assert "risk-token" not in output
    assert "************1111" in output


def test_http_logger_redacts_form_secret_in_success_and_error_logs(monkeypatch):
    captured = []
    monkeypatch.setattr(
        "common.decorators.http_log_decorator.lob_object.info",
        lambda message, *args, **kwargs: captured.append(str(message)),
    )
    monkeypatch.setattr(
        "common.decorators.http_log_decorator.lob_object.error",
        lambda message, *args, **kwargs: captured.append(str(message)),
    )

    @http_log_decorator()
    def send(_, fail=False, **kwargs):
        if fail:
            raise RuntimeError("request failed")
        return response()

    form = "grant_type=client_credentials&client_secret=TOPSECRET"
    send(object(), url="https://example.com/oauth", headers={}, data=form)
    with pytest.raises(RuntimeError):
        send(object(), url="https://example.com/oauth", headers={}, data=form, fail=True)

    output = " ".join(captured)
    assert "TOPSECRET" not in output
    assert "client_secret=[REDACTED]" in output


def test_task_logger_redacts_payment_payload_before_validation(monkeypatch):
    module = importlib.import_module("task.9Gweb.booking")
    captured = []
    monkeypatch.setattr(module.LOG, "info", lambda message, *args, **kwargs: captured.append(str(message)))

    module.main({
        "taskId": "redaction-test",
        "taskType": "booking",
        "source": "9GWEB",
        "taskData": {
            "paymentInfo": {
                "type": "CARD",
                "cardNumber": "4111111111111111",
                "cardCVV": "123",
            }
        },
    })

    output = " ".join(captured)
    assert "4111111111111111" not in output
    assert "'cardCVV': '123'" not in output
    assert "************1111" in output
