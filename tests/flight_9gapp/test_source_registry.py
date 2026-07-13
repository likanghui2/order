import ast
import importlib
from pathlib import Path
import runpy
from unittest.mock import Mock

import pytest

from app.source_registry import module_for_source
from common.enums.freight_rate_type_enum import FreightRateTypeEnum
from common.model.task.request_search_task_data_model import RequestSearchTaskDataModel

search_module = importlib.import_module("task.9Gapp.search")
_app_date = search_module._app_date
_run_search = search_module._run_search


def test_registry_discovers_9gapp_search():
    assert module_for_source("9GAPP", "search") == "task.9Gapp.search"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("20260801", "2026-08-01T00:00:00.000"),
        ("2026-08-01", "2026-08-01T00:00:00.000"),
        (None, None),
        ("", None),
    ],
)
def test_app_date_normalizes_current_task_dates(value, expected):
    assert _app_date(value) == expected


def test_run_search_maps_all_current_task_fields():
    service = Mock()
    service.search.return_value = ["journey"]
    search_data = RequestSearchTaskDataModel(
        depAirport="SGN",
        arrAirport="PQC",
        depDate="20260801",
        retDate="2026-08-04",
        adultNumber=2,
        childNumber=1,
        currencyCode="VND",
        freightRateType=FreightRateTypeEnum.PT,
        privateCode=["SAVE"],
    )

    assert _run_search(service, search_data) == ["journey"]
    service.search.assert_called_once_with(
        dep_airport="SGN",
        arr_airport="PQC",
        dep_date="2026-08-01T00:00:00.000",
        ret_date="2026-08-04T00:00:00.000",
        adt_number=2,
        chd_number=1,
        currency_code="VND",
        promo_code="SAVE",
    )


@pytest.mark.parametrize(
    ("module_path", "task_type"),
    [
        (Path("task/9Gapp/search.py"), "search"),
        (Path("task/9Gapp/sham_booking.py"), "shamBooking"),
    ],
)
def test_9gapp_task_has_guarded_local_example(module_path, task_type):
    source = module_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    guards = [
        node
        for node in tree.body
        if isinstance(node, ast.If)
        and isinstance(node.test, ast.Compare)
        and isinstance(node.test.left, ast.Name)
        and node.test.left.id == "__name__"
        and any(
            isinstance(item, ast.Constant) and item.value == "__main__"
            for item in node.test.comparators
        )
    ]

    assert len(guards) == 1
    assert '"source": "9GAPP"' in source
    assert f'"taskType": "{task_type}"' in source
    assert "main({" in source


@pytest.mark.parametrize(
    "module_path",
    [Path("task/9Gapp/search.py"), Path("task/9Gapp/sham_booking.py")],
)
def test_9gapp_task_can_load_as_direct_script_without_running_example(module_path):
    runpy.run_path(str(module_path), run_name="direct_script_import_check")
