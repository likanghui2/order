# 9G App Local Main Examples Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add directly executable local request examples to the 9G App search and sham-booking task modules.

**Architecture:** Each task module keeps its production path unchanged and adds a guarded `if __name__ == "__main__":` block containing one complete current-framework task payload. An AST-based unit test verifies both guards and their task metadata without executing network calls.

**Tech Stack:** Python 3.13, AST, pytest, current Celery task wrappers.

## Global Constraints

- Add examples only to `task/9Gapp/search.py` and `task/9Gapp/sham_booking.py`.
- Do not execute examples when modules are imported.
- Use source identifier `9GAPP` and current task payload aliases.
- Do not commit real proxy credentials.
- Preserve all existing search and sham-booking behavior.

---

### Task 1: Add Guarded Local Examples

**Files:**
- Modify: `task/9Gapp/search.py`
- Modify: `task/9Gapp/sham_booking.py`
- Modify: `tests/flight_9gapp/test_source_registry.py`

**Interfaces:**
- Consumes: the existing decorated `main` Celery task in each module.
- Produces: a direct `python task/9Gapp/search.py` search example and a direct `python task/9Gapp/sham_booking.py` sham-booking example.

- [ ] **Step 1: Write the failing AST test**

Add a parametrized test that proves each module has a guarded example with the correct task type:

```python
import ast
from pathlib import Path


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
        and any(isinstance(item, ast.Constant) and item.value == "__main__" for item in node.test.comparators)
    ]
    assert len(guards) == 1
    assert '"source": "9GAPP"' in source
    assert f'"taskType": "{task_type}"' in source
    assert "main({" in source
```

- [ ] **Step 2: Run the test and verify RED**

Run: `PYTHONPATH=. /Users/a1234/Desktop/rakdFlightLocalShamBooking/.venv/bin/pytest tests/flight_9gapp/test_source_registry.py::test_9gapp_task_has_guarded_local_example -q`

Expected: two failures because neither task module contains a `__main__` guard.

- [ ] **Step 3: Add the search example**

Append this shape to `task/9Gapp/search.py`, using placeholder proxy values exactly as shown:

```python
if __name__ == "__main__":
    print(main({
        "taskId": "9gapp-local-search",
        "taskType": "search",
        "source": "9GAPP",
        "taskData": {
            "depAirport": "SGN",
            "arrAirport": "PQC",
            "depDate": "20260720",
            "retDate": "",
            "adultNumber": 1,
            "childNumber": 0,
            "currencyCode": "VND",
            "freightRateType": "PT",
            "privateCode": [],
            "ext": {"proxy": {
                "host": "proxy.example.com",
                "port": 8080,
                "username": "YOUR_USERNAME",
                "password": "YOUR_PASSWORD",
                "region": "vn",
                "sessId": None,
                "sessionTime": 10,
                "format": "http://{username}:{password}@{host}:{port}",
            }},
        },
    }))
```

- [ ] **Step 4: Add the sham-booking example**

Append the complete current-framework request and a warning to refresh flight data:

```python
if __name__ == "__main__":
    # 运行前请先实时搜索，并更新日期、航班号、舱位和产品。
    print(main({
        "taskId": "9gapp-local-sham-booking",
        "taskType": "shamBooking",
        "source": "9GAPP",
        "taskData": {
            "depAirport": "SGN",
            "arrAirport": "PQC",
            "depDate": "20260720",
            "flightNumber": "9G0123",
            "cabin": "Y",
            "bookingConfig": {"bookRate": 10, "currencyCode": "VND"},
            "ext": {
                "productTag": "ECONOMY LITE",
                "proxy": {
                    "host": "proxy.example.com",
                    "port": 8080,
                    "username": "YOUR_USERNAME",
                    "password": "YOUR_PASSWORD",
                    "region": "vn",
                    "sessId": None,
                    "sessionTime": 10,
                    "format": "http://{username}:{password}@{host}:{port}",
                },
            },
        },
    }))
```

- [ ] **Step 5: Run focused and complete tests**

Run: `PYTHONPATH=. /Users/a1234/Desktop/rakdFlightLocalShamBooking/.venv/bin/pytest tests/flight_9gapp/test_source_registry.py -q`

Expected: all registry/example tests pass.

Run: `PYTHONPATH=. /Users/a1234/Desktop/rakdFlightLocalShamBooking/.venv/bin/pytest -q`

Expected: all repository tests pass without contacting 9G because the examples remain guarded.

- [ ] **Step 6: Verify direct-script syntax and migration boundary**

Run: `PYTHONPATH=. /Users/a1234/Desktop/rakdFlightLocalShamBooking/.venv/bin/python -m compileall -q task/9Gapp tests/flight_9gapp`

Expected: exit 0.

Run: `git diff --check`

Expected: no whitespace errors in the new changes.

- [ ] **Step 7: Commit**

```bash
git add task/9Gapp/search.py task/9Gapp/sham_booking.py tests/flight_9gapp/test_source_registry.py
git commit -m "test(9gapp): add local task examples"
```
