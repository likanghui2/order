# 9G Web Native Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add current-framework-native `9GWEB` search, verify, single-PNR sham booking, booking with optional payment, and order-detail support.

**Architecture:** Web-specific parsers convert Amadeus DES payloads into current models, an injectable Script owns HTTP/authentication/risk endpoints, and an injectable Service owns passenger/cart/order/payment orchestration. Four current Celery modules expose the integration without changing shared task models or the existing `9GAPP` implementation.

**Tech Stack:** Python 3.13, Pydantic 2, Celery, `CurlCffiTls`, `DanLiCaptchaUtil`, `NoCaptchaUtil`, `CardinalcommerceUtil`, pytest.

## Global Constraints

- Source and queue prefix are exactly `9GWEB`.
- Sham booking creates exactly one PNR and reserves at most five adults.
- Payment remains inside `booking`; no standalone pay task is added.
- Purchase Order, paid baggage, 3DS, and payment submission have no blind automatic retry.
- Existing `9GAPP` modules and behavior remain unchanged.
- No old `common.models`, `CurlHttpUtil`, inventory models, or inventory Redis utilities.
- All automated tests use injected fakes and perform no live web, captcha, proxy, or payment calls.
- Existing dirty-worktree files are not overwritten or committed.

---

## File Map

- Modify `flights/sunphuquocairways_9g/config.py`: Web constants and currency-country mapping.
- Create `flights/sunphuquocairways_9g/flight_common/web_flight_parser.py`: Web flight parsing.
- Create `flights/sunphuquocairways_9g/flight_common/web_order_parser.py`: Web order parsing.
- Create `flights/sunphuquocairways_9g/script/web_script.py`: Web transport and endpoint requests.
- Create `flights/sunphuquocairways_9g/service/web_service.py`: Web domain orchestration.
- Create `task/9Gweb/__init__.py`, `search.py`, `sham_booking.py`, `booking.py`, `order_detail.py`: task adapters and local examples.
- Create `flights/sunphuquocairways_9g/Dockerfile.web` and `start-web.sh`: worker packaging.
- Create `tests/flight_9gweb/`: focused offline tests.

### Task 1: Web Configuration and Flight Parser

**Files:**
- Modify: `flights/sunphuquocairways_9g/config.py`
- Create: `flights/sunphuquocairways_9g/flight_common/web_flight_parser.py`
- Test: `tests/flight_9gweb/test_web_flight_parser.py`

**Interfaces:**
- Produces: `Config.web_currency_context(currency: str) -> dict[str, str]`.
- Produces: `WebFlightParser.parse(response_data: dict, child_count: int = 0, promo_code: str = "") -> list[FlightJourneyModel]`.

- [ ] **Step 1: Write failing configuration/parser tests**

```python
def test_web_currency_context_maps_cny_and_rejects_unknown():
    assert Config.web_currency_context("CNY")["country_code"] == "CN"
    with pytest.raises(ServiceError):
        Config.web_currency_context("EUR")

def test_parser_maps_web_bundle_to_current_model():
    journey = WebFlightParser.parse(WEB_SEARCH_RESPONSE, child_count=1, promo_code="SAVE")[0]
    assert journey.segments[0].flight_number == "9G0123"
    bundle = journey.bundles[0]
    assert bundle.fare_key == "bound-1"
    assert bundle.product_tag == "ECONOMY LITE"
    assert bundle.seat == 4
    assert bundle.price_info.currency == "VND"
```

- [ ] **Step 2: Verify RED**

Run: `PYTHONPATH=. /Users/a1234/Desktop/rakdFlightLocalShamBooking/.venv/bin/pytest tests/flight_9gweb/test_web_flight_parser.py -q`

Expected: import failure because `web_flight_parser.py` does not exist.

- [ ] **Step 3: Implement Web constants and parser**

Add Web API/OAuth/captcha/card constants and `WEB_CURRENCY_COUNTRY_CODES`. Parse `data.airBoundGroups`, `dictionaries.flight`, `dictionaries.location`, and each bound's prices into current segments and bundles. Use `fare_key="^".join(air_bound_ids)`, `FreightRateTypeEnum.PT`, current price/SSR models, minimum segment quota, and filter sold-out entries.

