import json
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Optional


ACTIVE = "ACTIVE"
PAUSED = "PAUSED"
STOPPED = "STOPPED"


class TaskStore:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._lock = threading.RLock()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=30)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    task_id TEXT PRIMARY KEY,
                    source TEXT NOT NULL,
                    task_type TEXT NOT NULL,
                    task_data TEXT NOT NULL,
                    is_parent INTEGER NOT NULL DEFAULT 0,
                    parent_task_id TEXT,
                    child_index INTEGER,
                    passenger_count INTEGER,
                    passenger_range TEXT,
                    status TEXT NOT NULL,
                    in_flight INTEGER NOT NULL DEFAULT 0,
                    interval_seconds INTEGER NOT NULL,
                    max_runs INTEGER,
                    run_count INTEGER NOT NULL DEFAULT 0,
                    success_count INTEGER NOT NULL DEFAULT 0,
                    failure_count INTEGER NOT NULL DEFAULT 0,
                    last_status_code INTEGER,
                    last_message TEXT,
                    last_result TEXT,
                    next_run_at REAL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    finished_at REAL
                )
                """
            )
            self._ensure_task_columns(conn)
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS attempts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    attempt_no INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    status_code INTEGER,
                    message TEXT,
                    raw_result TEXT,
                    started_at REAL NOT NULL,
                    finished_at REAL,
                    duration_seconds REAL,
                    FOREIGN KEY(task_id) REFERENCES tasks(task_id)
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_due ON tasks(status, in_flight, next_run_at)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_attempts_task ON attempts(task_id, id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_attempts_status_time ON attempts(status_code, finished_at)")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS pnr_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    pnr TEXT NOT NULL,
                    source TEXT,
                    flight_number TEXT,
                    cabin TEXT,
                    currency_code TEXT,
                    dep_airport TEXT,
                    arr_airport TEXT,
                    dep_date TEXT,
                    passenger_count INTEGER,
                    passengers TEXT,
                    order_state TEXT,
                    created_at REAL NOT NULL,
                    expires_at REAL,
                    raw_result TEXT,
                    updated_at REAL NOT NULL,
                    UNIQUE(task_id, pnr)
                )
                """
            )
            self._ensure_pnr_record_columns(conn)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_pnr_records_created ON pnr_records(created_at DESC)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_pnr_records_pnr ON pnr_records(pnr)")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS source_proxy_configs (
                    source TEXT PRIMARY KEY,
                    enabled INTEGER NOT NULL DEFAULT 0,
                    host TEXT,
                    port INTEGER,
                    username TEXT,
                    password TEXT,
                    region TEXT,
                    session_time INTEGER,
                    format TEXT,
                    updated_at REAL NOT NULL
                )
                """
            )
        self.backfill_pnr_records_from_candidates()

    def _ensure_task_columns(self, conn: sqlite3.Connection) -> None:
        existing_columns = {row["name"] for row in conn.execute("PRAGMA table_info(tasks)").fetchall()}
        column_sql = {
            "is_parent": "ALTER TABLE tasks ADD COLUMN is_parent INTEGER NOT NULL DEFAULT 0",
            "parent_task_id": "ALTER TABLE tasks ADD COLUMN parent_task_id TEXT",
            "child_index": "ALTER TABLE tasks ADD COLUMN child_index INTEGER",
            "passenger_count": "ALTER TABLE tasks ADD COLUMN passenger_count INTEGER",
            "passenger_range": "ALTER TABLE tasks ADD COLUMN passenger_range TEXT",
        }
        for column, sql in column_sql.items():
            if column not in existing_columns:
                conn.execute(sql)

    def _ensure_pnr_record_columns(self, conn: sqlite3.Connection) -> None:
        existing_columns = {row["name"] for row in conn.execute("PRAGMA table_info(pnr_records)").fetchall()}
        column_sql = {
            "currency_code": "ALTER TABLE pnr_records ADD COLUMN currency_code TEXT",
        }
        for column, sql in column_sql.items():
            if column not in existing_columns:
                conn.execute(sql)

    def create_task(self, payload: dict[str, Any]) -> dict[str, Any]:
        now = time.time()
        task_id = payload.get("task_id") or payload.get("taskId") or uuid.uuid4().hex
        task_data = payload["task_data"]
        interval_seconds = int(payload.get("interval_seconds") or _book_rate(task_data) or 30)
        next_run_at = None if payload.get("is_parent") else (
            _parse_run_at(payload.get("first_run_at")) if payload.get("first_run_at") else now
        )
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO tasks (
                    task_id, source, task_type, task_data, is_parent, parent_task_id,
                    child_index, passenger_count, passenger_range, status, interval_seconds,
                    max_runs, next_run_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    payload["source"],
                    payload.get("task_type", "shamBooking"),
                    json.dumps(task_data, ensure_ascii=False),
                    1 if payload.get("is_parent") else 0,
                    payload.get("parent_task_id"),
                    payload.get("child_index"),
                    payload.get("passenger_count"),
                    payload.get("passenger_range"),
                    payload.get("status", ACTIVE),
                    interval_seconds,
                    payload.get("max_runs"),
                    next_run_at,
                    now,
                    now,
                ),
            )
        return self.get_task(task_id)

    def upsert_task(self, payload: dict[str, Any]) -> dict[str, Any]:
        existing = self.get_task(payload.get("task_id") or payload.get("taskId") or "")
        if not existing:
            return self.create_task(payload)
        task_id = existing["task_id"]
        now = time.time()
        task_data = payload["task_data"]
        interval_seconds = int(payload.get("interval_seconds") or _book_rate(task_data) or existing["interval_seconds"])
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                UPDATE tasks
                SET source = ?, task_type = ?, task_data = ?, interval_seconds = ?,
                    max_runs = ?, updated_at = ?
                WHERE task_id = ?
                """,
                (
                    payload["source"],
                    payload.get("task_type", "shamBooking"),
                    json.dumps(task_data, ensure_ascii=False),
                    interval_seconds,
                    payload.get("max_runs"),
                    now,
                    task_id,
                ),
            )
        return self.get_task(task_id)

    def list_tasks(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM tasks ORDER BY created_at DESC").fetchall()
        return self._order_task_rows([self._row_to_dict(row) for row in rows])

    def get_task(self, task_id: str) -> Optional[dict[str, Any]]:
        if not task_id:
            return None
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
        return self._row_to_dict(row) if row else None

    def list_attempts(self, task_id: str, limit: int = 80) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM attempts
                WHERE task_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (task_id, limit),
            ).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def list_pnr_candidate_events(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            attempt_rows = conn.execute(
                """
                SELECT
                    t.task_id,
                    t.source,
                    t.task_data,
                    t.updated_at,
                    a.id AS event_id,
                    a.raw_result AS result,
                    COALESCE(a.finished_at, a.started_at, t.updated_at) AS event_at
                FROM attempts a
                JOIN tasks t ON t.task_id = a.task_id
                WHERE t.is_parent = 0
                    AND a.status_code = 200
                    AND a.raw_result IS NOT NULL
                    AND LOWER(a.raw_result) LIKE '%pnr%'
                ORDER BY event_at DESC, a.id DESC
                """
            ).fetchall()
            task_rows = conn.execute(
                """
                SELECT
                    task_id,
                    source,
                    task_data,
                    updated_at,
                    0 AS event_id,
                    last_result AS result,
                    updated_at AS event_at
                FROM tasks
                WHERE is_parent = 0
                    AND last_result IS NOT NULL
                    AND LOWER(last_result) LIKE '%pnr%'
                ORDER BY updated_at DESC
                """
            ).fetchall()

        events = [self._pnr_candidate_row_to_dict(row, "attempt") for row in attempt_rows]
        events.extend(self._pnr_candidate_row_to_dict(row, "task") for row in task_rows)
        events.sort(key=lambda item: (item.get("event_at") or 0, item.get("event_id") or 0), reverse=True)
        return events

    def list_pnr_records(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM pnr_records
                ORDER BY created_at DESC, id DESC
                """
            ).fetchall()
        return [self._pnr_record_row_to_dict(row) for row in rows]

    def upsert_pnr_record(self, row: dict[str, Any]) -> None:
        pnr = _clean_optional(row.get("pnr"))
        task_id = _clean_optional(row.get("taskId") or row.get("task_id"))
        if not pnr or not task_id:
            return
        now = time.time()
        created_at = _safe_float(row.get("createdAt") or row.get("created_at")) or now
        expires_at = _safe_float(row.get("expiresAt") or row.get("expires_at"))
        passenger_count = _safe_int(row.get("passengerCount") or row.get("passenger_count"))
        raw_result = row.get("rawResult") if "rawResult" in row else row.get("raw_result")
        raw_result_text = raw_result if isinstance(raw_result, str) else json.dumps(raw_result, ensure_ascii=False, default=str)
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO pnr_records (
                    task_id, pnr, source, flight_number, cabin, currency_code,
                    dep_airport, arr_airport, dep_date, passenger_count, passengers, order_state, created_at,
                    expires_at, raw_result, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(task_id, pnr) DO UPDATE SET
                    source = excluded.source,
                    flight_number = excluded.flight_number,
                    cabin = excluded.cabin,
                    currency_code = excluded.currency_code,
                    dep_airport = excluded.dep_airport,
                    arr_airport = excluded.arr_airport,
                    dep_date = excluded.dep_date,
                    passenger_count = excluded.passenger_count,
                    passengers = excluded.passengers,
                    order_state = excluded.order_state,
                    expires_at = excluded.expires_at,
                    raw_result = excluded.raw_result,
                    updated_at = excluded.updated_at
                """,
                (
                    task_id,
                    pnr,
                    _clean_optional(row.get("source")),
                    _clean_optional(row.get("flightNumber") or row.get("flight_number")),
                    _clean_optional(row.get("cabin")),
                    _clean_optional(row.get("currencyCode") or row.get("currency_code")),
                    _clean_optional(row.get("depAirport") or row.get("dep_airport")),
                    _clean_optional(row.get("arrAirport") or row.get("arr_airport")),
                    _clean_optional(row.get("depDate") or row.get("dep_date")),
                    passenger_count,
                    _clean_optional(row.get("passengers")),
                    _clean_optional(row.get("orderState") or row.get("order_state")),
                    created_at,
                    expires_at,
                    raw_result_text,
                    now,
                ),
            )

    def backfill_pnr_records_from_candidates(self) -> int:
        count = 0
        for event in self.list_pnr_candidate_events():
            record = _pnr_record_from_task_result(
                task_id=event.get("task_id") or "",
                source=event.get("source") or "",
                task_data=event.get("task_data") or {},
                result=event.get("result"),
                created_at=float(event.get("event_at") or event.get("updated_at") or time.time()),
            )
            if not record:
                continue
            self.upsert_pnr_record(record)
            count += 1
        return count

    def acquire_due_tasks(self, limit: Optional[int]) -> list[dict[str, Any]]:
        now = time.time()
        with self._lock, self._connect() as conn:
            limit_clause = "" if limit is None or limit <= 0 else "LIMIT ?"
            params = [ACTIVE, now]
            if limit_clause:
                params.append(limit)
            rows = conn.execute(
                f"""
                SELECT * FROM tasks
                WHERE status = ? AND in_flight = 0 AND is_parent = 0
                    AND next_run_at IS NOT NULL AND next_run_at <= ?
                ORDER BY next_run_at ASC
                {limit_clause}
                """,
                params,
            ).fetchall()
            task_ids = [row["task_id"] for row in rows]
            if task_ids:
                conn.executemany(
                    "UPDATE tasks SET in_flight = 1, updated_at = ? WHERE task_id = ?",
                    [(now, task_id) for task_id in task_ids],
                )
        return [self._row_to_dict(row) for row in rows]

    def start_attempt(self, task_id: str) -> int:
        now = time.time()
        with self._lock, self._connect() as conn:
            task = conn.execute("SELECT run_count FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
            attempt_no = int(task["run_count"]) + 1 if task else 1
            conn.execute(
                """
                INSERT INTO attempts (task_id, attempt_no, status, started_at)
                VALUES (?, ?, 'RUNNING', ?)
                """,
                (task_id, attempt_no, now),
            )
            conn.execute(
                "UPDATE tasks SET run_count = ?, updated_at = ? WHERE task_id = ?",
                (attempt_no, now, task_id),
            )
        return attempt_no

    def finish_attempt(
        self,
        task_id: str,
        attempt_no: int,
        status_code: int,
        message: str,
        result: Any,
        duration_seconds: float,
    ) -> None:
        now = time.time()
        raw_result = json.dumps(result, ensure_ascii=False, default=str)
        success = status_code == 200
        pnr_record = None
        with self._lock, self._connect() as conn:
            row = conn.execute(
                """
                SELECT status, source, task_data, interval_seconds, max_runs, run_count,
                    success_count, failure_count, passenger_count
                FROM tasks
                WHERE task_id = ?
                """,
                (task_id,),
            ).fetchone()
            if not row:
                return
            task_status = row["status"]
            run_count = int(row["run_count"])
            max_runs = row["max_runs"]
            final_status = task_status
            finished_at = None
            next_run_at = None
            if task_status == ACTIVE:
                if max_runs is not None and run_count >= int(max_runs):
                    final_status = STOPPED
                    finished_at = now
                else:
                    next_run_at = now + int(row["interval_seconds"])
            conn.execute(
                """
                UPDATE attempts
                SET status = ?, status_code = ?, message = ?, raw_result = ?,
                    finished_at = ?, duration_seconds = ?
                WHERE task_id = ? AND attempt_no = ?
                """,
                (
                    "SUCCESS" if success else "FAILED",
                    status_code,
                    message,
                    raw_result,
                    now,
                    duration_seconds,
                    task_id,
                    attempt_no,
                ),
            )
            conn.execute(
                """
                UPDATE tasks
                SET status = ?, in_flight = 0, success_count = ?, failure_count = ?,
                    last_status_code = ?, last_message = ?, last_result = ?,
                    next_run_at = ?, updated_at = ?, finished_at = ?
                WHERE task_id = ?
                """,
                (
                    final_status,
                    int(row["success_count"]) + (1 if success else 0),
                    int(row["failure_count"]) + (0 if success else 1),
                    status_code,
                    message,
                    raw_result,
                    next_run_at,
                    now,
                    finished_at,
                    task_id,
                ),
            )
            if success:
                pnr_record = _pnr_record_from_task_result(
                    task_id=task_id,
                    source=row["source"],
                    task_data=self._decode_json(row["task_data"]) or {},
                    result=result,
                    created_at=now,
                    passenger_count=row["passenger_count"],
                )
        if pnr_record:
            self.upsert_pnr_record(pnr_record)

    def fail_attempt(self, task_id: str, attempt_no: int, message: str, duration_seconds: float) -> None:
        self.finish_attempt(task_id, attempt_no, 0, message, {"status": 0, "message": message}, duration_seconds)

    def pause_task(self, task_id: str) -> Optional[dict[str, Any]]:
        self._set_status_cascade(task_id, PAUSED, next_run_at=None)
        return self.get_task(task_id)

    def resume_task(self, task_id: str) -> Optional[dict[str, Any]]:
        self._set_status_cascade(task_id, ACTIVE, next_run_at=time.time(), finished_at=None)
        return self.get_task(task_id)

    def stop_task(self, task_id: str) -> Optional[dict[str, Any]]:
        self._set_status_cascade(task_id, STOPPED, next_run_at=None, finished_at=time.time())
        return self.get_task(task_id)

    def run_now(self, task_id: str) -> Optional[dict[str, Any]]:
        now = time.time()
        task = self.get_task(task_id)
        if not task:
            return None
        task_ids = self._cascade_task_ids(task_id)
        with self._lock, self._connect() as conn:
            for target_id in task_ids:
                next_run_at = None if target_id == task_id and task.get("is_parent") else now
                conn.execute(
                    "UPDATE tasks SET status = ?, next_run_at = ?, updated_at = ?, finished_at = NULL WHERE task_id = ?",
                    (ACTIVE, next_run_at, now, target_id),
                )
        return self.get_task(task_id)

    def delete_task(self, task_id: str) -> bool:
        if not self.get_task(task_id):
            return False
        task_ids = self._cascade_task_ids(task_id)
        with self._lock, self._connect() as conn:
            conn.executemany("DELETE FROM attempts WHERE task_id = ?", [(target_id,) for target_id in task_ids])
            conn.executemany("DELETE FROM tasks WHERE task_id = ?", [(target_id,) for target_id in task_ids])
        return True

    def reset_stale_in_flight(self, older_than_seconds: int = 1800) -> int:
        cutoff = time.time() - older_than_seconds
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                """
                UPDATE tasks
                SET in_flight = 0, next_run_at = ?, updated_at = ?
                WHERE in_flight = 1 AND updated_at < ? AND status = ?
                """,
                (time.time(), time.time(), cutoff, ACTIVE),
            )
        return cur.rowcount

    def list_source_proxy_configs(self, sources: list[str]) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM source_proxy_configs").fetchall()
        config_by_source = {row["source"].upper(): self._source_proxy_row_to_dict(row) for row in rows}
        return [config_by_source.get(source.upper(), _empty_source_proxy_config(source)) for source in sources]

    def get_source_proxy_config(self, source: str) -> Optional[dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM source_proxy_configs WHERE source = ?", (source.upper(),)).fetchone()
        return self._source_proxy_row_to_dict(row) if row else None

    def upsert_source_proxy_config(self, payload: dict[str, Any]) -> dict[str, Any]:
        source = payload["source"].upper()
        now = time.time()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO source_proxy_configs (
                    source, enabled, host, port, username, password, region,
                    session_time, format, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source) DO UPDATE SET
                    enabled = excluded.enabled,
                    host = excluded.host,
                    port = excluded.port,
                    username = excluded.username,
                    password = excluded.password,
                    region = excluded.region,
                    session_time = excluded.session_time,
                    format = excluded.format,
                    updated_at = excluded.updated_at
                """,
                (
                    source,
                    1 if payload.get("enabled") else 0,
                    _clean_optional(payload.get("host")),
                    payload.get("port"),
                    _clean_optional(payload.get("username")),
                    _clean_optional(payload.get("password")),
                    _clean_optional(payload.get("region")),
                    payload.get("session_time"),
                    _clean_optional(payload.get("format")),
                    now,
                ),
            )
        return self.get_source_proxy_config(source) or _empty_source_proxy_config(source)

    def delete_source_proxy_config(self, source: str) -> dict[str, Any]:
        source = source.upper()
        with self._lock, self._connect() as conn:
            conn.execute("DELETE FROM source_proxy_configs WHERE source = ?", (source,))
        return _empty_source_proxy_config(source)

    def _set_status(
        self,
        task_id: str,
        status: str,
        next_run_at: Optional[float],
        finished_at: Optional[float] = None,
    ) -> None:
        now = time.time()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                UPDATE tasks
                SET status = ?, in_flight = 0, next_run_at = ?, updated_at = ?, finished_at = ?
                WHERE task_id = ?
                """,
                (status, next_run_at, now, finished_at, task_id),
            )

    def _set_status_cascade(
        self,
        task_id: str,
        status: str,
        next_run_at: Optional[float],
        finished_at: Optional[float] = None,
    ) -> None:
        now = time.time()
        task_ids = self._cascade_task_ids(task_id)
        task = self.get_task(task_id)
        with self._lock, self._connect() as conn:
            for target_id in task_ids:
                target_next_run_at = None if target_id == task_id and task and task.get("is_parent") else next_run_at
                conn.execute(
                    """
                    UPDATE tasks
                    SET status = ?, in_flight = 0, next_run_at = ?, updated_at = ?, finished_at = ?
                    WHERE task_id = ?
                    """,
                    (status, target_next_run_at, now, finished_at, target_id),
                )

    def _cascade_task_ids(self, task_id: str) -> list[str]:
        task = self.get_task(task_id)
        if not task:
            return [task_id]
        if not task.get("is_parent"):
            return [task_id]
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT task_id FROM tasks WHERE parent_task_id = ? ORDER BY child_index ASC, created_at ASC",
                (task_id,),
            ).fetchall()
        return [task_id] + [row["task_id"] for row in rows]

    @classmethod
    def _row_to_dict(cls, row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        for key in ("task_data", "last_result", "raw_result"):
            if data.get(key):
                data[key] = cls._decode_json(data[key])
        if "in_flight" in data:
            data["in_flight"] = bool(data["in_flight"])
        if "is_parent" in data:
            data["is_parent"] = bool(data["is_parent"])
        return data

    @classmethod
    def _pnr_candidate_row_to_dict(cls, row: sqlite3.Row, origin: str) -> dict[str, Any]:
        data = dict(row)
        data["origin"] = origin
        data["task_data"] = cls._decode_json(data.get("task_data"))
        data["result"] = cls._decode_json(data.get("result"))
        return data

    @classmethod
    def _pnr_record_row_to_dict(cls, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "taskId": row["task_id"] or "",
            "pnr": row["pnr"] or "",
            "source": row["source"] or "",
            "flightNumber": row["flight_number"] or "-",
            "cabin": row["cabin"] or "-",
            "currencyCode": row["currency_code"] or "-",
            "depAirport": row["dep_airport"] or "-",
            "arrAirport": row["arr_airport"] or "-",
            "depDate": row["dep_date"] or "-",
            "passengerCount": row["passenger_count"] if row["passenger_count"] is not None else "-",
            "passengers": row["passengers"] or "-",
            "orderState": row["order_state"] or "-",
            "createdAt": row["created_at"] or 0,
            "expiresAt": row["expires_at"] or 0,
            "rawResult": cls._decode_json(row["raw_result"]),
        }

    @staticmethod
    def _decode_json(value: Any) -> Any:
        if not value:
            return value
        if not isinstance(value, str):
            return value
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value

    @staticmethod
    def _order_task_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        children_by_parent: dict[str, list[dict[str, Any]]] = {}
        root_rows: list[dict[str, Any]] = []
        child_ids = set()
        for row in rows:
            parent_id = row.get("parent_task_id")
            if parent_id:
                children_by_parent.setdefault(parent_id, []).append(row)
                child_ids.add(row["task_id"])
            else:
                root_rows.append(row)

        root_rows.sort(key=lambda item: item.get("created_at") or 0, reverse=True)
        ordered: list[dict[str, Any]] = []
        for row in root_rows:
            children = sorted(
                children_by_parent.get(row["task_id"], []),
                key=lambda item: (item.get("child_index") or 0, item.get("created_at") or 0),
            )
            if row.get("is_parent") and children:
                row["child_count"] = len(children)
                row["run_count"] = sum(int(child.get("run_count") or 0) for child in children)
                row["success_count"] = sum(int(child.get("success_count") or 0) for child in children)
                row["failure_count"] = sum(int(child.get("failure_count") or 0) for child in children)
                row["in_flight"] = any(child.get("in_flight") for child in children)
                child_statuses = {child.get("status") for child in children}
                if ACTIVE in child_statuses:
                    row["status"] = ACTIVE
                elif PAUSED in child_statuses:
                    row["status"] = PAUSED
                elif STOPPED in child_statuses:
                    row["status"] = STOPPED
            ordered.append(row)
            ordered.extend(children)
        parent_ids = {row["task_id"] for row in root_rows}
        for parent_id, children in children_by_parent.items():
            if parent_id not in parent_ids:
                ordered.extend(sorted(children, key=lambda item: item.get("created_at") or 0, reverse=True))
        return ordered

    @staticmethod
    def _source_proxy_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "source": row["source"],
            "enabled": bool(row["enabled"]),
            "host": row["host"] or "",
            "port": row["port"],
            "username": row["username"] or "",
            "password": row["password"] or "",
            "region": row["region"] or "",
            "session_time": row["session_time"],
            "format": row["format"] or "",
            "updated_at": row["updated_at"],
            "configured": True,
        }


