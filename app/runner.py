import importlib
import json
import threading
import time
from contextlib import contextmanager
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from typing import Any, Callable, Iterator, Optional

from common.global_variable import GlobalVariable
from common.model.proxy_Info_model import ProxyInfoModel
from common.utils import log_util

from .proxy_context import ensure_thread_local_proxy_provider
from .source_registry import SOURCE_MODULES
from .store import TaskStore


LOG = log_util.LogUtil("sqliteShamRunner")


class LocalRunner:
    def __init__(self, store: TaskStore, concurrency: int = 1, poll_interval: float = 0.5):
        self.store = store
        self.concurrency = concurrency
        self.unlimited = concurrency <= 0
        self.poll_interval = poll_interval
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._executor: Optional[ThreadPoolExecutor] = None
        self._running: dict[Future, str] = {}
        self._running_threads: dict[threading.Thread, str] = {}
        self._running_lock = threading.RLock()
        self._task_cache: dict[str, Callable[[dict[str, Any]], Any]] = {}
        self._proxy_provider = ensure_thread_local_proxy_provider(GlobalVariable.PROXY_INFO_DATA)
        GlobalVariable.PROXY_INFO_DATA = self._proxy_provider
        self._default_proxy = self._proxy_provider.default_copy()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self.store.reset_stale_in_flight(older_than_seconds=0)
        self._executor = None if self.unlimited else ThreadPoolExecutor(max_workers=max(1, self.concurrency))
        self._thread = threading.Thread(target=self._run, name="local-sham-runner", daemon=True)
        self._thread.start()
        LOG.info(
            {
                "concurrency": "unlimited" if self.unlimited else self.concurrency,
                "pollInterval": self.poll_interval,
            },
            "本地执行器已启动",
        )

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
        if self._executor:
            self._executor.shutdown(wait=False, cancel_futures=False)
        LOG.info("本地执行器已停止")

    def stats(self) -> dict[str, Any]:
        with self._running_lock:
            running = len(self._running) + len(self._running_threads)
        return {
            "running": running,
            "concurrency": self.concurrency,
            "unlimited": self.unlimited,
            "pollInterval": self.poll_interval,
        }

    def _run(self) -> None:
        while not self._stop_event.is_set():
            self._collect_finished(block=False)
            if self.unlimited:
                for task in self.store.acquire_due_tasks(0):
                    self._start_unlimited_task(task)
            else:
                assert self._executor is not None
                with self._running_lock:
                    free_slots = self.concurrency - len(self._running)
                if free_slots > 0:
                    for task in self.store.acquire_due_tasks(free_slots):
                        future = self._executor.submit(self._execute_task, task)
                        with self._running_lock:
                            self._running[future] = task["task_id"]
            self._stop_event.wait(self.poll_interval)
        self._collect_finished(block=True)

    def _start_unlimited_task(self, task: dict[str, Any]) -> None:
        thread = threading.Thread(
            target=self._execute_task_thread,
            args=(task,),
            name=f"local-sham-{task['task_id']}",
            daemon=True,
        )
        with self._running_lock:
            self._running_threads[thread] = task["task_id"]
        thread.start()

    def _execute_task_thread(self, task: dict[str, Any]) -> None:
        try:
            self._execute_task(task)
        finally:
            with self._running_lock:
                self._running_threads.pop(threading.current_thread(), None)

    def _execute_task(self, task: dict[str, Any]) -> None:
        task_id = task["task_id"]
        attempt_no = self.store.start_attempt(task_id)
        start = time.perf_counter()
        try:
            payload = {
                "taskId": task_id,
                "source": task["source"],
                "taskType": task["task_type"],
                "taskData": task["task_data"],
            }
            task_callable = self._load_task(task["source"])
            with self._source_proxy(task["source"]):
                result = task_callable(payload)
            parsed = self._parse_result(result)
            self.store.finish_attempt(
                task_id=task_id,
                attempt_no=attempt_no,
                status_code=int(parsed.get("status") or 0),
                message=str(parsed.get("message") or ""),
                result=parsed,
                duration_seconds=time.perf_counter() - start,
            )
        except Exception as exc:
            LOG.error({"taskId": task_id, "error": str(exc)}, "本地执行异常")
            self.store.fail_attempt(task_id, attempt_no, f"本地执行异常: {exc}", time.perf_counter() - start)

    def _load_task(self, source: str) -> Callable[[dict[str, Any]], Any]:
        source = source.upper()
        if source in self._task_cache:
            return self._task_cache[source]
        module_name = SOURCE_MODULES.get(source)
        if not module_name:
            raise ValueError(f"不支持的 source: {source}")
        module = importlib.import_module(module_name)
        task = getattr(module, "main")
        self._task_cache[source] = task
        return task

    @contextmanager
    def _source_proxy(self, source: str) -> Iterator[None]:
        self._proxy_provider.set_current(self._build_proxy_info(source))
        try:
            yield
        finally:
            self._proxy_provider.clear_current()

    def _build_proxy_info(self, source: str) -> ProxyInfoModel:
        config = self.store.get_source_proxy_config(source)
        if not config or not config.get("enabled"):
            return self._default_proxy.model_copy(deep=True)
        host = str(config.get("host") or "").strip()
        port = config.get("port")
        if not host or port is None:
            raise ValueError(f"{source} 代理已启用，但 host/port 未配置")
        format_value = str(config.get("format") or "").strip() or self._default_proxy_format(config)
        return ProxyInfoModel(
            host=host,
            port=int(port),
            username=str(config.get("username") or "").strip() or None,
            password=str(config.get("password") or "").strip() or None,
            region=str(config.get("region") or "").strip() or None,
            session_time=int(config["session_time"]) if config.get("session_time") else None,
            format=format_value,
        )

    @staticmethod
    def _default_proxy_format(config: dict[str, Any]) -> str:
        has_auth = bool(config.get("username") and config.get("password"))
        has_region_session = bool(config.get("region") and config.get("session_time"))
        if has_auth and has_region_session:
            return "http://client-{username}_area-{region}_session-{sessId}_life-{sessionTime}:{password}@{host}:{port}"
        if has_auth:
            return "http://{username}:{password}@{host}:{port}"
        return "http://{host}:{port}"

    def _collect_finished(self, block: bool) -> None:
        with self._running_lock:
            dead_threads = [thread for thread in self._running_threads if not thread.is_alive()]
            for thread in dead_threads:
                self._running_threads.pop(thread, None)
            futures = list(self._running.keys())
        if not futures:
            return
        timeout = None if block else 0
        done, _ = wait(futures, timeout=timeout, return_when=FIRST_COMPLETED)
        for future in done:
            with self._running_lock:
                task_id = self._running.pop(future, "")
            try:
                future.result()
            except Exception as exc:
                LOG.error({"taskId": task_id, "error": str(exc)}, "执行线程异常")

    @staticmethod
    def _parse_result(result: Any) -> dict[str, Any]:
        if isinstance(result, bytes):
            result = result.decode("utf-8")
        if isinstance(result, str):
            try:
                return json.loads(result)
            except json.JSONDecodeError:
                return {"status": 0, "message": result, "data": None}
        if isinstance(result, dict):
            return result
        return {"status": 0, "message": str(result), "data": None}