- [ ] **Step 4: Verify GREEN and commit**

Run: `PYTHONPATH=. /Users/a1234/Desktop/rakdFlightLocalShamBooking/.venv/bin/pytest tests/flight_9gweb/test_web_flight_parser.py -q`

Expected: all tests pass.

```bash
git add flights/sunphuquocairways_9g/config.py flights/sunphuquocairways_9g/flight_common/web_flight_parser.py tests/flight_9gweb/test_web_flight_parser.py
git commit -m "feat(9gweb): add Web flight parser"
```

### Task 2: Injectable Web Script

**Files:**
- Create: `flights/sunphuquocairways_9g/script/web_script.py`
- Test: `tests/flight_9gweb/test_web_script.py`

**Interfaces:**
- Produces: `WebScript.initialize_session()`, `authenticate(currency)`, `search(...)`, `create_cart(air_bound_ids)`, `update_traveler(...)`, `add_contacts(...)`, `purchase_order(cart_id)`, `services_by_order(...)`, `add_services(...)`, `payment_methods(...)`, `payment_action(...)`, `payment_records(...)`, and `get_itinerary(...)`.
- Constructor accepts `tls`, `captcha`, and `hcaptcha` fakes.

- [ ] **Step 1: Write failing auth/request tests**

```python
def test_authenticate_solves_incapsula_and_requests_oauth():
    script = WebScript(PROXY, tls=FakeTls([oauth_response()]), captcha=FakeCaptcha())
    script.initialize_session()
    script.authenticate("VND")
    assert script.authorization == "Bearer token-1"
    assert script.country_code == "VN"

def test_search_builds_current_round_trip_payload():
    script = authenticated_script(response(WEB_SEARCH_RESPONSE))
    script.search([("SGN", "PQC", DATE1), ("PQC", "SGN", DATE2)], 2, 1, "SAVE")
    payload = json.loads(script.tls.calls[-1]["data"])
    assert len(payload["itineraries"]) == 2
    assert [item["passengerTypeCode"] for item in payload["travelers"]] == ["ADT", "ADT", "CHD"]
```

- [ ] **Step 2: Verify RED**

Run: `PYTHONPATH=. /Users/a1234/Desktop/rakdFlightLocalShamBooking/.venv/bin/pytest tests/flight_9gweb/test_web_script.py -q`

Expected: import failure because `WebScript` does not exist.

- [ ] **Step 3: Implement endpoint wrappers**

Use `CurlCffiTls` and `ResponseInfoModel`, compact JSON, URL-encoded OAuth form bodies, common DES headers, a stable UUID with an incrementing request counter, exact expected status codes, and `_response_json(response, expected_status)` that maps no-flight, challenge, HTTP, and invalid JSON responses to current errors. Each mutation method performs one HTTP request per call.

- [ ] **Step 4: Verify GREEN and commit**

Run the focused script tests, expect all pass, then:

```bash
git add flights/sunphuquocairways_9g/script/web_script.py tests/flight_9gweb/test_web_script.py
git commit -m "feat(9gweb): add injectable Web API script"
```

### Task 3: Order Parser and Core Web Service

**Files:**
- Create: `flights/sunphuquocairways_9g/flight_common/web_order_parser.py`
- Create: `flights/sunphuquocairways_9g/service/web_service.py`
- Test: `tests/flight_9gweb/test_web_order_parser.py`
- Test: `tests/flight_9gweb/test_web_service.py`

**Interfaces:**
- Produces: `WebOrderParser.parse(itinerary: dict, baggage: dict | None = None) -> ResponseOrderInfoModel`.
- Produces: `WebService.search(...)`, `create_order(bundle, passengers, contact_info) -> BookingResult`, `add_requested_baggage(...)`, and `order_detail(pnr, last_name)`.
- `BookingResult` contains `pnr`, `journey`, `bundle`, `passengers`, `contact_info`, `total_amount`, `currency`, `flight_ids`, and `contact_id`.

- [ ] **Step 1: Write failing order/service tests**

