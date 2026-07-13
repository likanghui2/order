import importlib
import json

import pytest

from common.decorators.http_log_decorator import http_log_decorator
from common.model.response_info_model import ResponseInfoModel
from common.utils.log_redaction import redact_sensitive


def response():
    return ResponseInfoModel(data_bytes=b"{}", status=200, headers={}, url="https://example.com")


@pytest.mark.parametrize(
    "value",
    [
        {
            "headers": {
                "Spa-Trace-Id": "trace-secret",
                "authorization": "Bearer secret-token",
                "cookie": "session=secret",
            },
            "trace_id": "trace-secret-2",
            "password": "plain-password",
            "cardNumber": "4111111111111111",
            "cardCVV": "123",
        },
        '{"Spa-Trace-Id": "trace-json-secret"}',
        "Spa-Trace-Id=trace-form-secret",
        "grant_type=client_credentials&client_secret=TOPSECRET",
        ["Bearer secret-token", {"password": "plain-password"}],
        ("4111111111111111", "123"),
    ],
    ids=["dict", "json", "trace-form", "secret-form", "list", "tuple"],
)
def test_log_values_are_returned_without_redaction(value):
    assert redact_sensitive(value) == value


def test_http_logger_keeps_card_authentication_and_form_data(monkeypatch):
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

    headers = {
        "authorization": "Bearer secret-token",
        "x-d-token": "risk-token",
        "Spa-Trace-Id": "trace-token",
    }
    card_data = json.dumps({"pan": "4111111111111111", "CVV": "123"})
    form = "grant_type=client_credentials&client_secret=TOPSECRET"

    send(object(), url="https://example.com/pay", headers=headers, data=card_data)
    with pytest.raises(RuntimeError):
        send(object(), url="https://example.com/oauth", headers=headers, data=form, fail=True)

    output = " ".join(captured)
    for expected in (
        "4111111111111111",
        "123",
        "secret-token",
        "risk-token",
        "trace-token",
        "TOPSECRET",
    ):
        assert expected in output
    assert "[REDACTED]" not in output


def test_task_logger_keeps_payment_payload_before_validation(monkeypatch):
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
    assert "4111111111111111" in output
    assert "'cardCVV': '123'" in output
    assert "[REDACTED]" not in output