def _book_rate(task_data: dict[str, Any]) -> Optional[int]:
    booking_config = task_data.get("bookingConfig") or {}
    value = booking_config.get("bookRate")
    return int(value) if value else None


def _clean_optional(value: Any) -> Optional[str]:
    text = str(value).strip() if value is not None else ""
    return text or None


def _pnr_record_from_task_result(
    task_id: str,
    source: str,
    task_data: dict[str, Any],
    result: Any,
    created_at: float,
    passenger_count: Any = None,
) -> Optional[dict[str, Any]]:
    result_data = _as_dict(result)
    if _safe_int(result_data.get("status")) != 200:
        return None
    pnr = _extract_pnr(result_data)
    if not pnr:
        return None
    valid_minutes = _pnr_valid_minutes(task_data)
    result_passenger_count = _extract_passenger_count(result_data)
    ext = _as_dict(task_data.get("ext"))
    fallback_passenger_count = (
        result_passenger_count
        or _safe_int(ext.get("passengerCount"))
        or _safe_int(passenger_count)
    )
    return {
        "taskId": task_id,
        "pnr": pnr,
        "source": source,
        "flightNumber": task_data.get("flightNumber") or "-",
        "cabin": _extract_cabin(result_data),
        "currencyCode": _extract_currency_code(result_data, task_data),
        "depAirport": task_data.get("depAirport") or "-",
        "arrAirport": task_data.get("arrAirport") or "-",
        "depDate": task_data.get("depDate") or "-",
        "passengerCount": fallback_passenger_count,
        "passengers": _extract_passenger_names(result_data),
        "orderState": _as_dict(result_data.get("data")).get("orderState") or result_data.get("message") or "-",
        "createdAt": created_at,
        "expiresAt": created_at + valid_minutes * 60 if created_at and valid_minutes else 0,
        "rawResult": result_data,
    }


