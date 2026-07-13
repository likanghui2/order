# 9G App Trace Token Cache Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cache 9G App search `trace_id` values in one global Redis ZSET, make them claimable after 120 seconds for 20 minutes, and consume one Token atomically for each `create_order + hold_booking` flow.

**Architecture:** A focused `NineGAppTraceCache` owns the Redis ZSET and Lua claim operation. `AppScript.search()` produces Tokens, while `AppScript.create_order()` atomically claims one and keeps it on that script instance so `hold_booking()` reuses it. The cache member is the raw Token string; time metadata exists only as the ZSET score.

**Tech Stack:** Python 3.13, redis-py 6.1, Redis ZSET/Lua, pytest 9, current `ServiceError` framework.

## Global Constraints

- Redis key is exactly `9g:app:trace:v1`.
- ZSET member contains only the raw `trace_id` Token string.
- Token ready delay is exactly 120 seconds.
- Token claim window is exactly 1200 seconds after it becomes ready.
- A claimed Token is removed atomically and cannot be reused by another task.
- One claimed Token is reused only by the current `create_order + hold_booking` pair.
- No route, proxy, device, task, passenger, or JSON data is cached.
- No fallback to an `AppScript` trace value produced by the current search.
- Do not modify or depend on `tools/vj_web_session_server.py`.
- Preserve all pre-existing uncommitted user changes when merging back to `main`.

---

## File Structure

- Create `flights/sunphuquocairways_9g/flight_common/app_trace_cache.py`: Redis ZSET storage, timing rules, Lua claim, stats, and framework error mapping.
- Modify `flights/sunphuquocairways_9g/script/app_script.py`: inject cache, save search Tokens, claim before create, reuse for hold.
- Modify `common/utils/log_redaction.py`: treat `Spa-Trace-Id` and `trace_id` as secrets.
- Create `tests/flight_9gapp/test_app_trace_cache.py`: isolated cache contract tests.
- Modify `tests/flight_9gapp/test_app_script.py`: producer and consumer integration tests.
- Modify `tests/flight_9gweb/test_log_redaction.py`: header and key redaction regression.

### Task 1: Redis ZSET Trace Token Cache

**Files:**
- Create: `flights/sunphuquocairways_9g/flight_common/app_trace_cache.py`
- Create: `tests/flight_9gapp/test_app_trace_cache.py`

**Interfaces:**
- Consumes: `RedisUtil.get_redis_connection()`, `GlobalVariable` Redis configuration, `ServiceError`.
- Produces: `NineGAppTraceCache.save(token: str) -> None`, `pop_ready() -> Optional[str]`, and `stats() -> dict[str, int]`.

- [ ] **Step 1: Write failing timing and storage tests**

Create a controlled Redis connection test double that records ZSET members as raw strings and implements the two Lua entry points according to their arguments. Tests must assert the public cache behavior, not internal helper calls:

```python
def test_token_is_raw_member_and_waits_120_seconds():
    clock = Clock(1_000)
    redis = MemoryRedis(clock)
    cache = NineGAppTraceCache(redis_connection=redis, clock=clock)

    cache.save("trace-token-1")

    assert redis.members(NineGAppTraceCache.KEY) == {"trace-token-1": 1_120}
    assert cache.pop_ready() is None
    clock.advance(120)
    assert cache.pop_ready() == "trace-token-1"
    assert cache.pop_ready() is None


def test_token_expires_20_minutes_after_ready():
    clock = Clock(1_000)
    cache = NineGAppTraceCache(redis_connection=MemoryRedis(clock), clock=clock)
    cache.save("trace-token-1")

    clock.advance(120 + 1_200 + 1)

    assert cache.pop_ready() is None
    assert cache.stats() == {"warming": 0, "ready": 0, "total": 0}
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
PYTHONPATH=. .venv/bin/python -m pytest tests/flight_9gapp/test_app_trace_cache.py -q
```

Expected: collection fails because `app_trace_cache.py` and `NineGAppTraceCache` do not exist.

- [ ] **Step 3: Implement the minimal cache**

Create `app_trace_cache.py` with this complete public implementation; keep any test-only Redis emulation inside the test file:

