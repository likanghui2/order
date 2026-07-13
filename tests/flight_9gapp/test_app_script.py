import hashlib
import hmac
import json
import random
import time

import pytest

from common.errors.service_error import ServiceError, ServiceStateEnum
from common.model.response_info_model import ResponseInfoModel
from flights.sunphuquocairways_9g.config import Config
from flights.sunphuquocairways_9g.script.app_script import AppScript


class FakeTls:
    def __init__(self, responses=None):
        self.responses = list(responses or [])
        self.initialized_with = None
        self.calls = []

    def initialize(self, proxy_info, **kwargs):
        self.initialized_with = (proxy_info, kwargs)

    def post(self, **kwargs):
        self.calls.append(kwargs)
        return self.responses.pop(0)

    def get(self, **kwargs):
        self.calls.append(kwargs)
        return self.responses.pop(0)


class FakeCaptcha:
    def __init__(self):
        self.calls = []

    def incapsula_token_get(self, **kwargs):
        self.calls.append(kwargs)
        return "token-1"


class FakeTraceCache:
    def __init__(self, ready=None):
        self.ready = list(ready or [])
        self.saved = []

    def save(self, token):
        self.saved.append(token)

    def pop_ready(self):
        return self.ready.pop(0) if self.ready else None


def response(data: dict, status: int = 200) -> ResponseInfoModel:
    return ResponseInfoModel(
        data_bytes=json.dumps(data).encode(),
        status=status,
        headers={},
        url="https://mobile-api.sunphuquocairways.com/test",
    )


def test_signed_headers_use_exact_compact_body(monkeypatch):
    script = AppScript(None, tls=FakeTls(), captcha=FakeCaptcha())
    monkeypatch.setattr(time, "time", lambda: 1.0)
    monkeypatch.setattr(random, "choices", lambda *args, **kwargs: list("abcdefghij"))
    body = '{"adult":1}'

    headers = script.signed_headers(body, office_id="HAN9G08MB")

    expected = hmac.new(
        Config.HMAC_API_SECRET.encode(),
        f"POST|/normal/search|1000|{body}|abcdefghij".encode(),
        hashlib.sha256,
    ).hexdigest()
    assert headers["X-Signature"] == expected
    assert headers["X-Office-Id"] == "HAN9G08MB"
    assert headers["X-Timestamp"] == "1000"
    assert headers["X-Nonce"] == "abcdefghij"


def test_search_builds_round_trip_payload_and_saves_trace_id_in_global_cache():
    cache = FakeTraceCache()
    tls = FakeTls([response({"success": True, "trace_id": "trace-1", "data": {}})])
    script = AppScript(None, tls=tls, captcha=FakeCaptcha(), trace_cache=cache)

    result = script.search(
        [("SGN", "PQC", "2026-08-01T00:00:00.000"), ("PQC", "SGN", "2026-08-04T00:00:00.000")],
        2,
        1,
        promo_code="SAVE",
        office_id="HAN9G08MB",
    )

    payload = json.loads(tls.calls[0]["data"])
    assert len(payload["list_route"]) == 2
    assert payload["adult"] == 2
    assert payload["child"] == 1
    assert payload["option"]["promo_code"] == "SAVE"
    assert result["success"] is True
    assert cache.saved == ["trace-1"]
    assert script.trace_id is None


def test_search_rejects_response_without_trace_id():
    cache = FakeTraceCache()
    tls = FakeTls([response({"success": True, "data": {}})])
    script = AppScript(None, tls=tls, captcha=FakeCaptcha(), trace_cache=cache)

    with pytest.raises(ServiceError) as error:
        script.search([("SGN", "PQC", "2026-08-01T00:00:00.000")], 1, 0)

    assert error.value.code == ServiceStateEnum.DATA_VALIDATION_FAILED.name
    assert cache.saved == []


def test_create_order_waits_gets_token_and_sends_it_once(monkeypatch):
    tls = FakeTls([response({"success": True, "data": {"booking_id": "booking-1"}})])
    captcha = FakeCaptcha()
    script = AppScript(
        None,
        tls=tls,
        captcha=captcha,
        trace_cache=FakeTraceCache(["cached-trace"]),
    )
    waits = []
    monkeypatch.setattr(time, "sleep", waits.append)

    script.create_order(
        ["trip-1"],
        [{"first_name": "ADA"}],
        [{"email": "ada@example.com"}],
        office_id="HAN9G08MB",
    )

    assert waits == [Config.CREATE_ORDER_WAIT_SECONDS]
    assert len(captcha.calls) == 1
    assert tls.calls[0]["headers"]["x-d-token"] == "token-1"
    assert json.loads(tls.calls[0]["data"])["trip_ids"] == ["trip-1"]


def test_create_and_hold_claim_one_cached_trace_token(monkeypatch):
    cache = FakeTraceCache(["cached-trace"])
    tls = FakeTls(
        [
            response({"success": True, "data": {"booking_id": "booking-1"}}),
            response({"success": True, "data": {"pnr_number": "ABC123"}}),
        ]
    )
    script = AppScript(None, tls=tls, captcha=FakeCaptcha(), trace_cache=cache)
    monkeypatch.setattr(time, "sleep", lambda _: None)

    script.create_order(["trip-1"], [{"first_name": "ADA"}], [{"email": "a@example.com"}])
    script.hold_booking("booking-1")

    assert [call["headers"]["Spa-Trace-Id"] for call in tls.calls] == [
        "cached-trace",
        "cached-trace",
    ]
    assert cache.ready == []


def test_create_order_rejects_empty_trace_pool_before_post(monkeypatch):
    tls = FakeTls()
    script = AppScript(None, tls=tls, captcha=FakeCaptcha(), trace_cache=FakeTraceCache())
    monkeypatch.setattr(time, "sleep", lambda _: None)

    with pytest.raises(ServiceError) as error:
        script.create_order(["trip-1"], [{"first_name": "ADA"}], [{"email": "a@example.com"}])

    assert error.value.code == ServiceStateEnum.BUSINESS_ERROR.name
    assert tls.calls == []


def test_no_flight_response_maps_to_current_error():
    tls = FakeTls([response({"error": {"value": "NO FLIGHTS FOUND"}}, status=400)])
    script = AppScript(None, tls=tls, captcha=FakeCaptcha())

    with pytest.raises(ServiceError) as error:
        script.search([("SGN", "PQC", "2026-08-01T00:00:00.000")], 1, 0)

    assert error.value.code == ServiceStateEnum.NO_FLIGHT_DATA.name


def test_initialize_session_uses_current_tls_client():
    tls = FakeTls()
    proxy = object()
    script = AppScript(proxy, tls=tls, captcha=FakeCaptcha())

    script.initialize_session()

    assert tls.initialized_with == (proxy, {"impersonate": "chrome146"})