def _extract_pnr(result: dict[str, Any]) -> str:
    data = _as_dict(result.get("data"))
    return str(data.get("pnr") or result.get("pnr") or "").strip()


def _extract_cabin(result: dict[str, Any]) -> str:
    data = _as_dict(result.get("data"))
    candidates: list[Any] = []
    candidates.extend(_extract_cabins_from_journeys(data.get("journeys")))
    candidates.extend(_extract_cabins_from_bundles(data.get("bundles")))
    candidates.extend(_extract_cabins_from_segments(data.get("segments")))
    candidates.extend(
        [
            data.get("cabin"),
            _as_dict(data.get("reservation")).get("cabin"),
            _as_dict(data.get("order")).get("cabin"),
            _as_dict(data.get("booking")).get("cabin"),
            result.get("cabin"),
        ]
    )
    return next((cabin for cabin in (_normalize_cabin(item) for item in candidates) if cabin), "-")


def _extract_currency_code(result: dict[str, Any], task_data: dict[str, Any]) -> str:
    data = _as_dict(result.get("data"))
    booking_config = _as_dict(task_data.get("bookingConfig"))
    candidates = [
        data.get("currencyCode"),
        data.get("currency"),
        _as_dict(data.get("reservation")).get("currencyCode"),
        _as_dict(data.get("reservation")).get("currency"),
        _as_dict(data.get("order")).get("currencyCode"),
        _as_dict(data.get("order")).get("currency"),
        _as_dict(data.get("booking")).get("currencyCode"),
        _as_dict(data.get("booking")).get("currency"),
        result.get("currencyCode"),
        result.get("currency"),
        booking_config.get("currencyCode"),
        booking_config.get("currency"),
    ]
    return next((currency for currency in (_normalize_currency_code(item) for item in candidates) if currency), "-")


