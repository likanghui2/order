#!/usr/bin/env python3
import argparse
import json
import signal
import sqlite3
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional


APP_DIR = Path(__file__).resolve().parents[1]
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from common.model.proxy_Info_model import ProxyInfoModel
from flights.sunphuquocairways_9g.config import Config
from flights.sunphuquocairways_9g.flight_common.app_trace_cache import NineGAppTraceCache
from flights.sunphuquocairways_9g.flight_common.booking_utils import app_date
from flights.sunphuquocairways_9g.script.app_script import AppScript


SOURCE = "9GAPP"
ACTIVE_STATUS = "ACTIVE"
SUPPORTED_TASK_TYPES = {"search", "shambooking"}
_PRODUCER_LOCK = threading.RLock()
_PRODUCER: Optional["TraceTokenProducer"] = None
_PRODUCER_THREAD: Optional[threading.Thread] = None


@dataclass(frozen=True)
class ProducerSettings:
    db_path: Path = APP_DIR / "local_sham_booking.db"
    target_size: int = 20  # Redis 中 ready + warming Token 的目标库存数量
    batch_size: int = 1  # 每轮最多新建多少个 Session 并查询生产 Token
    interval_seconds: float = 2.0  # 成功生产一轮后，到下一轮生产前的等待秒数
    idle_interval_seconds: float = 10.0  # 无任务、无代理或库存已满时的检查间隔秒数
    error_interval_seconds: float = 10.0  # 生产失败或程序异常后的重试等待秒数


@dataclass(frozen=True)
class TraceSearchJob:
    task_id: str
    dep_airport: str
    arr_airport: str
    dep_date: str
    adult_count: int
    child_count: int
    currency_code: str
    promo_code: str


class TraceTokenProducer:
    def __init__(
        self,
        settings: ProducerSettings,
        cache=None,
        script_factory: Optional[Callable[[ProxyInfoModel], AppScript]] = None,
        stop_event: Optional[threading.Event] = None,
    ) -> None:
        self.settings = settings
        self.cache = cache if cache is not None else NineGAppTraceCache()
        self.script_factory = script_factory or self._default_script_factory
        self.stop_event = stop_event or threading.Event()
        self._job_cursor = 0

    @staticmethod
    def _default_script_factory(proxy_info: ProxyInfoModel) -> AppScript:
        return AppScript(proxy_info.model_copy(deep=True))

    def warm_once(self) -> dict:
        before = self.cache.stats()
        missing = max(0, self.settings.target_size - int(before["total"]))
        if missing == 0:
            return {"reason": "pool_full", "produced": 0, "stats": before}

        jobs = self._active_jobs()
        if not jobs:
            return {"reason": "no_active_tasks", "produced": 0, "stats": before}

        proxy_info = self._enabled_proxy()
        if proxy_info is None:
            return {"reason": "no_enabled_proxy", "produced": 0, "stats": before}

        produced = 0
        errors = []
        attempt_count = min(missing, self.settings.batch_size)
        for offset in range(attempt_count):
            if self.stop_event.is_set():
                break
            job = jobs[(self._job_cursor + offset) % len(jobs)]
            try:
                script = self.script_factory(proxy_info)
                script.initialize_session()
                script.search(
                    airport_data=[(job.dep_airport, job.arr_airport, job.dep_date)],
                    adult_count=job.adult_count,
                    child_count=job.child_count,
                    infant_count=0,
                    promo_code=job.promo_code,
                    **Config.currency_context(job.currency_code),
                )
                produced += 1
            except Exception as error:
                errors.append({"taskId": job.task_id, "error": str(error)})
        self._job_cursor = (self._job_cursor + attempt_count) % len(jobs)
        after = self.cache.stats()
        reason = "produced" if produced else "production_failed"
        return {"reason": reason, "produced": produced, "errors": errors, "stats": after}

    def run_forever(self) -> None:
        while not self.stop_event.is_set():
            try:
                result = self.warm_once()
                print(json.dumps(result, ensure_ascii=False), flush=True)
                if result["reason"] in {"no_active_tasks", "no_enabled_proxy", "pool_full"}:
                    wait_seconds = self.settings.idle_interval_seconds
                elif result["reason"] == "production_failed":
                    wait_seconds = self.settings.error_interval_seconds
                else:
                    wait_seconds = self.settings.interval_seconds
            except Exception as error:
                print(
                    json.dumps({"reason": "producer_error", "error": str(error)}, ensure_ascii=False),
                    flush=True,
                )
                wait_seconds = self.settings.error_interval_seconds
            self.stop_event.wait(wait_seconds)

    def _active_jobs(self) -> list[TraceSearchJob]:
        if not self.settings.db_path.exists():
            return []
        try:
            with sqlite3.connect(self.settings.db_path) as connection:
                connection.row_factory = sqlite3.Row
                rows = connection.execute(
                    """
                    SELECT task_id, task_type, task_data
                    FROM tasks
                    WHERE upper(source) = ? AND upper(status) = ?
                        AND lower(task_type) IN ('search', 'shambooking')
                    ORDER BY task_id ASC
                    """,
                    (SOURCE, ACTIVE_STATUS),
                ).fetchall()
        except sqlite3.Error:
            return []

        jobs = []
        seen = set()
        for row in rows:
            job = self._job_from_row(row)
            if job is None:
                continue
            key = (
                job.dep_airport,
                job.arr_airport,
                job.dep_date,
                job.adult_count,
                job.child_count,
                job.currency_code,
                job.promo_code,
            )
            if key not in seen:
                seen.add(key)
                jobs.append(job)
        return jobs

    @staticmethod
    def _job_from_row(row: sqlite3.Row) -> Optional[TraceSearchJob]:
        try:
            data = json.loads(row["task_data"])
        except (json.JSONDecodeError, TypeError):
            return None
        if not isinstance(data, dict):
            return None

        dep_airport = str(data.get("depAirport") or "").strip().upper()
        arr_airport = str(data.get("arrAirport") or "").strip().upper()
        dep_date = app_date(data.get("depDate"))
        if not dep_airport or not arr_airport or not dep_date:
            return None

        task_type = str(row["task_type"] or "").strip().lower()
        booking_config = data.get("bookingConfig")
        booking_config = booking_config if isinstance(booking_config, dict) else {}
        currency_code = str(
            data.get("currencyCode") or booking_config.get("currencyCode") or "VND"
        ).strip().upper()
        adult_count = max(1, int(data.get("adultNumber") or 1))
        child_count = max(0, int(data.get("childNumber") or 0))
        if task_type == "shambooking":
            adult_count = 1
            child_count = 0
        private_codes = data.get("privateCode")
        promo_code = str(private_codes[0]).strip() if isinstance(private_codes, list) and private_codes else ""
        return TraceSearchJob(
            task_id=str(row["task_id"]),
            dep_airport=dep_airport,
            arr_airport=arr_airport,
            dep_date=dep_date,
            adult_count=adult_count,
            child_count=child_count,
            currency_code=currency_code,
            promo_code=promo_code,
        )

    def _enabled_proxy(self) -> Optional[ProxyInfoModel]:
        if not self.settings.db_path.exists():
            return None
        try:
            with sqlite3.connect(self.settings.db_path) as connection:
                connection.row_factory = sqlite3.Row
                row = connection.execute(
                    """
                    SELECT host, port, username, password, region, session_time, format
                    FROM source_proxy_configs
                    WHERE upper(source) = ? AND enabled = 1
                    """,
                    (SOURCE,),
                ).fetchone()
        except sqlite3.Error:
            return None
        if not row or not row["host"] or row["port"] is None or not row["format"]:
            return None
        return ProxyInfoModel(
            host=str(row["host"]).strip(),
            port=int(row["port"]),
            username=str(row["username"] or "").strip() or None,
            password=str(row["password"] or "").strip() or None,
            region=str(row["region"] or "").strip() or None,
            session_time=int(row["session_time"]) if row["session_time"] else None,
            format=str(row["format"]).strip(),
        )


