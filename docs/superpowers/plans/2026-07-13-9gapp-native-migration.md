# 9G App Native Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add complete `9GAPP` search, verify, and single-PNR sham-booking support using only the current repository framework.

**Architecture:** A current-model parser converts 9G API payloads into `FlightJourneyModel` objects, a thin Script owns HTTP/signing/Incapsula behavior, and a Service owns currency and booking-domain transformations. Current Celery task entry points orchestrate search and one-PNR sham booking without importing old framework types.

**Tech Stack:** Python 3.12+, Pydantic 2, Celery, curl-cffi through `CurlCffiTls`, pytest, Faker.

## Global Constraints

- The source identifier and queue prefix are exactly `9GAPP`.
- Sham booking creates exactly one PNR per task and reserves at most 5 adults.
- Search supports current single-trip and round-trip task inputs; sham booking remains single-trip because the current sham-booking request has no return date.
- Re-fetch the selected flight for the final passenger count before creating an order.
- Keep the pre-create wait configurable and default it to 30 seconds.
- Do not import old `common.models`, `CurlHttpUtil`, inventory models, or inventory Redis utilities.
- Do not modify or discard unrelated dirty-worktree changes.

---

## File Map

- Create `flights/sunphuquocairways_9g/__init__.py`: airline package marker.
- Create `flights/sunphuquocairways_9g/config.py`: immutable 9G constants, product mapping, and currency contexts.
- Create `flights/sunphuquocairways_9g/flight_common/__init__.py`: parser package marker.
- Create `flights/sunphuquocairways_9g/flight_common/app_flight_parser.py`: API-to-current-model parsing only.
- Create `flights/sunphuquocairways_9g/script/__init__.py`: HTTP package marker.
- Create `flights/sunphuquocairways_9g/script/app_script.py`: request construction, signing, transport, and response validation.
- Create `flights/sunphuquocairways_9g/service/__init__.py`: service package marker.
- Create `flights/sunphuquocairways_9g/service/app_service.py`: passenger/contact conversion and booking orchestration.
- Create `task/9Gapp/__init__.py`: task package marker.
- Create `task/9Gapp/search.py`: current search/verify task adapter.
- Create `task/9Gapp/sham_booking.py`: current single-PNR sham-booking adapter.
- Create `flights/sunphuquocairways_9g/Dockerfile`: worker image.
- Create `flights/sunphuquocairways_9g/start.sh`: `9GAPP` queue launcher.
- Create `tests/flight_9gapp/test_app_flight_parser.py`: parser contract tests.
- Create `tests/flight_9gapp/test_app_script.py`: signing and request tests.
- Create `tests/flight_9gapp/test_app_service.py`: currency and booking transformation tests.
- Create `tests/flight_9gapp/test_sham_booking.py`: task orchestration tests.
- Create `tests/flight_9gapp/test_source_registry.py`: task discovery test.

### Task 1: Configuration and Current-Model Flight Parser

**Files:**
- Create: `flights/sunphuquocairways_9g/__init__.py`
- Create: `flights/sunphuquocairways_9g/config.py`
- Create: `flights/sunphuquocairways_9g/flight_common/__init__.py`
- Create: `flights/sunphuquocairways_9g/flight_common/app_flight_parser.py`
- Test: `tests/flight_9gapp/test_app_flight_parser.py`

**Interfaces:**
- Produces: `Config.currency_context(currency: str) -> dict[str, str]`.
- Produces: `AppFlightParser.parse(response_data: dict, child_count: int = 0, promo_code: str = "") -> list[FlightJourneyModel]`.
- Produces: bundle `fare_key` containing the 9G `trip_id` and `ext["fareFamilyCode"]` containing the API fare-family code.

- [ ] **Step 1: Write failing parser tests**

Create a representative response fixture inline and assert required current-model fields:

