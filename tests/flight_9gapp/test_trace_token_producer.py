import json
import sqlite3
import threading
from pathlib import Path

from tools import nine_g_app_trace_token_producer as producer_module
from tools.nine_g_app_trace_token_producer import ProducerSettings, TraceTokenProducer


class FakeCache:
    def __init__(self, total=0):
        self.total = total

    def stats(self):
        return {"warming": self.total, "ready": 0, "total": self.total}


class FakeScript:
    def __init__(self, cache, proxy):
        self.cache = cache
        self.proxy = proxy
        self.initialized = 0
        self.search_calls = []

    def initialize_session(self):
        self.initialized += 1

    def search(self, **kwargs):
        self.search_calls.append(kwargs)
        self.cache.total += 1
        return {"success": True, "trace_id": f"trace-{self.cache.total}"}


def create_db(path: Path):
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE tasks (
                task_id TEXT PRIMARY KEY,
                source TEXT NOT NULL,
                task_type TEXT NOT NULL,
                task_data TEXT NOT NULL,
                status TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE source_proxy_configs (
                source TEXT PRIMARY KEY,
                enabled INTEGER NOT NULL,
                host TEXT,
                port INTEGER,
                username TEXT,
                password TEXT,
                region TEXT,
                session_time INTEGER,
                format TEXT
            )
            """
        )


def add_task(path: Path, task_id: str, task_type: str, task_data: dict, status="ACTIVE"):
    with sqlite3.connect(path) as connection:
        connection.execute(
            "INSERT INTO tasks(task_id, source, task_type, task_data, status) VALUES (?, '9GAPP', ?, ?, ?)",
            (task_id, task_type, json.dumps(task_data), status),
        )


def add_proxy(path: Path, enabled=1):
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            INSERT INTO source_proxy_configs(
                source, enabled, host, port, username, password, region, session_time, format
            ) VALUES ('9GAPP', ?, 'proxy.example.com', 9000, 'user', 'pass', 'sg', 10,
                'http://{username}:{password}@{host}:{port}')
            """,
            (enabled,),
        )


def settings(db_path: Path, **overrides):
    values = {
        "db_path": db_path,
        "target_size": 3,
        "batch_size": 2,
        "interval_seconds": 2.0,
        "idle_interval_seconds": 10.0,
        "error_interval_seconds": 10.0,
    }
    values.update(overrides)
    return ProducerSettings(**values)


def test_producer_settings_use_fixed_local_defaults():
    current = ProducerSettings()

    assert current.db_path.name == "local_sham_booking.db"
    assert current.interval_seconds == 2.0
    assert current.idle_interval_seconds == 10.0
    assert current.error_interval_seconds == 10.0


def test_no_active_9gapp_task_means_no_network_traffic(tmp_path):
    db_path = tmp_path / "tasks.db"
    create_db(db_path)
    add_proxy(db_path)
    cache = FakeCache()
    scripts = []
    producer = TraceTokenProducer(
        settings(db_path),
        cache=cache,
        script_factory=lambda proxy: scripts.append(FakeScript(cache, proxy)),
    )

    result = producer.warm_once()

    assert result["reason"] == "no_active_tasks"
    assert result["produced"] == 0
    assert scripts == []


def test_paused_task_and_disabled_proxy_do_not_produce(tmp_path):
    db_path = tmp_path / "tasks.db"
    create_db(db_path)
    add_task(
        db_path,
        "paused",
        "search",
        {"depAirport": "SGN", "arrAirport": "PQC", "depDate": "20260720"},
        status="PAUSED",
    )
    add_proxy(db_path, enabled=0)
    producer = TraceTokenProducer(settings(db_path), cache=FakeCache(), script_factory=lambda proxy: None)

    assert producer.warm_once()["reason"] == "no_active_tasks"

    with sqlite3.connect(db_path) as connection:
        connection.execute("UPDATE tasks SET status = 'ACTIVE'")
    assert producer.warm_once()["reason"] == "no_enabled_proxy"


def test_active_tasks_supply_search_fields_and_enabled_proxy(tmp_path):
    db_path = tmp_path / "tasks.db"
    create_db(db_path)
    add_task(
        db_path,
        "search-1",
        "search",
        {
            "depAirport": "SGN",
            "arrAirport": "PQC",
            "depDate": "20260720",
            "adultNumber": 2,
            "childNumber": 1,
            "currencyCode": "VND",
            "privateCode": ["SAVE"],
        },
    )
    add_task(
        db_path,
        "sham-1",
        "shamBooking",
        {
            "depAirport": "PQC",
            "arrAirport": "SGN",
            "depDate": "2026-07-21",
            "bookingConfig": {"currencyCode": "USD"},
        },
    )
    add_proxy(db_path)
    cache = FakeCache()
    scripts = []

    def script_factory(proxy):
        script = FakeScript(cache, proxy)
        scripts.append(script)
        return script

    producer = TraceTokenProducer(settings(db_path), cache=cache, script_factory=script_factory)

    result = producer.warm_once()

    assert result["reason"] == "produced"
    assert result["produced"] == 2
    assert len(scripts) == 2
    assert all(script.initialized == 1 for script in scripts)
    assert scripts[0].proxy.host == "proxy.example.com"
    assert scripts[0].search_calls[0] == {
        "airport_data": [("SGN", "PQC", "2026-07-20T00:00:00.000")],
        "adult_count": 2,
        "child_count": 1,
        "infant_count": 0,
        "promo_code": "SAVE",
        "office_id": "HAN9G08MB",
        "accept_language": "vi",
        "x_lang": "vi",
    }
    assert scripts[1].search_calls[0]["airport_data"] == [
        ("PQC", "SGN", "2026-07-21T00:00:00.000")
    ]
    assert scripts[1].search_calls[0]["office_id"] == "WAS9G08MB"


def test_full_pool_skips_database_and_network(tmp_path):
    missing_db = tmp_path / "missing.db"
    scripts = []
    producer = TraceTokenProducer(
        settings(missing_db, target_size=3),
        cache=FakeCache(total=3),
        script_factory=lambda proxy: scripts.append(FakeScript(None, proxy)),
    )

    result = producer.warm_once()

    assert result["reason"] == "pool_full"
    assert scripts == []


def test_background_lifecycle_starts_once_and_stops_cleanly():
    class FakeProducer:
        def __init__(self):
            self.stop_event = threading.Event()
            self.started = threading.Event()

        def run_forever(self):
            self.started.set()
            self.stop_event.wait()

    fake = FakeProducer()
    try:
        first_thread = producer_module._start_producer(fake)
        second_thread = producer_module._start_producer()

        assert fake.started.wait(timeout=1)
        assert first_thread is second_thread
        assert producer_module.producer_status() == {"running": True}
    finally:
        producer_module._stop_producer()

    assert producer_module.producer_status() == {"running": False}