```python
import time
from typing import Callable, Optional

import redis

from common.errors.service_error import ServiceError, ServiceStateEnum
from common.global_variable import GlobalVariable
from common.utils.redis_util import RedisUtil


class NineGAppTraceCache:
    KEY = "9g:app:trace:v1"
    READY_SECONDS = 120
    AVAILABLE_SECONDS = 1_200
    KEY_TTL_SECONDS = READY_SECONDS + AVAILABLE_SECONDS

    POP_READY_SCRIPT = """
    local key = KEYS[1]
    local now = tonumber(ARGV[1])
    local available = tonumber(ARGV[2])
    local expired_before = now - available
    redis.call('ZREMRANGEBYSCORE', key, '-inf', expired_before)
    local items = redis.call('ZRANGEBYSCORE', key, '(' .. expired_before, now, 'LIMIT', 0, 1)
    if #items == 0 then
        return nil
    end
    redis.call('ZREM', key, items[1])
    return items[1]
    """

    def __init__(
        self,
        redis_connection=None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._redis_connection = redis_connection
        self._clock = clock
        self._redis_util = None if redis_connection is not None else RedisUtil(
            host=GlobalVariable.REDIS_HOST,
            port=GlobalVariable.REDIS_PORT,
            username=GlobalVariable.REDIS_USERNAME,
            password=GlobalVariable.REDIS_PASSWORD,
        )

    def _connection(self):
        return self._redis_connection or self._redis_util.get_redis_connection()

    def save(self, token: str) -> None:
        token = str(token or "").strip()
        if not token:
            raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, "9GAPP trace_id")
        now = float(self._clock())
        try:
            connection = self._connection()
            connection.zremrangebyscore(self.KEY, "-inf", now - self.AVAILABLE_SECONDS)
            connection.zadd(self.KEY, {token: now + self.READY_SECONDS})
            connection.expire(self.KEY, self.KEY_TTL_SECONDS)
        except redis.RedisError as error:
            raise ServiceError(
                ServiceStateEnum.BUSINESS_ERROR,
                "9GAPP trace_id缓存不可用",
            ) from error

    def pop_ready(self) -> Optional[str]:
        try:
            raw = self._connection().eval(
                self.POP_READY_SCRIPT,
                1,
                self.KEY,
                float(self._clock()),
                self.AVAILABLE_SECONDS,
            )
        except redis.RedisError as error:
            raise ServiceError(
                ServiceStateEnum.BUSINESS_ERROR,
                "9GAPP trace_id缓存不可用",
            ) from error
        if not raw:
            return None
        return raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)

    def stats(self) -> dict[str, int]:
        now = float(self._clock())
        expired_before = now - self.AVAILABLE_SECONDS
        try:
            connection = self._connection()
            connection.zremrangebyscore(self.KEY, "-inf", expired_before)
            ready = int(connection.zcount(self.KEY, f"({expired_before}", now))
            warming = int(connection.zcount(self.KEY, f"({now}", "+inf"))
        except redis.RedisError as error:
            raise ServiceError(
                ServiceStateEnum.BUSINESS_ERROR,
                "9GAPP trace_id缓存不可用",
            ) from error
        return {"warming": warming, "ready": ready, "total": warming + ready}
```

The test double must support `zremrangebyscore`, `zadd`, `expire`, `zcount`, and `eval` without storing anything other than Token members and numeric scores.

- [ ] **Step 4: Run tests and verify GREEN**

Run:

```bash
PYTHONPATH=. .venv/bin/python -m pytest tests/flight_9gapp/test_app_trace_cache.py -q
```

Expected: all cache tests pass, including empty Token validation, one-time claim, 119/120-second boundary, 20-minute expiry, stats, and Redis error mapping.

- [ ] **Step 5: Commit cache component**

```bash
git add flights/sunphuquocairways_9g/flight_common/app_trace_cache.py tests/flight_9gapp/test_app_trace_cache.py
git commit -m "feat(9gapp): add trace token ZSET cache"
```

### Task 2: Produce Tokens on Search and Consume on Booking