```python
def test_parse_search_response_to_current_models():
    journeys = AppFlightParser.parse(SEARCH_RESPONSE, child_count=1, promo_code="SAVE")
    journey = journeys[0]
    assert journey.dep_airport == "SGN"
    assert journey.arr_airport == "PQC"
    assert [segment.flight_number for segment in journey.segments] == ["9G0123"]
    bundle = journey.bundles[0]
    assert bundle.fare_key == "outbound-trip-id"
    assert bundle.cabin == "Y"
    assert bundle.product_tag == "ECONOMY LITE"
    assert bundle.seat == 4
    assert bundle.price_info.adult_ticket_price == Decimal("1000000")
    assert bundle.price_info.adult_tax_price == Decimal("100000")
    assert bundle.price_info.child_ticket_price == Decimal("800000")
    assert bundle.ext["fareFamilyCode"] == "EL1"

def test_parse_filters_sold_out_bundle():
    response = deepcopy(SEARCH_RESPONSE)
    response["data"]["list_trip"][0]["booking_class"][0]["booking_status"] = "soldOut"
    assert AppFlightParser.parse(response) == []

def test_currency_context_rejects_unsupported_currency():
    with pytest.raises(ServiceError) as error:
        Config.currency_context("CNY")
    assert error.value.code == ServiceStateEnum.DATA_VALIDATION_FAILED.name
```

- [ ] **Step 2: Run parser tests and verify failure**

Run: `.venv/bin/pytest tests/flight_9gapp/test_app_flight_parser.py -q`

Expected: collection fails because the new package does not exist.

- [ ] **Step 3: Implement config and parser minimally**

Define `Config` with API base, API key/secret, User-Agent, Reese84 URL/app ID, `CREATE_ORDER_WAIT_SECONDS = 30`, product tags copied from the live old 9G implementation, and currency contexts for `VND`, `USD`, `SGD`, `THB`, `TWD`, `HKD`, and `KRW`.

The parser must construct current models directly:

```python
journey = FlightJourneyModel(
    segments=segments,
    bundles=bundles,
    journeyKey=trip.get("trip_id") or "^".join(segment.segment_key for segment in segments),
    depAirport=segments[0].dep_airport,
    arrAirport=segments[-1].arr_airport,
    depTime=segments[0].dep_time,
    arrTime=segments[-1].arr_time,
    ext={},
)
```

Map missing seat counts to 9, filter `booking_status == "soldOut"`, use `FreightRateTypeEnum.PT`, and return empty baggage through `FlightSsrInfoModel(baggage=[])` because the current baggage model cannot faithfully represent the old per-passenger allowance description.

- [ ] **Step 4: Run parser tests and verify pass**

Run: `.venv/bin/pytest tests/flight_9gapp/test_app_flight_parser.py -q`

Expected: all parser and configuration tests pass.

- [ ] **Step 5: Commit parser slice**

```bash
git add flights/sunphuquocairways_9g/__init__.py flights/sunphuquocairways_9g/config.py flights/sunphuquocairways_9g/flight_common tests/flight_9gapp/test_app_flight_parser.py
git commit -m "feat(9gapp): add flight response parser"
```

### Task 2: Signed HTTP Script and App Service

**Files:**
- Create: `flights/sunphuquocairways_9g/script/__init__.py`
- Create: `flights/sunphuquocairways_9g/script/app_script.py`
- Create: `flights/sunphuquocairways_9g/service/__init__.py`
- Create: `flights/sunphuquocairways_9g/service/app_service.py`
- Test: `tests/flight_9gapp/test_app_script.py`
- Test: `tests/flight_9gapp/test_app_service.py`

**Interfaces:**
- Consumes: `Config.currency_context` and `AppFlightParser.parse` from Task 1.
- Produces: `AppScript.initialize_session() -> None`.
- Produces: `AppScript.search(airport_data, adult_count, child_count, infant_count=0, promo_code="", **currency_context) -> dict`.
- Produces: `AppScript.create_order(trip_ids, passenger_list, contact_list, **currency_context) -> dict` and `hold_booking(booking_id, **currency_context) -> dict`.
- Produces: `AppService.search(dep_airport, arr_airport, dep_date, adt_number, chd_number, currency_code, ret_date=None, promo_code="") -> list[FlightJourneyModel]`.
- Produces: `AppService.create_and_hold(bundle, passengers, contact_info, currency_code) -> tuple[str, str]`, returning `(booking_id, pnr)`.

