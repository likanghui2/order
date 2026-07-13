import ast
import importlib
from pathlib import Path

from app.source_registry import module_for_source
from common.enums.order_state_enum import OrderStateEnum
from common.model.task.request_order_detail_task_model import RequestOrderDetailTaskModel
from common.model.task.response_order_info_model import ResponseOrderInfoModel


module = importlib.import_module("task.9Gweb.order_detail")


class FakeService:
    def __init__(self):
        self.calls = []

    def order_detail(self, pnr, last_name, currency_code):
        self.calls.append((pnr, last_name, currency_code))
        return ResponseOrderInfoModel(pnr=pnr, orderState=OrderStateEnum.HOLD)


def test_order_detail_forwards_pnr_last_name_and_currency():
    service = FakeService()
    request = RequestOrderDetailTaskModel.model_validate(
        {"pnr": "ABC123", "lastName": "LOVELACE", "firstName": "ADA", "currencyCode": "USD"}
    )

    result = module._run_order_detail(service, request)

    assert service.calls == [("ABC123", "LOVELACE", "USD")]
    assert result.order_state == OrderStateEnum.HOLD


def test_order_detail_registry_and_guarded_local_example():
    assert module_for_source("9GWEB", "orderDetail") == "task.9Gweb.order_detail"
    tree = ast.parse(Path(module.__file__).read_text())
    assert any(
        isinstance(node, ast.If)
        and isinstance(node.test, ast.Compare)
        and isinstance(node.test.left, ast.Name)
        and node.test.left.id == "__name__"
        for node in tree.body
    )
