import json
import os
import time
import uuid
from copy import deepcopy
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional
from urllib.parse import unquote, urlparse

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .runner import LocalRunner
from .source_registry import normalize_source, supported_sources
from .store import ACTIVE, TaskStore


APP_DIR = Path(__file__).resolve().parents[1]
STATIC_DIR = APP_DIR / "static"
DB_PATH = Path(os.getenv("LOCAL_SHAM_DB", APP_DIR / "local_sham_booking.db"))


class TaskPayload(BaseModel):
    task_id: Optional[str] = Field(default=None, alias="taskId")
    source: str
    task_type: str = Field(default="shamBooking", alias="taskType")
    task_data: dict[str, Any] = Field(..., alias="taskData")
    interval_seconds: Optional[int] = Field(default=None, ge=1, alias="intervalSeconds")
    max_runs: Optional[int] = Field(default=None, ge=1, alias="maxRuns")
    first_run_at: Optional[Any] = Field(default=None, alias="firstRunAt")
    passenger_range: Optional[str] = Field(default=None, alias="passengerRange")


class ImportPayload(BaseModel):
    tasks: Any
    replace_existing: bool = Field(default=True, alias="replaceExisting")


class SourceProxyPayload(BaseModel):
    enabled: bool = False
    host: Optional[str] = None
    port: Optional[int] = Field(default=None, ge=1, le=65535)
    username: Optional[str] = None
    password: Optional[str] = None
    region: Optional[str] = None
    session_time: Optional[int] = Field(default=None, ge=1, alias="sessionTime")
    format: Optional[str] = None