def _start_producer(producer: Optional[TraceTokenProducer] = None) -> threading.Thread:
    global _PRODUCER, _PRODUCER_THREAD
    with _PRODUCER_LOCK:
        if _PRODUCER_THREAD and _PRODUCER_THREAD.is_alive():
            return _PRODUCER_THREAD
        _PRODUCER = producer or TraceTokenProducer(ProducerSettings())
        _PRODUCER_THREAD = threading.Thread(
            target=_PRODUCER.run_forever,
            name="nine-g-app-trace-token-producer",
            daemon=True,
        )
        _PRODUCER_THREAD.start()
        return _PRODUCER_THREAD


def _stop_producer() -> None:
    global _PRODUCER, _PRODUCER_THREAD
    with _PRODUCER_LOCK:
        producer = _PRODUCER
        thread = _PRODUCER_THREAD
        if producer is not None:
            producer.stop_event.set()
    if thread and thread.is_alive():
        thread.join(timeout=5)
    with _PRODUCER_LOCK:
        _PRODUCER = None
        _PRODUCER_THREAD = None


def producer_status() -> dict[str, bool]:
    with _PRODUCER_LOCK:
        return {"running": bool(_PRODUCER_THREAD and _PRODUCER_THREAD.is_alive())}


def main() -> None:
    parser = argparse.ArgumentParser(description="9G App Trace Token 独立生产器")
    parser.add_argument("--once", action="store_true", help="只执行一轮后退出")
    args = parser.parse_args()

    producer = TraceTokenProducer(ProducerSettings())
    if args.once:
        print(json.dumps(producer.warm_once(), ensure_ascii=False))
        return

    signal.signal(signal.SIGINT, lambda *_: producer.stop_event.set())
    signal.signal(signal.SIGTERM, lambda *_: producer.stop_event.set())
    producer.run_forever()


if __name__ == "__main__":
    main()