- [ ] **Step 1: Write failing signing and transport tests**

Use fake TLS and fixed `time.time`/`random.choices` values:

```python
def test_signed_headers_use_exact_compact_body(monkeypatch):
    script = AppScript(None, tls=FakeTls())
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

def test_search_builds_round_trip_payload():
    tls = FakeTls(ResponseInfoModel(data_bytes=b'{"success":true,"data":{}}', status=200, headers={}, url="x"))
    script = AppScript(None, tls=tls)
    script.search([("SGN", "PQC", "2026-08-01T00:00:00.000"), ("PQC", "SGN", "2026-08-04T00:00:00.000")], 2, 1)
    payload = json.loads(tls.last_data)
    assert len(payload["list_route"]) == 2
    assert payload["adult"] == 2
    assert payload["child"] == 1
```

- [ ] **Step 2: Write failing service transformation tests**

```python
def test_create_and_hold_sends_current_passengers_and_returns_pnr(monkeypatch):
    script = FakeScript()
    service = AppService(None, script=script)
    booking_id, pnr = service.create_and_hold(BUNDLE, PASSENGERS, CONTACT, "VND")
    assert booking_id == "booking-1"
    assert pnr == "ABC123"
    assert script.create_calls == 1
    assert script.hold_calls == 1
    assert script.passenger_list[0]["first_name"] == PASSENGERS[0].first_name
    assert script.contact_list[0]["email"] == CONTACT.email_address

def test_create_and_hold_rejects_missing_booking_id():
    with pytest.raises(ServiceError) as error:
        AppService(None, script=MissingBookingIdScript()).create_and_hold(BUNDLE, PASSENGERS, CONTACT, "VND")
    assert error.value.code == ServiceStateEnum.DATA_VALIDATION_FAILED.name
```

- [ ] **Step 3: Run script/service tests and verify failure**

Run: `.venv/bin/pytest tests/flight_9gapp/test_app_script.py tests/flight_9gapp/test_app_service.py -q`

Expected: collection fails because Script and Service are absent.

- [ ] **Step 4: Implement Script with injectable boundaries**

`AppScript.__init__` accepts optional `tls` and `captcha` test doubles while production defaults remain current utilities:

```python
def __init__(self, proxy_info=None, tls=None, captcha=None):
    self._proxy_info = proxy_info
    self._tls = tls or CurlCffiTls()
    self._captcha = captcha or DanLiCaptchaUtil(Config.INCAPSULA_APP_ID)
```

Implement compact JSON, exact HMAC signing, search payloads, one create call, one hold call, 9G no-flight detection, and current error mapping. `create_order` sleeps `Config.CREATE_ORDER_WAIT_SECONDS`, then obtains a token and sends it as `x-d-token`. Do not decorate create or hold with automatic retries.

- [ ] **Step 5: Implement Service transformations**

Build current passenger data using `.first_name`, `.last_name`, `.birthday`, `.type`, and `.gender`. Build two contact records from `.email_address`, `.phone_code`, and `.phone_number`. Validate `fare_key`, booking ID, and PNR with `ServiceStateEnum.DATA_VALIDATION_FAILED`. Search delegates parsing to `AppFlightParser.parse` and raises `NO_FLIGHT_DATA` for an empty result.

- [ ] **Step 6: Run Script and Service tests**

Run: `.venv/bin/pytest tests/flight_9gapp/test_app_script.py tests/flight_9gapp/test_app_service.py -q`

Expected: all tests pass and no network is contacted.

- [ ] **Step 7: Commit service slice**

```bash
git add flights/sunphuquocairways_9g/script flights/sunphuquocairways_9g/service tests/flight_9gapp/test_app_script.py tests/flight_9gapp/test_app_service.py
git commit -m "feat(9gapp): add signed app booking service"
```

### Task 3: Current Search and Verify Task Adapter