**Files:**
- Modify: `flights/sunphuquocairways_9g/script/app_script.py`
- Modify: `tests/flight_9gapp/test_app_script.py`

**Interfaces:**
- Consumes: `NineGAppTraceCache.save()` and `NineGAppTraceCache.pop_ready()` from Task 1.
- Produces: `AppScript(..., trace_cache=None)` whose search stores Tokens and whose create/hold flow uses one claimed Token.

- [ ] **Step 1: Write failing AppScript integration tests**

Add an injectable fake cache and revise the existing search test:

```python
class FakeTraceCache:
    def __init__(self, ready=None):
        self.ready = list(ready or [])
        self.saved = []

    def save(self, token):
        self.saved.append(token)

    def pop_ready(self):
        return self.ready.pop(0) if self.ready else None


def test_search_saves_trace_id_in_global_cache():
    cache = FakeTraceCache()
    tls = FakeTls([response({"success": True, "trace_id": "trace-1", "data": {}})])
    script = AppScript(None, tls=tls, captcha=FakeCaptcha(), trace_cache=cache)

    script.search([("SGN", "PQC", "2026-08-01T00:00:00.000")], 1, 0)

    assert cache.saved == ["trace-1"]
    assert script.trace_id is None


def test_create_and_hold_claim_one_cached_trace_token(monkeypatch):
    cache = FakeTraceCache(["cached-trace"])
    tls = FakeTls([
        response({"success": True, "data": {"booking_id": "booking-1"}}),
        response({"success": True, "data": {"pnr_number": "ABC123"}}),
    ])
    script = AppScript(None, tls=tls, captcha=FakeCaptcha(), trace_cache=cache)
    monkeypatch.setattr(time, "sleep", lambda _: None)

    script.create_order(["trip-1"], [{"first_name": "ADA"}], [{"email": "a@example.com"}])
    script.hold_booking("booking-1")

    assert [call["headers"]["Spa-Trace-Id"] for call in tls.calls] == [
        "cached-trace",
        "cached-trace",
    ]
    assert cache.ready == []
```

Add a separate test asserting an empty pool raises before `FakeTls.post()` is called.

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
PYTHONPATH=. .venv/bin/python -m pytest tests/flight_9gapp/test_app_script.py -q
```

Expected: fails because `AppScript.__init__` does not accept `trace_cache`, search does not save, and create does not claim.

- [ ] **Step 3: Implement producer and consumer wiring**

Update construction and the two flow boundaries:

```python
from flights.sunphuquocairways_9g.flight_common.app_trace_cache import NineGAppTraceCache


def __init__(
    self,
    proxy_info: Optional[ProxyInfoModel] = None,
    tls=None,
    captcha=None,
    trace_cache=None,
):
    self._proxy_info = proxy_info
    self._tls = tls or CurlCffiTls()
    self._captcha = captcha or DanLiCaptchaUtil(Config.INCAPSULA_APP_ID)
    self._device_id = str(uuid.uuid4()).upper()
    self.trace_id = None
    self.timeout = 60
    self._trace_cache = trace_cache or NineGAppTraceCache()
```

Replace the final three lines of `search()` with:

```python
    data = self._check_response(response)
    trace_id = str(data.get("trace_id") or "").strip()
    if not trace_id:
        raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, "9GAPP响应缺少trace_id")
    self._trace_cache.save(trace_id)
    self.trace_id = None
    return data
```

Insert these lines at the beginning of `create_order()`, immediately before the current `time.sleep(Config.CREATE_ORDER_WAIT_SECONDS)` statement:

```python
    trace_id = self._trace_cache.pop_ready()
    if not trace_id:
        raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, "9GAPP暂无可用trace_id")
    self.trace_id = trace_id