def _normalize_currency_code(value: Any) -> str:
    currency = str(value or "").strip().upper()
    return currency if currency and currency != "-" else ""


def _extract_cabins_from_journeys(journeys: Any) -> list[Any]:
    cabins: list[Any] = []
    for journey in _as_list(journeys):
        journey_data = _as_dict(journey)
        cabins.append(journey_data.get("cabin"))
        cabins.extend(_extract_cabins_from_bundles(journey_data.get("bundles")))
        cabins.extend(_extract_cabins_from_segments(journey_data.get("segments")))
    return cabins


def _extract_cabins_from_bundles(bundles: Any) -> list[Any]:
    return [_as_dict(bundle).get("cabin") for bundle in _as_list(bundles)]


def _extract_cabins_from_segments(segments: Any) -> list[Any]:
    return [_as_dict(segment).get("cabin") for segment in _as_list(segments)]


def _normalize_cabin(value: Any) -> str:
    cabin = str(value or "").strip()
    return cabin if cabin and cabin != "-" else ""


def _extract_passengers(result: dict[str, Any]) -> list[Any]:
    data = _as_dict(result.get("data"))
    passengers = data.get("passengers") or result.get("passengers")
    return passengers if isinstance(passengers, list) else []


def _extract_passenger_count(result: dict[str, Any]) -> Optional[int]:
    passengers = _extract_passengers(result)
    return len(passengers) if passengers else None