store = TaskStore(DB_PATH)
runner = LocalRunner(
    store,
    concurrency=int(os.getenv("LOCAL_SHAM_CONCURRENCY", "0")),
    poll_interval=float(os.getenv("LOCAL_SHAM_POLL_INTERVAL", "0.5")),
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    runner.start()
    yield
    runner.stop()


app = FastAPI(title="Local Sham Booking", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "time": int(time.time()),
        "dbPath": str(DB_PATH),
        "runner": runner.stats(),
    }


@app.get("/api/sources")
def sources():
    return {"sources": supported_sources()}


@app.get("/api/source-proxies")
def list_source_proxies():
    return [_proxy_response(item) for item in store.list_source_proxy_configs(supported_sources())]


@app.put("/api/source-proxies/{source}")
def save_source_proxy(source: str, request: SourceProxyPayload):
    payload = _normalize_source_proxy_payload(source, request)
    return _proxy_response(store.upsert_source_proxy_config(payload))


@app.delete("/api/source-proxies/{source}")
def delete_source_proxy(source: str):
    normalized = normalize_source(source)
    return _proxy_response(store.delete_source_proxy_config(normalized))


@app.get("/api/tasks")
def list_tasks():
    return store.list_tasks()


@app.post("/api/tasks")
def create_task(request: TaskPayload):
    payload = _normalize_payload(request)
    if store.get_task(payload["task_id"]):
        raise HTTPException(status_code=409, detail="taskId 已存在")
    passenger_counts = _parse_passenger_range(request.passenger_range)
    if passenger_counts:
        return _create_task_tree(payload, request.passenger_range or "", passenger_counts)
    return store.create_task(payload)


@app.put("/api/tasks/{task_id}")
def update_task(task_id: str, request: TaskPayload):
    payload = _normalize_payload(request, fallback_task_id=task_id)
    return store.upsert_task(payload)


@app.post("/api/tasks/import")
def import_tasks(request: ImportPayload):
    task_items = _coerce_import_items(request.tasks)
    imported = []
    for item in task_items:
        payload = _normalize_payload(TaskPayload.model_validate(item))
        if request.replace_existing:
            imported.append(store.upsert_task(payload))
        else:
            imported.append(store.create_task(payload))
    return {"count": len(imported), "tasks": imported}


@app.get("/api/tasks/{task_id}")
def get_task(task_id: str):
    task = store.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    task["attempts"] = store.list_attempts(task_id)
    return task


@app.get("/api/tasks/{task_id}/attempts")
def list_attempts(task_id: str):
    if not store.get_task(task_id):
        raise HTTPException(status_code=404, detail="任务不存在")
    return store.list_attempts(task_id)


@app.post("/api/tasks/{task_id}/pause")
def pause_task(task_id: str):
    task = store.pause_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return task


@app.post("/api/tasks/{task_id}/resume")
def resume_task(task_id: str):
    task = store.resume_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return task


@app.post("/api/tasks/{task_id}/stop")
def stop_task(task_id: str):
    task = store.stop_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return task


@app.post("/api/tasks/{task_id}/run-now")
def run_now(task_id: str):
    task = store.run_now(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return task


@app.delete("/api/tasks/{task_id}")
def delete_task(task_id: str):
    if not store.delete_task(task_id):
        raise HTTPException(status_code=404, detail="任务不存在")
    return {"status": "ok", "taskId": task_id}


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


def _normalize_payload(request: TaskPayload, fallback_task_id: Optional[str] = None) -> dict[str, Any]:
    source = normalize_source(request.source)
    task_id = request.task_id or fallback_task_id or _generated_task_id(request.task_data, source)
    return {
        "task_id": task_id,
        "source": source,
        "task_type": request.task_type,
        "task_data": request.task_data,
        "interval_seconds": request.interval_seconds,
        "max_runs": request.max_runs,
        "first_run_at": request.first_run_at,
        "status": ACTIVE,
    }


def _create_task_tree(payload: dict[str, Any], passenger_range: str, passenger_counts: list[int]) -> dict[str, Any]:
    parent_payload = dict(payload)
    parent_task_id = parent_payload["task_id"]
    parent_payload["is_parent"] = True
    parent_payload["passenger_range"] = passenger_range or _format_passenger_range(passenger_counts)
    parent_payload["first_run_at"] = None
    parent_payload["status"] = ACTIVE
    parent = store.create_task(parent_payload)
    children = []

    try:
        for index, passenger_count in enumerate(passenger_counts, start=1):
            child_payload = dict(payload)
            child_payload["task_id"] = _child_task_id(parent_task_id, passenger_count, index)
            child_payload["parent_task_id"] = parent_task_id
            child_payload["child_index"] = index
            child_payload["passenger_count"] = passenger_count
            child_payload["passenger_range"] = parent_payload["passenger_range"]
            child_payload["task_data"] = _task_data_for_passenger_count(payload["task_data"], passenger_count)
            children.append(store.create_task(child_payload))
    except Exception:
        store.delete_task(parent_task_id)
        raise
    parent["children"] = children
    return parent


def _task_data_for_passenger_count(task_data: dict[str, Any], passenger_count: int) -> dict[str, Any]:
    child_task_data = deepcopy(task_data)
    ext = dict(child_task_data.get("ext") or {})
    ext["passengerCount"] = passenger_count
    child_task_data["ext"] = ext
    return child_task_data


def _child_task_id(parent_task_id: str, passenger_count: int, index: int) -> str:
    base_id = f"{parent_task_id}-P{passenger_count}"
    if not store.get_task(base_id):
        return base_id
    while True:
        candidate = f"{base_id}-{index}-{uuid.uuid4().hex[:4]}"
        if not store.get_task(candidate):
            return candidate


def _parse_passenger_range(value: Optional[str]) -> list[int]:
    if value is None:
        return []
    text = value.strip()
    if not text:
        return []
    normalized = text.replace("~", "-").replace("至", "-").replace("，", ",")
    try:
        if "," in normalized:
            counts = [int(item.strip()) for item in normalized.split(",") if item.strip()]
        elif "-" in normalized:
            start_text, end_text = normalized.split("-", 1)
            start = int(start_text.strip())
            end = int(end_text.strip())
            if end < start:
                raise ValueError
            counts = list(range(start, end + 1))
        else:
            counts = [int(normalized)]
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="人数格式应为 1-1、1-4 或 1,2,3") from exc
    if not counts or any(count <= 0 for count in counts):
        raise HTTPException(status_code=400, detail="人数必须是大于 0 的整数")
    if len(set(counts)) != len(counts):
        raise HTTPException(status_code=400, detail="人数不能重复")
    if len(counts) > 100:
        raise HTTPException(status_code=400, detail="一次最多拆分 100 个子任务")
    return counts


def _format_passenger_range(counts: list[int]) -> str:
    if not counts:
        return ""
    if len(counts) == 1:
        return f"{counts[0]}-{counts[0]}"
    return f"{counts[0]}-{counts[-1]}"


def _coerce_import_items(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, str):
        value = json.loads(value)
    if isinstance(value, dict) and isinstance(value.get("tasks"), list):
        value = value["tasks"]
    if isinstance(value, dict):
        return [dict(task, taskId=task_id) for task_id, task in value.items()]
    if isinstance(value, list):
        return value
    raise HTTPException(status_code=400, detail="导入内容必须是数组、tasks 数组或 taskId 映射")


def _generated_task_id(task_data: dict[str, Any], source: str) -> str:
    dep = _clean_part(task_data.get("depAirport"), "DEP")
    arr = _clean_part(task_data.get("arrAirport"), "ARR")
    flight = _clean_part(task_data.get("flightNumber"), "FLIGHT")
    dep_date = "".join(ch for ch in str(task_data.get("depDate") or "") if ch.isdigit())[:8]
    suffix = str(uuid.uuid4().int % 100000).zfill(5)
    return f"{source}-{dep}-{arr}-{flight}-{dep_date or 'DATE'}-{suffix}"


def _clean_part(value: Any, fallback: str) -> str:
    cleaned = "".join(ch for ch in str(value or "").upper() if ch.isascii() and ch.isalnum())
    return cleaned or fallback


def _normalize_source_proxy_payload(source: str, request: SourceProxyPayload) -> dict[str, Any]:
    normalized_source = normalize_source(source)
    data = request.model_dump(by_alias=False)
    host, port, username, password, format_value = _normalize_proxy_host(
        data.get("host"),
        data.get("port"),
        data.get("username"),
        data.get("password"),
        data.get("format"),
    )
    enabled = bool(data.get("enabled"))
    if enabled and (not host or port is None):
        raise HTTPException(status_code=400, detail="启用代理时必须填写代理 IP/Host 和端口")
    return {
        "source": normalized_source,
        "enabled": enabled,
        "host": host,
        "port": port,
        "username": username,
        "password": password,
        "region": _clean_optional(data.get("region")),
        "session_time": data.get("session_time"),
        "format": format_value,
    }


def _normalize_proxy_host(
    host: Optional[str],
    port: Optional[int],
    username: Optional[str],
    password: Optional[str],
    format_value: Optional[str],
) -> tuple[str, Optional[int], str, str, str]:
    host_text = _clean_optional(host)
    username_text = _clean_optional(username)
    password_text = _clean_optional(password)
    format_text = _clean_optional(format_value)
    if not host_text:
        return "", port, username_text, password_text, format_text

    if "://" in host_text:
        parsed = urlparse(host_text)
        if parsed.hostname:
            host_text = parsed.hostname
        if parsed.port and port is None:
            port = parsed.port
        if parsed.username and not username_text:
            username_text = unquote(parsed.username)
        if parsed.password and not password_text:
            password_text = unquote(parsed.password)
        if not format_text:
            format_text = host or ""
    elif ":" in host_text and port is None:
        maybe_host, maybe_port = host_text.rsplit(":", 1)
        if maybe_port.isdigit():
            host_text = maybe_host
            port = int(maybe_port)
    return host_text, port, username_text, password_text, format_text


def _proxy_response(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "source": item["source"],
        "enabled": bool(item.get("enabled")),
        "host": item.get("host") or "",
        "port": item.get("port"),
        "username": item.get("username") or "",
        "password": item.get("password") or "",
        "region": item.get("region") or "",
        "sessionTime": item.get("session_time"),
        "format": item.get("format") or "",
        "updatedAt": item.get("updated_at"),
        "configured": bool(item.get("configured")),
    }


def _clean_optional(value: Optional[Any]) -> str:
    return str(value).strip() if value is not None else ""
