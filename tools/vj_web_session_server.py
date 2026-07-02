#!/usr/bin/env python3
import io
import json
import os
import random
import sqlite3
import sys
import threading
import time
from contextlib import asynccontextmanager, redirect_stdout
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# ==========================================
# 1. 环境变量与路径配置
# ==========================================
APP_DIR = Path(__file__).resolve().parents[1]
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from common.global_variable import GlobalVariable
from common.model.proxy_Info_model import ProxyInfoModel
from flights.vietjet.script.web_script import REDIS, WebScript

HOST = "0.0.0.0"
PORT = int(os.getenv("VJ_WEB_SESSION_SERVER_PORT", "8028"))
SOURCE = "VJWEB"
DB_PATH = Path(os.getenv("LOCAL_SHAM_DB", str(APP_DIR / "local_sham_booking.db")))
ROUTES: list[str] = []
TARGET_SIZE = int(os.getenv("VJ_WEB_SESSION_TARGET_SIZE", "100"))
INTERVAL_SECONDS = float(os.getenv("VJ_WEB_SESSION_INTERVAL_SECONDS", "2"))
READY_SECONDS = int(os.getenv("VJ_WEB_SESSION_READY_SECONDS", "120"))
CACHE_TTL_SECONDS = int(os.getenv("VJ_WEB_SESSION_CACHE_TTL_SECONDS", "300"))
CACHE_MAX_SIZE = int(os.getenv("VJ_WEB_SESSION_CACHE_MAX_SIZE", "800"))
USE_DB_ROUTES_WHEN_EMPTY = True
WARM_ON_START = True

CACHE_VERSION = "v4"  # 缓存版本升级为 v4，防止与旧 List 结构冲突

# ==========================================
# 2. 全局状态与线程控制
# ==========================================
_STOP_EVENT = threading.Event()
_STATE_LOCK = threading.RLock()
_WARMER_THREAD: Optional[threading.Thread] = None
_STATE: dict[str, Any] = {
    "running": False,
    "lastRoutes": [],
    "lastStats": {},
    "lastError": None,
    "lastWarmAt": None,
}


# ==========================================
# 3. AWS Token 缓存复用管理器
# ==========================================
class AWSTokenManager:
    """
    负责管理 AWS WAF Token 的获取和复用，减少对官网安全接口的频繁请求
    """

    def __init__(self, ttl_seconds: int = 240):
        self._lock = threading.Lock()
        self._token: Optional[str] = None
        self._ua: Optional[str] = None
        self._expire_at: float = 0
        self._ttl = ttl_seconds

    def get_token(self, script: WebScript) -> tuple[str, str]:
        with self._lock:
            now = time.time()
            if self._token and now < self._expire_at:
                return self._token, self._ua

            _log("AWS WAF Token 缺失或已过期，正在重新获取...")
            with redirect_stdout(io.StringIO()):
                token_data = script.aws()

            self._token = token_data["data"]["token"]
            self._ua = token_data["data"].get("ua") or getattr(script, "_WebScript__ua")
            self._expire_at = now + self._ttl

            _log(f"成功获取新 WAF Token (有效期 {self._ttl}s)")
            return self._token, self._ua


# 实例化全局单例
GLOBAL_WAF_TOKEN_MANAGER = AWSTokenManager(ttl_seconds=240)


