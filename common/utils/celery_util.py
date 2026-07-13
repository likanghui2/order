import os
import urllib.parse
from typing import Callable, Optional

from common.global_variable import GlobalVariable


class LocalBackend:
    def __init__(self):
        self.expires = None


class LocalTask:
    def __init__(self, func: Callable, bind: bool = False, name: Optional[str] = None):
        self.run = func
        self.bind = bind
        self.name = name or f"{func.__module__}.{func.__name__}"
        self.__name__ = getattr(func, "__name__", self.name)
        self.__doc__ = getattr(func, "__doc__", None)
        self.backend = LocalBackend()

    def __call__(self, *args, **kwargs):
        if self.bind:
            return self.run(self, *args, **kwargs)
        return self.run(*args, **kwargs)


class LocalCeleryApp:
    def task(self, *decorator_args, **decorator_kwargs):
        bind = bool(decorator_kwargs.get("bind", False))
        name = decorator_kwargs.get("name")

        if decorator_args and callable(decorator_args[0]):
            return LocalTask(decorator_args[0], bind=bind, name=name)

        def decorator(func: Callable):
            return LocalTask(func, bind=bind, name=name)

        return decorator

    def send_task(self, *args, **kwargs):
        raise RuntimeError("本地押位项目已取消队列机制，请直接调用任务函数执行")


def _enabled(name: str) -> bool:
    return str(os.environ.get(name) or "").strip().lower() in {"1", "true", "yes", "on"}


def _real_celery_app(username: str, password: str, task_routes: dict, close_output: bool):
    try:
        import celery
    except ImportError as error:
        raise RuntimeError("USE_REAL_CELERY=1 requires the celery package") from error

    user = urllib.parse.quote(str(username or ""), safe="")
    secret = urllib.parse.quote(str(password or ""), safe="")
    virtual_host = urllib.parse.quote(str(GlobalVariable.RABBITMQ_VIRTUAL_HOST or ""), safe="")
    broker = (
        f"amqp://{user}:{secret}@{GlobalVariable.RABBITMQ_HOST}:"
        f"{GlobalVariable.RABBITMQ_PORT}/{virtual_host}"
    )
    app = celery.Celery("flight_worker", broker=broker)
    if not close_output:
        redis_user = urllib.parse.quote(str(GlobalVariable.REDIS_USERNAME or ""), safe="")
        redis_password = urllib.parse.quote(str(GlobalVariable.REDIS_PASSWORD or ""), safe="")
        auth = f"{redis_user}:{redis_password}@" if redis_user or redis_password else ""
        app.conf.result_backend = (
            f"redis://{auth}{GlobalVariable.REDIS_HOST}:{GlobalVariable.REDIS_PORT}/"
            f"{GlobalVariable.REDIS_TASK_RESULT_DB}"
        )
    app.conf.update(
        task_routes=task_routes,
        timezone="Asia/Shanghai",
        enable_utc=False,
        result_expires=3600,
        worker_redirect_stdouts=False,
        worker_prefetch_multiplier=1,
        broker_connection_max_retries=None,
        broker_connection_retry_on_startup=True,
        broker_channel_error_retry=True,
        worker_max_tasks_per_child=100,
        worker_enable_remote_control=False,
        task_acks_late=False,
    )
    return app


def create(
    username: str = "",
    password: str = "",
    task_routes: Optional[dict] = None,
    close_output: bool = False,
):
    if _enabled("USE_REAL_CELERY"):
        return _real_celery_app(username, password, task_routes or {}, close_output)
    return LocalCeleryApp()
