import ast
import importlib
from pathlib import Path

from app.source_registry import module_for_source
from common.enums.freight_rate_type_enum import FreightRateTypeEnum
from common.model.task.request_search_task_data_model import RequestSearchTaskDataModel


search_module = importlib.import_module("task.9Gweb.search")


class FakeService:
    def __init__(self):
        self.calls = []

    def search(self, **kwargs):
        self.calls.append(kwargs)
        return ["journey-1"]


def request(**changes):
    data = {
        "depAirport": "SGN",
        "arrAirport": "PQC",
        "depDate": "20260801",
        "retDate": "2026-08-04",
        "adultNumber": 2,
        "childNumber": 1,
        "currencyCode": "VND",
        "freightRateType": FreightRateTypeEnum.PT,
        "privateCode": ["SAVE"],
        "ext": {},
    }
    data.update(changes)
    return RequestSearchTaskDataModel.model_validate(data)


def test_run_search_normalizes_dates_and_forwards_promo():
    service = FakeService()

    result = search_module._run_search(service, request())

    assert result == ["journey-1"]
    assert service.calls == [
        {
            "dep_airport": "SGN",
            "arr_airport": "PQC",
            "dep_date": "2026-08-01T00:00:00",
            "ret_date": "2026-08-04T00:00:00",
            "adt_number": 2,
            "chd_number": 1,
            "currency_code": "VND",
            "promo_code": "SAVE",
        }
    ]


def test_registry_discovers_search_and_verify():
    assert module_for_source("9GWEB", "search") == "task.9Gweb.search"
    assert module_for_source("9gweb", "verify") == "task.9Gweb.search"


def test_search_has_guarded_local_example():
    source = Path(search_module.__file__).read_text()
    tree = ast.parse(source)
    assert any(
        isinstance(node, ast.If)
        and isinstance(node.test, ast.Compare)
        and isinstance(node.test.left, ast.Name)
        and node.test.left.id == "__name__"
        for node in tree.body
    )