# ==========================================
# 4. 核心缓存类 (Redis ZSET 实现)
# ==========================================
class VJSessionCache:
    # Lua 脚本：原子性拉取已就绪的 Session
    LUA_POP_READY_SCRIPT = """
    local key = KEYS[1]
    local now = tonumber(ARGV[1])
    local items = redis.call('ZRANGE', key, '-inf', now, 'BYSCORE')

    for _, item in ipairs(items) do
        local success, parsed = pcall(cjson.decode, item)
        if success and parsed then
            if parsed.expiresAt > now then
                redis.call('ZREM', key, item)
                return item
            else
                redis.call('ZREM', key, item)
            end
        else
            redis.call('ZREM', key, item)
        end
    end
    return nil
    """

    def __init__(self) -> None:
        self.redis_client = REDIS

    def cache_key(self, dep_airport: str, arr_airport: str) -> str:
        return f"vj:web:session:{CACHE_VERSION}:{_clean_airport(dep_airport)}-{_clean_airport(arr_airport)}"

    def save(
            self,
            *,
            dep_airport: str,
            arr_airport: str,
            session_id: str,
            request_id: str,
            device_uuid: str,
            zero_trust_config: tuple[str, str],
            session_exp_in: Any,
    ) -> dict[str, Any]:
        now = time.time()
        expires_at = _safe_float(session_exp_in)
        if expires_at <= now:
            expires_at = now + READY_SECONDS + CACHE_TTL_SECONDS

        ready_at = now + READY_SECONDS
        if expires_at <= ready_at:
            raise RuntimeError(f"sessionExpIn 太近，无法满足 {READY_SECONDS}s 生效时间")

        payload = {
            "sessionId": session_id,
            "requestId": request_id,
            "sessionExpIn": int(expires_at),
            "departurePlace": _clean_airport(dep_airport),
            "arrival": _clean_airport(arr_airport),
            "deviceUuid": device_uuid,
            "zeroTrustConfig": list(zero_trust_config),
            "createdAt": int(now),
            "readyAt": int(ready_at),
            "expiresAt": int(expires_at),
        }

        redis_conn = self.redis_client.get_redis_connection()
        key = self.cache_key(dep_airport, arr_airport)

        payload_str = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        redis_conn.zadd(key, {payload_str: ready_at})
        redis_conn.expire(key, max(1, int(expires_at - now)))

        return payload

    def pop_ready(self, dep_airport: str, arr_airport: str) -> Optional[dict[str, Any]]:
        redis_conn = self.redis_client.get_redis_connection()
        key = self.cache_key(dep_airport, arr_airport)
        now = time.time()

        raw = redis_conn.eval(self.LUA_POP_READY_SCRIPT, 1, key, now)
        if not raw:
            return None

        raw_text = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
        try:
            return json.loads(raw_text)
        except json.JSONDecodeError:
            return None

    def stats(self, dep_airport: str, arr_airport: str) -> dict[str, Any]:
        result = {
            "ready": 0,
            "warming": 0,
            "expired": 0,
            "total": 0,
            "nextReadyInSeconds": None,
        }
        redis_conn = self.redis_client.get_redis_connection()
        key = self.cache_key(dep_airport, arr_airport)
        now = time.time()

        next_ready_at = None
        items = redis_conn.zrange(key, 0, -1)

        for raw in items:
            raw_text = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
            try:
                item = json.loads(raw_text)
            except json.JSONDecodeError:
                continue

            result["total"] += 1
            expires_at = _safe_float(item.get("expiresAt"))
            ready_at = _safe_float(item.get("readyAt"))

            if expires_at <= now:
                result["expired"] += 1
            elif ready_at <= now:
                result["ready"] += 1
            else:
                result["warming"] += 1
                next_ready_at = ready_at if next_ready_at is None else min(next_ready_at, ready_at)

        if next_ready_at is not None:
            result["nextReadyInSeconds"] = max(0, int(next_ready_at - now))
        return result

    def active_count(self, dep_airport: str, arr_airport: str) -> int:
        stats_data = self.stats(dep_airport, arr_airport)
        return int(stats_data["ready"] + stats_data["warming"])

    def list_all(self, include_session_id: bool = False) -> dict[str, Any]:
        redis_conn = self.redis_client.get_redis_connection()
        keys = sorted(redis_conn.scan_iter(f"vj:web:session:{CACHE_VERSION}:*"))
        now = time.time()
        routes = []
        totals = {"ready": 0, "warming": 0, "expired": 0, "total": 0}

        for raw_key in keys:
            cache_key = raw_key.decode("utf-8") if isinstance(raw_key, bytes) else str(raw_key)
            route = cache_key.rsplit(":", 1)[-1]
            sessions = []
            stats_data = {"ready": 0, "warming": 0, "expired": 0, "total": 0}

            for index, raw in enumerate(redis_conn.zrange(cache_key, 0, -1), 1):
                raw_text = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
                try:
                    item = json.loads(raw_text)
                except json.JSONDecodeError:
                    sessions.append({"index": index, "state": "bad-json"})
                    continue

                state, ready_in_seconds, expire_in_seconds = _session_state(item, now)
                stats_data[state] += 1
                stats_data["total"] += 1

                session_id = item.get("sessionId") or ""
                view = {
                    "index": index,
                    "state": state,
                    "readyInSeconds": ready_in_seconds,
                    "expireInSeconds": expire_in_seconds,
                    "requestId": item.get("requestId"),
                    "sessionExpIn": item.get("sessionExpIn"),
                    "departurePlace": item.get("departurePlace"),
                    "arrival": item.get("arrival"),
                    "deviceUuid": item.get("deviceUuid"),
                    "zeroTrustConfig": item.get("zeroTrustConfig"),
                    "createdAt": item.get("createdAt"),
                    "readyAt": item.get("readyAt"),
                    "expiresAt": item.get("expiresAt"),
                }
                if include_session_id:
                    view["sessionId"] = session_id
                else:
                    view["sessionIdLen"] = len(session_id)
                    view["sessionIdPreview"] = _preview(session_id)
                sessions.append(view)

            for name in totals:
                totals[name] += stats_data[name]

            routes.append(
                {
                    "route": route,
                    "cacheKey": cache_key,
                    "stats": stats_data,
                    "sessions": sessions,
                }
            )

        return {"stats": totals, "routes": routes}