```python
def test_order_parser_maps_eticket_to_open_for_use():
    order = WebOrderParser.parse(ITINERARY_WITH_TICKET)
    assert order.order_state == OrderStateEnum.OPEN_FOR_USE
    assert order.passengers[0].ticket_number == "1234567890123"

def test_create_order_updates_every_traveler_and_purchases_once():
    service = WebService(None, script=FakeScript())
    result = service.create_order(BUNDLE, PASSENGERS, CONTACT)
    assert service.script.purchase_calls == 1
    assert service.script.updated_travelers == len(PASSENGERS)
    assert result.pnr == "ABC123"
```

- [ ] **Step 2: Verify RED**

Run both focused files; expect missing modules.

- [ ] **Step 3: Implement parser and Service**

Transform current passenger fields into DES titles/dates, update all cart traveler IDs, add email/phone contacts, call Purchase Order once, map returned traveler and flight IDs, derive total using currency decimal places, and validate cart ID/PNR/core amount. Order parsing maps eticket to `OPEN_FOR_USE`, valid unticketed order to `HOLD`, explicit cancellation to `CANCEL`, and unknown status to `UNKNOWN`.

- [ ] **Step 4: Verify GREEN and commit**

Run focused tests, expect all pass, then commit parser, Service, and tests with `feat(9gweb): add Web booking service`.

### Task 4: Payment Orchestration

**Files:**
- Modify: `flights/sunphuquocairways_9g/service/web_service.py`
- Test: `tests/flight_9gweb/test_web_payment.py`

**Interfaces:**
- Produces: `WebService.pay_order(pnr, passengers, contact_info, payment_info) -> ResponseOrderInfoModel`.
- Constructor accepts a `cardinal_factory` to avoid real 3DS calls in tests.

- [ ] **Step 1: Write failing NO_PAY/payment tests**

```python
def test_pay_order_submits_payment_once_and_writes_ticket_numbers():
    service = payment_service()
    result = service.pay_order("ABC123", PASSENGERS, CONTACT, CARD)
    assert service.script.payment_action_names == ["load", "tdsinit", "add"]
    assert service.script.payment_record_calls == 1
    assert result.order_state == OrderStateEnum.OPEN_FOR_USE
    assert result.passengers[0].ticket_number == "1234567890123"

def test_payment_failure_is_not_retried():
    service = failing_payment_service()
    with pytest.raises(ServiceError):
        service.pay_order("ABC123", PASSENGERS, CONTACT, CARD)
    assert service.script.add_payment_calls == 1
```

- [ ] **Step 2: Verify RED**

Run the payment test file; expect missing `pay_order`.

- [ ] **Step 3: Implement payment once-only flow**

Select `CheckoutFormPayment`, execute `load`, `tdsinit`, create `CardinalcommerceUtil(proxy, Config.USER_AGENT)`, initialize JWT and save browser data, execute one `add`, execute one payment-record query, then poll itinerary at most five times for tickets. Accept Visa and Mastercard card types and reject all others before submitting.

- [ ] **Step 4: Verify GREEN and commit**

Run payment and core Service tests; expect all pass; commit with `feat(9gweb): add optional Web payment`.

### Task 5: Search and Single-PNR Sham Tasks

**Files:**
- Create: `task/9Gweb/__init__.py`
- Create: `task/9Gweb/search.py`
- Create: `task/9Gweb/sham_booking.py`
- Test: `tests/flight_9gweb/test_search_task.py`
- Test: `tests/flight_9gweb/test_sham_booking_task.py`

**Interfaces:**
- Produces: discoverable `task.9Gweb.search.main` and `task.9Gweb.sham_booking.main`.
- Produces: `_run_sham_booking(service, request, response) -> ResponseOrderInfoModel`.

- [ ] **Step 1: Write failing adapter/orchestration tests**

```python
def test_sham_searches_one_then_five_and_purchases_once():
    service = FakeService(first_seats=8, second_seats=5)
    result = _run_sham_booking(service, REQUEST, ResponseOrderInfoModel())
    assert service.search_counts == [1, 5]
    assert service.create_calls == 1
    assert result.order_state == OrderStateEnum.HOLD
```

Also assert registry discovery, date normalization, product selection, zero seats, second-search seat decline, and complete guarded local examples.

- [ ] **Step 2: Verify RED**