def _extract_passenger_names(result: dict[str, Any]) -> str:
    names: list[str] = []
    for passenger in _extract_passengers(result):
        passenger_data = _as_dict(passenger)
        joined = "/".join(
            item
            for item in [
                str(passenger_data.get("lastName") or passenger_data.get("last_name") or "").strip(),
                str(passenger_data.get("firstName") or passenger_data.get("first_name") or "").strip(),
            ]
            if item
        )
        name = joined or passenger_data.get("name") or passenger_data.get("passengerName") or ""
        if name:
            names.append(str(name))
    return ", ".join(names) if names else "-"


def _pnr_valid_minutes(task_data: dict[str, Any]) -> Optional[float]:
    ext = _as_dict(task_data.get("ext"))
    value = _safe_float(ext.get("pnrValidMinutes") or ext.get("pnrValidityMinutes") or ext.get("pnrValidMinute"))
    return value if value and value > 0 else None


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _safe_int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _empty_source_proxy_config(source: str) -> dict[str, Any]:
    return {
        "source": source.upper(),
        "enabled": False,
        "host": "",
        "port": None,
        "username": "",
        "password": "",
        "region": "",
        "session_time": None,
        "format": "",
        "updated_at": None,
        "configured": False,
    }


def _parse_run_at(value: Any) -> float:
    if isinstance(value, (int, float)):
        raw = float(value)
        return raw / 1000 if raw > 10_000_000_000 else raw
    text = str(value).strip()
    if text.lower() in {"", "now"}:
        return time.time()
    if text.isdigit():
        raw = float(text)
        return raw / 1000 if raw > 10_000_000_000 else raw
    parsed = time.strptime(text, "%Y-%m-%d %H:%M:%S")
    return time.mktime(parsed)