# ==========================================
# 5. FastAPI 应用与路由
# ==========================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    if WARM_ON_START:
        _start_warmer()
    yield
    _stop_warmer()


app = FastAPI(title="VietJet Web Session Server", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "time": int(time.time()),
        "source": SOURCE,
        "dbPath": str(DB_PATH),
        "routes": ROUTES,
        "targetSize": TARGET_SIZE,
        "intervalSeconds": INTERVAL_SECONDS,
        "readySeconds": READY_SECONDS,
        "cacheMaxSize": CACHE_MAX_SIZE,
        "warmOnStart": WARM_ON_START,
        "state": _snapshot_state(),
    }


@app.get("/stats")
def route_stats(
        dep_airport: str = Query(..., alias="depAirport"),
        arr_airport: str = Query(..., alias="arrAirport"),
):
    dep_airport, arr_airport = _normalize_route_query(dep_airport, arr_airport)
    cache = VJSessionCache()
    return {
        "status": 200,
        "message": "ok",
        "cacheKey": cache.cache_key(dep_airport, arr_airport),
        "stats": cache.stats(dep_airport, arr_airport),
    }


@app.get("/sessions")
def list_sessions(
        include_session_id: bool = Query(default=False, alias="includeSessionId"),
):
    return {
        "status": 200,
        "message": "ok",
        "cacheVersion": CACHE_VERSION,
        "data": VJSessionCache().list_all(include_session_id=include_session_id),
    }


@app.get("/vj-session")
@app.get("/api/vj-web-session")
def get_vj_session(
        dep_airport: str = Query(..., alias="depAirport"),
        arr_airport: str = Query(..., alias="arrAirport"),
):
    dep_airport, arr_airport = _normalize_route_query(dep_airport, arr_airport)
    cache = VJSessionCache()
    session = cache.pop_ready(dep_airport, arr_airport)
    stats = cache.stats(dep_airport, arr_airport)
    cache_key = cache.cache_key(dep_airport, arr_airport)

    if not session:
        raise HTTPException(
            status_code=404,
            detail={
                "message": f"未取到可用缓存VJ session[{dep_airport}-{arr_airport}]",
                "cacheKey": cache_key,
                "stats": stats,
            },
        )

    return {
        "status": 200,
        "message": "ok",
        "cacheKey": cache_key,
        "requestId": session.get("requestId"),
        "sessionExpIn": session.get("sessionExpIn"),
        "stats": stats,
        "data": session,
    }


