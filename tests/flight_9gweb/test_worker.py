from pathlib import Path

from celery import Celery

from common.utils import celery_util


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
    assert source.count(":CELERY_APP") == 4


def test_web_dockerfile_uses_python_313_and_copies_web_tasks():
    source = DOCKERFILE.read_text()

    assert "FROM python:3.13-slim" in source
    assert "requirements-py313.txt" in source
    assert "COPY ./task/9Gweb /app/task/9Gweb" in source
    assert "start-web.sh" in source
    assert "USE_REAL_CELERY=1" in source


def test_python_313_requirements_include_real_celery_worker():
    requirements = (ROOT / "requirements-py313.txt").read_text().lower()
    assert "celery" in requirements


def test_real_worker_mode_builds_a_celery_app(monkeypatch):
    monkeypatch.setenv("USE_REAL_CELERY", "1")

    app = celery_util.create("worker user", "p@ss", {"task.name": {"queue": "9GWEB-search"}})

    assert isinstance(app, Celery)
    assert app.conf.broker_url.startswith("amqp://worker%20user:p%40ss@")
    assert app.conf.task_routes == {"task.name": {"queue": "9GWEB-search"}}
    assert app.conf.worker_prefetch_multiplier == 1