```

Do not pop in `hold_booking`; it must reuse `self.trace_id` set by `create_order`.

- [ ] **Step 4: Run AppScript and service/task regressions**

Run:

```bash
PYTHONPATH=. .venv/bin/python -m pytest tests/flight_9gapp -q
```

Expected: all 9G App tests pass. The existing single-PNR sham booking assertions remain unchanged.

- [ ] **Step 5: Commit App integration**

```bash
git add flights/sunphuquocairways_9g/script/app_script.py tests/flight_9gapp/test_app_script.py
git commit -m "feat(9gapp): consume cached trace tokens"
```

### Task 3: Prevent Trace Token Logging

**Files:**
- Modify: `common/utils/log_redaction.py`
- Modify: `tests/flight_9gweb/test_log_redaction.py`

**Interfaces:**
- Consumes: existing `redact_sensitive()` recursive and string redaction pipeline.
- Produces: redaction for `Spa-Trace-Id`, `trace_id`, and `traceId` in dictionaries, JSON, form values, and header-like strings.

- [ ] **Step 1: Write failing redaction tests**

```python
def test_trace_tokens_are_redacted_from_headers_and_payloads():
    redacted = redact_sensitive({
        "headers": {"Spa-Trace-Id": "trace-secret"},
        "trace_id": "trace-secret-2",
    })

    assert redacted["headers"]["Spa-Trace-Id"] == "[REDACTED]"
    assert redacted["trace_id"] == "[REDACTED]"
    assert "trace-secret" not in str(redacted)
```

- [ ] **Step 2: Run test and verify RED**

Run:

```bash
PYTHONPATH=. .venv/bin/python -m pytest tests/flight_9gweb/test_log_redaction.py::test_trace_tokens_are_redacted_from_headers_and_payloads -q
```

Expected: fails because the trace keys are not currently secret keys.

- [ ] **Step 3: Add trace keys to every redaction path**

Add these values to `_SECRET_KEYS`:

```python
"spatraceid",
"spa-trace-id",
"traceid",
"trace_id",
```

Add `Spa-Trace-Id|trace_id|traceId` to both `_KEY_VALUE_PATTERN` and `_FORM_VALUE_PATTERN`. Reuse the existing `[REDACTED]` replacement and do not add a second logging framework.

- [ ] **Step 4: Run security tests and verify GREEN**

```bash
PYTHONPATH=. .venv/bin/python -m pytest tests/flight_9gweb/test_log_redaction.py tests/flight_9gapp -q
```

Expected: all selected tests pass and no complete trace Token appears in captured logs.

- [ ] **Step 5: Commit log protection**

```bash
git add common/utils/log_redaction.py tests/flight_9gweb/test_log_redaction.py
git commit -m "fix(logging): redact 9G App trace tokens"
```

### Task 4: Full Verification and Local Main Integration

**Files:**
- Verify only; do not change unrelated files.

**Interfaces:**
- Consumes: all prior task commits.
- Produces: verified feature branch merged locally into `main`, preserving the user's dirty files.

- [ ] **Step 1: Run static and full verification**

```bash
PYTHONPATH=. .venv/bin/python -m compileall -q common flights/sunphuquocairways_9g task/9Gapp tests/flight_9gapp
PYTHONPATH=. .venv/bin/python -m pytest -q
git diff --check
```

Expected in the clean feature worktree: all tests pass with no syntax or whitespace errors.

- [ ] **Step 2: Review feature invariants**

Confirm with focused searches that:

```bash
rg -n "9g:app:trace:v1|READY_SECONDS = 120|AVAILABLE_SECONDS = 1_200" flights tests
rg -n "trace_cache\.save|trace_cache\.pop_ready" flights/sunphuquocairways_9g tests/flight_9gapp
rg -n "create_order\(" task/9Gapp/sham_booking.py
```

Expected: one global pool, one claim point, and one existing PNR creation call.

- [ ] **Step 3: Request code review**

Review atomicity, timing boundaries, Token leakage, Redis error behavior, and preservation of the single-PNR flow. Resolve only reproducible findings and rerun focused tests.

- [ ] **Step 4: Merge locally while preserving dirty files**

Stash only dirty files that overlap the feature, merge with `--no-ff`, then pop the stash and resolve in favor of the user's pre-existing App captcha and wait-time edits while retaining the new trace cache wiring.

- [ ] **Step 5: Verify merged main**

Run `tests/flight_9gapp` and the full suite. If the full suite still contains the pre-existing App captcha assertion mismatch, report it separately without overwriting the user's local `app_script.py` change.