# ==========================================
# 6. 后台预热线程逻辑
# ==========================================
def _start_warmer() -> None:
    global _WARMER_THREAD
    if _WARMER_THREAD and _WARMER_THREAD.is_alive():
        return
    _STOP_EVENT.clear()
    _WARMER_THREAD = threading.Thread(target=_warmer_loop, name="vj-web-session-warmer", daemon=True)
    _WARMER_THREAD.start()


def _stop_warmer() -> None:
    _STOP_EVENT.set()
    if _WARMER_THREAD and _WARMER_THREAD.is_alive():
        _WARMER_THREAD.join(timeout=5)


def _warmer_loop() -> None:
    _set_state(running=True, lastError=None)
    _log(f"VJ session server started on {HOST}:{PORT}")
    while not _STOP_EVENT.is_set():
        try:
            _warm_pass()
            _set_state(lastError=None, lastWarmAt=int(time.time()))
        except Exception as exc:
            _set_state(lastError=str(exc))
            _log(f"warm pass failed: {exc}")
        _STOP_EVENT.wait(max(0.1, INTERVAL_SECONDS))
    _set_state(running=False)


def _warm_pass() -> None:
    routes = _routes_from_config(ROUTES)
    if not routes and USE_DB_ROUTES_WHEN_EMPTY:
        routes = _routes_from_db(DB_PATH, SOURCE)

    _set_state(lastRoutes=[f"{dep}-{arr}" for dep, arr in routes])
    if not routes:
        return

    proxy_info = _proxy_from_db(DB_PATH, SOURCE)
    cache = VJSessionCache()
    for dep_airport, arr_airport in routes:
        _warm_route(cache, proxy_info, dep_airport, arr_airport)


def _warm_route(
        cache: VJSessionCache,
        proxy_info: ProxyInfoModel,
        dep_airport: str,
        arr_airport: str,
) -> None:
    current_size = cache.active_count(dep_airport, arr_airport)
    if current_size >= TARGET_SIZE:
        stats = cache.stats(dep_airport, arr_airport)
        _remember_stats(dep_airport, arr_airport, stats)
        # _log(f"{dep_airport}-{arr_airport} {_format_pool_stats(stats)}") # 可选：觉得日志太吵可注释这行
        return

    for _ in range(TARGET_SIZE - current_size):
        try:
            cached = _warm_one_session(
                proxy_info=_clone_proxy(proxy_info),
                dep_airport=dep_airport,
                arr_airport=arr_airport,
            )
            stats = cache.stats(dep_airport, arr_airport)
            _remember_stats(dep_airport, arr_airport, stats)
            _log(
                f"{dep_airport}-{arr_airport} warmed requestId={cached['requestId']} "
                f"exp={cached['sessionExpIn']} {_format_pool_stats(stats)}"
            )
        except Exception as exc:
            stats = cache.stats(dep_airport, arr_airport)
            _remember_stats(dep_airport, arr_airport, stats)
            _log(f"{dep_airport}-{arr_airport} warm failed: {exc}")
            break