Run both task test files; expect missing `task.9Gweb` modules.

- [ ] **Step 3: Implement task adapters**

Search uses short `MachineCache` reuse and re-authenticates for currency changes. Sham uses `MAX_SEAT_COUNT = 5`, two live searches, current fake passengers/contact, one `create_order`, and maps one HOLD response. Add complete placeholder-only `__main__` payloads.

- [ ] **Step 4: Verify GREEN and commit**

Run task tests and all `tests/flight_9gweb`; expect all pass; commit with `feat(9gweb): add search and single PNR sham tasks`.

### Task 6: Booking and Order-Detail Tasks

**Files:**
- Create: `task/9Gweb/booking.py`
- Create: `task/9Gweb/order_detail.py`
- Test: `tests/flight_9gweb/test_booking_task.py`
- Test: `tests/flight_9gweb/test_order_detail_task.py`

**Interfaces:**
- Produces: discoverable `booking` and `orderDetail` task modules.

- [ ] **Step 1: Write failing booking/detail tests**

```python
def test_booking_no_pay_returns_hold_without_payment():
    result = _run_booking(service, REQUEST_NO_PAY, ResponseOrderInfoModel())
    assert result.order_state == OrderStateEnum.HOLD
    assert service.pay_calls == 0

def test_order_detail_delegates_pnr_and_last_name():
    assert _run_order_detail(service, DETAIL_REQUEST).pnr == "ABC123"
    service.order_detail.assert_called_once_with("ABC123", "LOVELACE")
```

Also test paid booking delegates once, time/product/seat validation, price threshold, registry discovery, and guarded local examples.

- [ ] **Step 2: Verify RED**

Run both files; expect missing task modules.

- [ ] **Step 3: Implement task adapters**

Booking performs search, `FlightUtil` number/time/product/price checks before creating the order, adds requested baggage, maps HOLD response, and calls `pay_order` only when type is not `NO_PAY`. Detail initializes a fresh service and delegates PNR/last name. Add placeholder-only local examples.

- [ ] **Step 4: Verify GREEN and commit**

Run focused and all 9G Web tests; expect pass; commit with `feat(9gweb): add booking and order detail tasks`.

### Task 7: Worker Packaging and Final Verification

**Files:**
- Create: `flights/sunphuquocairways_9g/Dockerfile.web`
- Create: `flights/sunphuquocairways_9g/start-web.sh`
- Test: `tests/flight_9gweb/test_worker.py`

**Interfaces:**
- Produces: Python 3.13 worker supporting `9GWEB-search`, `9GWEB-verify`, `9GWEB-shamBooking`, `9GWEB-booking`, and `9GWEB-orderDetail`.

- [ ] **Step 1: Write failing worker test**

Read the launcher and assert all four module paths and five queue suffixes exist. Run it and verify failure because files are absent.

- [ ] **Step 2: Implement packaging**

Follow the existing 9G App Python 3.13 Docker conventions, copy `task/9Gweb`, use `requirements-py313.txt`, and route each `TASK_TYPE` to the correct Celery module and `9GWEB-*` queue.

- [ ] **Step 3: Run full verification**

```bash
bash -n flights/sunphuquocairways_9g/start-web.sh
PYTHONPATH=. /Users/a1234/Desktop/rakdFlightLocalShamBooking/.venv/bin/python -m compileall -q flights/sunphuquocairways_9g task/9Gweb tests/flight_9gweb
PYTHONPATH=. /Users/a1234/Desktop/rakdFlightLocalShamBooking/.venv/bin/pytest tests/flight_9gweb tests/flight_9gapp -q
PYTHONPATH=. /Users/a1234/Desktop/rakdFlightLocalShamBooking/.venv/bin/pytest -q
```

Expected: all tests pass.

- [ ] **Step 4: Audit boundaries and commit**

```bash
rg -n "common\.models|CurlHttpUtil|InventoryBooking|redis" flights/sunphuquocairways_9g/{script/web_script.py,service/web_service.py,flight_common/web_*.py} task/9Gweb
git diff --check
```

Expected: no forbidden dependency matches and no whitespace errors. Commit packaging and worker test with `build(9gweb): add worker packaging`.