**Files:**
- Create: `task/9Gapp/__init__.py`
- Create: `task/9Gapp/search.py`
- Test: `tests/flight_9gapp/test_source_registry.py`

**Interfaces:**
- Consumes: `AppService.search` from Task 2 and current `RequestSearchTaskDataModel`.
- Produces: Celery task `task.9Gapp.search.main` discoverable for source `9GAPP`.

- [ ] **Step 1: Write failing registry and date tests**

```python
def test_registry_discovers_9gapp_search_and_sham_booking():
    assert module_for_source("9GAPP", "search") == "task.9Gapp.search"
    assert module_for_source("9GAPP", "shamBooking") == "task.9Gapp.sham_booking"

@pytest.mark.parametrize(("value", "expected"), [("20260801", "2026-08-01T00:00:00.000"), ("2026-08-01", "2026-08-01T00:00:00.000")])
def test_app_date(value, expected):
    assert _app_date(value) == expected
```

- [ ] **Step 2: Run tests and verify failure**

Run: `.venv/bin/pytest tests/flight_9gapp/test_source_registry.py -q`

Expected: `9GAPP` modules are not discovered.

- [ ] **Step 3: Implement task adapter**

Follow `task/GAapp/search.py`, but pass both current dates and the private code:

```python
response = service.search(
    dep_airport=search_data.dep_airport,
    arr_airport=search_data.arr_airport,
    dep_date=_app_date(search_data.dep_date),
    ret_date=_app_date(search_data.ret_date),
    adt_number=search_data.adult_number,
    chd_number=search_data.child_number,
    currency_code=search_data.currency_code,
    promo_code=search_data.private_code[0] if search_data.private_code else "",
)
```

Initialize a fresh service when cache is absent and retain the current 280-second `MachineCache` convention.

- [ ] **Step 4: Run adapter tests**

Run: `.venv/bin/pytest tests/flight_9gapp/test_source_registry.py -q`

Expected: tests pass.

- [ ] **Step 5: Commit search adapter**

```bash
git add task/9Gapp/__init__.py task/9Gapp/search.py tests/flight_9gapp/test_source_registry.py
git commit -m "feat(9gapp): register search task"
```

### Task 4: Single-PNR Sham Booking Task

**Files:**
- Create: `task/9Gapp/sham_booking.py`
- Test: `tests/flight_9gapp/test_sham_booking.py`

**Interfaces:**
- Consumes: `AppService.search`, `AppService.create_and_hold`, and current sham-booking models.
- Produces: `_select_bundle(journey, cabin, product_tag=None) -> FlightBundleModel`.
- Produces: `_run_sham_booking(service, sham_booking_data, response_order_data) -> ResponseOrderInfoModel`, separated from the decorated Celery task for deterministic unit tests.

- [ ] **Step 1: Write failing selection tests**

```python
def test_select_bundle_matches_cabin_and_product():
    selected = _select_bundle(JOURNEY, "Y", "ECONOMY LITE")
    assert selected.cabin == "Y"
    assert selected.product_tag == "ECONOMY LITE"

def test_select_bundle_rejects_missing_product():
    with pytest.raises(ServiceError) as error:
        _select_bundle(JOURNEY, "Y", "BUSINESS PRIME")
    assert error.value.code == ServiceStateEnum.NO_AVAILABLE_BUNDLE.name
```

- [ ] **Step 2: Write failing one-PNR orchestration test**

```python
def test_sham_booking_searches_twice_and_creates_one_pnr(monkeypatch):
    service = FakeService(first_seats=8, second_seats=5)
    response = _run_sham_booking(service, REQUEST, ResponseOrderInfoModel())
    assert service.search_adult_counts == [1, 5]
    assert service.create_calls == 1
    assert response.pnr == "ABC123"
    assert len(response.passengers) == 5
    assert response.total_amount == Decimal("5500000")
    assert response.order_state == OrderStateEnum.HOLD
```

Add negative tests for no matching flight, zero seats, and second-search seats below the chosen count.

- [ ] **Step 3: Run sham tests and verify failure**