def _warm_one_session(
        *,
        proxy_info: ProxyInfoModel,
        dep_airport: str,
        arr_airport: str,
) -> dict[str, Any]:
    request_id = _request_id_get()
    script = WebScript(proxy_info=proxy_info)

    # ---------------------------------------------
    # 核心复用：从全局管理器获取 WAF Token，极大提升速度
    # ---------------------------------------------
    token, ua = GLOBAL_WAF_TOKEN_MANAGER.get_token(script)

    # 强行注入私有变量。如果不修改 WebScript 源码，此举不可省略。
    setattr(script, "_WebScript__aws_token", token)
    setattr(script, "_WebScript__ua", ua)
    # ---------------------------------------------

    headers = {
        "accept-encoding": "gzip, deflate, br, zstd",
        "user-agent": ua,
        "accept": "application/json",
        "accept-language": "zh-cn",
        "content-type": "application/json",
        "referer": "https://www.vietjetair.com/",
        "content-language": "zh-cn",
        "X-Session-Id": "null",
        "X-Aws-Waf-Token": token,
        "origin": "https://www.vietjetair.com",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-site",
        "connection": "keep-alive",
        "te": "trailers",
    }
    headers.update(script.zero_trust_headers("/booking/api/v1/get-session"))

    payload = {
        "currency": "VND",
        "adultCount": 1,
        "childCount": 0,
        "infantCount": 0,
        "departurePlace": dep_airport,
        "arrival": arr_airport,
        "requestId": request_id,
    }

    http_utils = getattr(script, "_WebScript__http_utils")
    timeout = getattr(script, "_WebScript__timeout")
    response = http_utils.post(
        url=f"https://vietjet-api.vietjetair.com/booking/api/v1/get-session?requestId={request_id}",
        headers=headers,
        data=payload,
        timeout=timeout,
    )

    if response.status != 200:
        body = _response_text(response)
        raise RuntimeError(f"get-session HTTP {response.status}: {body[:1000]}")

    response_data = response.to_dict()
    session_id = response_data.get("sessionId")
    if not session_id:
        raise RuntimeError(f"get-session 未返回 sessionId: {response_data}")

    return VJSessionCache().save(
        dep_airport=dep_airport,
        arr_airport=arr_airport,
        session_id=session_id,
        request_id=request_id,
        device_uuid=getattr(script, "_WebScript__vj_device_uuid"),
        zero_trust_config=getattr(script, "_WebScript__zero_trust_config"),
        session_exp_in=response_data.get("sessionExpIn"),
    )


# ==========================================
# 7. 辅助与工具函数
# ==========================================
def _routes_from_config(value: list[str]) -> list[tuple[str, str]]:
    routes = []
    for item in value:
        item = str(item or "").strip().upper()
        if not item or "-" not in item:
            continue
        dep_airport, arr_airport = item.split("-", 1)
        dep_airport = _clean_airport(dep_airport)
        arr_airport = _clean_airport(arr_airport)
        if dep_airport and arr_airport:
            routes.append((dep_airport, arr_airport))
    return _unique_routes(routes)


