import importlib
import copy
import json
import threading
import time
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from typing import Any, Callable, Optional

from common.model.proxy_Info_model import ProxyInfoModel
from common.utils import log_util

from .source_registry import module_for_source
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

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        try:
            self.store.reset_stale_in_flight(older_than_seconds=0)
        except Exception as exc:
            LOG.error({"error": str(exc)}, "重置本地任务状态失败")
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
            try:
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
            except Exception as exc:
                LOG.error({"error": str(exc)}, "本地执行器轮询异常")
                self._stop_event.wait(max(3, self.poll_interval))
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
        attempt = self.store.start_attempt(task_id)
        attempt_no = int(attempt["attempt_no"])
        execution_task_id = str(attempt["execution_task_id"])
        start = time.perf_counter()
        try:
            task_data = self._task_data_with_proxy(task["source"], task["task_data"])
            payload = {
                "taskId": execution_task_id,
                "source": task["source"],
                "taskType": task["task_type"],
                "taskData": task_data,
            }
            task_callable = self._load_task(task["source"], task["task_type"])
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
            LOG.error({"taskId": task_id, "executionTaskId": execution_task_id, "error": str(exc)}, "本地执行异常")
            self.store.fail_attempt(task_id, attempt_no, f"本地执行异常: {exc}", time.perf_counter() - start)

    def _load_task(self, source: str, task_type: str) -> Callable[[dict[str, Any]], Any]:
        source = source.upper()
        cache_key = f"{source}:{task_type}"
        if cache_key in self._task_cache:
            return self._task_cache[cache_key]
        module_name = module_for_source(source, task_type)
        if not module_name:
            raise ValueError(f"不支持的 source/taskType: {source}/{task_type}")
        module = importlib.import_module(module_name)
        task = getattr(module, "main")
        self._task_cache[cache_key] = task
        return task

    def _task_data_with_proxy(self, source: str, task_data: Any) -> Any:
        if not isinstance(task_data, dict):
            return task_data
        data = copy.deepcopy(task_data)
        proxy_payload = self._source_proxy_ext_payload(source)
        if not proxy_payload:
            return data
        ext = data.get("ext")
        if not isinstance(ext, dict):
            ext = {}
        ext["proxy"] = proxy_payload
        data["ext"] = ext
        return data

    def _source_proxy_ext_payload(self, source: str) -> Optional[dict[str, Any]]:
        config = self.store.get_source_proxy_config(source)
        if not config or not config.get("enabled"):
            return None
        proxy = self._build_proxy_info_from_config(source, config)
        return self._proxy_info_to_ext(proxy, source)

    def _build_proxy_info_from_config(self, source: str, config: dict[str, Any]) -> ProxyInfoModel:
        host = str(config.get("host") or "").strip()
        port = config.get("port")
        if not host or port is None:
            raise ValueError(f"{source} 代理已启用，但 host/port 未配置")
        format_value = str(config.get("format") or "").strip()
        if not format_value:
            raise ValueError(f"{source} 代理已启用，但 format 未配置")
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
    def _proxy_info_to_ext(proxy: ProxyInfoModel, source: str) -> dict[str, Any]:
        return {
            "source": source.upper(),
            "host": proxy.host,
            "port": proxy.port,
            "username": proxy.username,
            "password": proxy.password,
            "region": proxy.region,
            "sessId": proxy.sess_id,
            "sessionTime": proxy.session_time,
            "format": proxy.format,
        }

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
