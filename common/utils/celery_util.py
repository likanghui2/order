from typing import Callable, Optional


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


def create(*args, **kwargs):
    return LocalCeleryApp()
