import json
import importlib

from common.decorators.http_log_decorator import http_log_decorator
from common.model.response_info_model import ResponseInfoModel


def response():
    return ResponseInfoModel(data_bytes=b"{}", status=200, headers={}, url="https://example.com")


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
