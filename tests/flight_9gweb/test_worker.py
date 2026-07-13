from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
LAUNCHER = ROOT / "flights/sunphuquocairways_9g/start-web.sh"
DOCKERFILE = ROOT / "flights/sunphuquocairways_9g/Dockerfile.web"


def test_launcher_routes_all_web_task_types_and_queues():
    source = LAUNCHER.read_text()

    for task_type in ("search", "verify", "shamBooking", "booking", "orderDetail"):
        assert f'"{task_type}"' in source
        assert f'9GWEB-{task_type}' in source or '${PREFIX}-${TASK_TYPE}' in source
    for module in (
        "task.9Gweb.search",
        "task.9Gweb.sham_booking",
        "task.9Gweb.booking",
        "task.9Gweb.order_detail",
    ):
        assert module in source


def test_web_dockerfile_uses_python_313_and_copies_web_tasks():
    source = DOCKERFILE.read_text()

    assert "FROM python:3.13-slim" in source
    assert "requirements-py313.txt" in source
    assert "COPY ./task/9Gweb /app/task/9Gweb" in source
    assert "start-web.sh" in source