Run: `.venv/bin/pytest tests/flight_9gapp/test_sham_booking.py -q`

Expected: collection fails because the task module is absent.

- [ ] **Step 4: Implement single-PNR orchestration**

Use `MAX_SEAT_COUNT = 5`. Search once for one adult, select the requested flight/bundle, build exactly `min(bundle.seat, 5)` passengers, then search again for that count and reselect. Reject a second result with fewer seats using `BUSINESS_ERROR`. Build contact names from the first passenger, invoke `create_and_hold` exactly once, reduce `journey.bundles` to the selected bundle, and calculate:

```python
response_order_data.total_amount = (
    use_bundle.price_info.adult_ticket_price + use_bundle.price_info.adult_tax_price
) * seat_count
```

Read optional `productTag` from `sham_booking_data.ext`. The decorated `main` only constructs the real service, initializes it, and delegates to `_run_sham_booking`.

- [ ] **Step 5: Run sham tests**

Run: `.venv/bin/pytest tests/flight_9gapp/test_sham_booking.py -q`

Expected: all tests pass, `create_calls == 1`, and no network is contacted.

- [ ] **Step 6: Commit sham adapter**

```bash
git add task/9Gapp/sham_booking.py tests/flight_9gapp/test_sham_booking.py
git commit -m "feat(9gapp): add single PNR sham booking"
```

### Task 5: Worker Packaging and Full Verification

**Files:**
- Create: `flights/sunphuquocairways_9g/Dockerfile`
- Create: `flights/sunphuquocairways_9g/start.sh`

**Interfaces:**
- Consumes: `task.9Gapp.search` and `task.9Gapp.sham_booking`.
- Produces: a worker image that handles `9GAPP-search`, `9GAPP-verify`, and `9GAPP-shamBooking` queues.

- [ ] **Step 1: Add launcher smoke test command before implementation**

Run: `bash -n flights/sunphuquocairways_9g/start.sh`

Expected: failure because the file is absent.

- [ ] **Step 2: Implement Dockerfile and launcher**

Use the current Python 3.12 worker image convention. Copy `flights/sunphuquocairways_9g`, `common`, `task`, `requirements.txt`, and `requirements-py312.txt`. The launcher must use:

```bash
case "$TASK_TYPE" in
  "search" | "verify")
    exec celery -A task.9Gapp.search worker -Q "9GAPP-$TASK_TYPE" -P threads --concurrency="$CONCURRENCY" --without-heartbeat --without-gossip --without-mingle --task-events
    ;;
  "shamBooking")
    exec celery -A task.9Gapp.sham_booking worker -Q "9GAPP-shamBooking" -P threads --concurrency="$CONCURRENCY" --without-heartbeat --without-gossip --without-mingle --task-events
    ;;
  *)
    echo "Unknown task: $TASK_TYPE"
    exit 1
    ;;
esac
```

- [ ] **Step 3: Verify syntax and imports**

Run: `bash -n flights/sunphuquocairways_9g/start.sh`

Expected: exit 0.

Run: `.venv/bin/python -m compileall -q flights/sunphuquocairways_9g task/9Gapp tests/flight_9gapp`

Expected: exit 0.

- [ ] **Step 4: Run focused and regression tests**

Run: `.venv/bin/pytest tests/flight_9gapp -q`

Expected: all 9G tests pass.

Run: `.venv/bin/pytest -q`

Expected: all collected repository tests pass; if legacy scripts are collected incorrectly, record the pre-existing collection issue and rerun the focused suite.

- [ ] **Step 5: Audit migration boundaries**

Run: `rg -n "common\.models|CurlHttpUtil|InventoryBooking|redis" flights/sunphuquocairways_9g task/9Gapp`

Expected: no matches.

Run: `git diff --check`

Expected: no whitespace errors in task files; unrelated existing user changes remain untouched.

- [ ] **Step 6: Commit worker packaging**

```bash
git add flights/sunphuquocairways_9g/Dockerfile flights/sunphuquocairways_9g/start.sh
git commit -m "build(9gapp): add worker packaging"
```