def _routes_from_db(db_path: Path, source: str) -> list[tuple[str, str]]:
    if not db_path.exists():
        return []
    routes = []
    try:
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT task_data
                FROM tasks
                WHERE source = ?
                    AND task_type IN ('search', 'shamBooking')
                """,
                (source.upper(),),
            ).fetchall()
    except sqlite3.Error as exc:
        _log(f"read routes failed: {exc}")
        return []

    for row in rows:
        task_data = _json_dict(row["task_data"])
        dep_airport = _clean_airport(task_data.get("depAirport"))
        arr_airport = _clean_airport(task_data.get("arrAirport"))
        if dep_airport and arr_airport:
            routes.append((dep_airport, arr_airport))
    return _unique_routes(routes)


def _proxy_from_db(db_path: Path, source: str) -> ProxyInfoModel:
    if db_path.exists():
        try:
            with sqlite3.connect(db_path) as conn:
                conn.row_factory = sqlite3.Row
                row = conn.execute(
                    "SELECT * FROM source_proxy_configs WHERE source = ? AND enabled = 1",
                    (source.upper(),),
                ).fetchone()
        except sqlite3.Error as exc:
            _log(f"read proxy config failed: {exc}")
            row = None

        if row and row["host"] and row["port"] and row["format"]:
            return ProxyInfoModel(
                host=str(row["host"]).strip(),
                port=int(row["port"]),
                username=str(row["username"] or "").strip() or None,
                password=str(row["password"] or "").strip() or None,
                region=str(row["region"] or "").strip() or None,
                session_time=int(row["session_time"]) if row["session_time"] else None,
                format=str(row["format"]).strip(),
            )
    return _clone_proxy(GlobalVariable.PROXY_INFO_DATA)


def _normalize_route_query(dep_airport: str, arr_airport: str) -> tuple[str, str]:
    dep_airport = _clean_airport(dep_airport)
    arr_airport = _clean_airport(arr_airport)
    if not dep_airport or not arr_airport:
        raise HTTPException(status_code=400, detail="depAirport/arrAirport 不能为空")
    return dep_airport, arr_airport


def _request_id_get() -> str:
    now = int(time.time() * 1000)
    chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    rnd = "".join(random.choice(chars) for _ in range(12))
    return f"{rnd}-{now}"


def _json_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    try:
        data = json.loads(value)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _clean_airport(value: Any) -> str:
    return str(value or "").strip().upper()


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0


def _session_state(item: dict[str, Any], now: float) -> tuple[str, int, int]:
    ready_at = _safe_float(item.get("readyAt"))
    expires_at = _safe_float(item.get("expiresAt") or item.get("sessionExpIn"))
    ready_in_seconds = max(0, int(ready_at - now)) if ready_at > now else 0
    expire_in_seconds = max(0, int(expires_at - now)) if expires_at > now else 0
    if expires_at <= now:
        return "expired", ready_in_seconds, expire_in_seconds
    if ready_at <= now:
        return "ready", ready_in_seconds, expire_in_seconds
    return "warming", ready_in_seconds, expire_in_seconds


def _preview(value: str) -> Optional[str]:
    if not value:
        return None
    if len(value) <= 48:
        return value
    return f"{value[:24]}...{value[-16:]}"


def _unique_routes(routes: list[tuple[str, str]]) -> list[tuple[str, str]]:
    result = []
    seen = set()
    for dep_airport, arr_airport in routes:
        key = (dep_airport, arr_airport)
        if key in seen:
            continue
        seen.add(key)
        result.append(key)
    return result


def _clone_proxy(proxy_info: ProxyInfoModel) -> ProxyInfoModel:
    if hasattr(proxy_info, "model_copy"):
        return proxy_info.model_copy(deep=True)
    return proxy_info.copy(deep=True)


def _response_text(response: Any) -> str:
    try:
        return response.to_text()
    except Exception:
        try:
            return json.dumps(response.to_dict(), ensure_ascii=False)
        except Exception:
            return ""


def _format_pool_stats(stats: dict[str, Any]) -> str:
    next_ready = stats.get("nextReadyInSeconds")
    next_ready_text = f" nextReadyIn={next_ready}s" if next_ready is not None else ""
    return (
        f"pool ready={stats['ready']} warming={stats['warming']} "
        f"expired={stats['expired']} target={TARGET_SIZE}{next_ready_text}"
    )


def _remember_stats(dep_airport: str, arr_airport: str, stats: dict[str, Any]) -> None:
    with _STATE_LOCK:
        _STATE["lastStats"][f"{dep_airport}-{arr_airport}"] = stats


def _set_state(**values: Any) -> None:
    with _STATE_LOCK:
        _STATE.update(values)


def _snapshot_state() -> dict[str, Any]:
    with _STATE_LOCK:
        return json.loads(json.dumps(_STATE, ensure_ascii=False))


def _log(message: str) -> None:
    print(f"{datetime.now():%Y-%m-%d %H:%M:%S} {message}", flush=True)


if __name__ == "__main__":
    uvicorn.run(app, host=HOST, port=PORT, reload=False)
