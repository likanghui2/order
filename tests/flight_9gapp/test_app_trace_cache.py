import math

import pytest
import redis

from common.errors.service_error import ServiceError, ServiceStateEnum
from flights.sunphuquocairways_9g.flight_common.app_trace_cache import NineGAppTraceCache


class Clock:
    def __init__(self, now):
        self.now = now

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


class MemoryRedis:
    def __init__(self, clock):
        self.clock = clock
        self._members = {}

    @staticmethod
    def _bound(value):
        exclusive = isinstance(value, str) and value.startswith("(")
        if exclusive:
            value = value[1:]
        if value == "-inf":
            return -math.inf, exclusive
        if value == "+inf":
            return math.inf, exclusive
        return float(value), exclusive

    @classmethod
    def _in_range(cls, score, minimum, maximum):
        lower, lower_exclusive = cls._bound(minimum)
        upper, upper_exclusive = cls._bound(maximum)
        lower_matches = score > lower if lower_exclusive else score >= lower
        upper_matches = score < upper if upper_exclusive else score <= upper
        return lower_matches and upper_matches

    def members(self, key):
        return dict(self._members.get(key, {}))

    def zremrangebyscore(self, key, minimum, maximum):
        members = self._members.get(key, {})
        removed = [
            member
            for member, score in members.items()
            if self._in_range(score, minimum, maximum)
        ]
        for member in removed:
            del members[member]
        return len(removed)

    def zadd(self, key, mapping):
        members = self._members.setdefault(key, {})
        added = sum(member not in members for member in mapping)
        members.update({member: float(score) for member, score in mapping.items()})
        return added

    def expire(self, key, seconds):
        return key in self._members and seconds > 0

    def zcount(self, key, minimum, maximum):
        return sum(
            self._in_range(score, minimum, maximum)
            for score in self._members.get(key, {}).values()
        )

    def eval(self, script, number_of_keys, *args):
        assert number_of_keys == 1
        key, now, available = args
        expired_before = float(now) - float(available)
        self.zremrangebyscore(key, "-inf", expired_before)
        ready = sorted(
            (
                (score, member)
                for member, score in self._members.get(key, {}).items()
                if expired_before < score <= float(now)
            )
        )
        if not ready:
            return None
        _, member = ready[0]
        del self._members[key][member]
        return member.encode("utf-8")


class ErrorRedis:
    @staticmethod
    def _raise(*args, **kwargs):
        raise redis.RedisError("redis unavailable")

    zremrangebyscore = _raise
    zadd = _raise
    expire = _raise
    zcount = _raise
    eval = _raise


def test_token_is_raw_member_and_waits_120_seconds():
    clock = Clock(1_000)
    redis_connection = MemoryRedis(clock)
    cache = NineGAppTraceCache(redis_connection=redis_connection, clock=clock)

    cache.save("trace-token-1")

    assert redis_connection.members(NineGAppTraceCache.KEY) == {"trace-token-1": 1_120}
    assert cache.pop_ready() is None
    clock.advance(119)
    assert cache.pop_ready() is None
    clock.advance(1)
    assert cache.pop_ready() == "trace-token-1"
    assert cache.pop_ready() is None


def test_token_expires_20_minutes_after_ready():
    clock = Clock(1_000)
    cache = NineGAppTraceCache(redis_connection=MemoryRedis(clock), clock=clock)
    cache.save("trace-token-1")

    clock.advance(120 + 1_200 + 1)

    assert cache.pop_ready() is None
    assert cache.stats() == {"warming": 0, "ready": 0, "total": 0}


def test_stats_reports_warming_ready_and_total_tokens():
    clock = Clock(1_000)
    cache = NineGAppTraceCache(redis_connection=MemoryRedis(clock), clock=clock)
    cache.save("ready-token")
    clock.advance(60)
    cache.save("warming-token")

    clock.advance(60)

    assert cache.stats() == {"warming": 1, "ready": 1, "total": 2}
    assert cache.pop_ready() == "ready-token"
    assert cache.stats() == {"warming": 1, "ready": 0, "total": 1}


@pytest.mark.parametrize("token", [None, "", "   "])
def test_save_rejects_empty_token(token):
    clock = Clock(1_000)
    cache = NineGAppTraceCache(redis_connection=MemoryRedis(clock), clock=clock)

    with pytest.raises(ServiceError) as error:
        cache.save(token)

    assert error.value.code == ServiceStateEnum.DATA_VALIDATION_FAILED.name
    assert "9GAPP trace_id" in error.value.message


@pytest.mark.parametrize("operation", ["save", "pop_ready", "stats"])
def test_redis_errors_are_mapped_to_business_error(operation):
    cache = NineGAppTraceCache(redis_connection=ErrorRedis(), clock=Clock(1_000))

    with pytest.raises(ServiceError) as error:
        if operation == "save":
            cache.save("trace-token-1")
        else:
            getattr(cache, operation)()

    assert error.value.code == ServiceStateEnum.BUSINESS_ERROR.name
    assert "9GAPP trace_id缓存不可用" in error.value.message
