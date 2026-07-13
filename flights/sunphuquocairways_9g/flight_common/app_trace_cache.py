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
