from decimal import Decimal

import pytest

from common.enums.freight_rate_type_enum import FreightRateTypeEnum
from common.enums.gender_enum import GenderEnum
from common.enums.passenger_type_enum import PassengerTypeEnum
from common.errors.service_error import ServiceError, ServiceStateEnum
from common.model.flight.flight_bundle_model import FlightBundleModel
from common.model.flight.flight_bundle_price_model import FlightBundlePriceModel
from common.model.flight.flight_ssr_info_model import FlightSsrInfoModel
from common.model.order.contact_info_model import ContactInfoModel
from common.model.order.passenger_info_model import PassengerInfoModel
from flights.sunphuquocairways_9g.service.app_service import AppService


def bundle(fare_key="trip-1"):
    return FlightBundleModel(
        priceInfo=FlightBundlePriceModel(
            adultTicketPrice=Decimal("100"),
            adultTaxPrice=Decimal("10"),
            childTicketPrice=Decimal("80"),
            childTaxPrice=Decimal("8"),
            currency="VND",
        ),
        ssrInfo=FlightSsrInfoModel(baggage=[]),
        code="EL1",
        cabinLevel="Y",
        cabin="Y",
        fareKey=fare_key,
        productTag="ECONOMY LITE",
        seat=5,
        freightRateType=FreightRateTypeEnum.PT,
    )


PASSENGERS = [
    PassengerInfoModel(
        type=PassengerTypeEnum.ADT,
        lastName="LOVELACE",
        firstName="ADA",
        gender=GenderEnum.F,
        birthday="1990-01-02",
    )
]
CONTACT = ContactInfoModel(
    lastName="LOVELACE",
    firstName="ADA",
    emailAddress="ada@example.com",
    phoneCode="84",
    phoneNumber="901234567",
)


class FakeScript:
    def __init__(self, create_response=None, hold_response=None, search_response=None):
        self.create_response = create_response or {"data": {"booking_id": "booking-1"}}
        self.hold_response = hold_response or {"data": {"pnr_number": "ABC123"}}
        self.search_response = search_response
        self.create_calls = 0
        self.hold_calls = 0
        self.passenger_list = None
        self.contact_list = None
        self.trace_id = None

    def initialize_session(self):
        pass

    def search(self, **kwargs):
        return self.search_response

    def create_order(self, trip_ids, passenger_list, contact_list, **kwargs):
        self.create_calls += 1
        self.passenger_list = passenger_list
        self.contact_list = contact_list
        self.trace_id = "claimed-trace"
        return self.create_response

    def hold_booking(self, booking_id, **kwargs):
        self.hold_calls += 1
        return self.hold_response


def test_create_and_hold_sends_current_passengers_and_returns_pnr():
    script = FakeScript()
    service = AppService(None, script=script)

    booking_id, pnr = service.create_and_hold(bundle(), PASSENGERS, CONTACT, "VND")

    assert (booking_id, pnr) == ("booking-1", "ABC123")
    assert script.create_calls == 1
    assert script.hold_calls == 1
    assert script.passenger_list[0]["first_name"] == "ADA"
    assert script.passenger_list[0]["title"] == "Mrs"
    assert script.contact_list[0]["email"] == CONTACT.email_address
    assert script.contact_list[1]["dial_code"] == "84"
    assert script.trace_id is None


@pytest.mark.parametrize(
    ("create_response", "hold_response", "missing_field"),
    [
        ({"data": {}}, {"data": {"pnr_number": "ABC123"}}, "booking_id"),
        ({"data": {"booking_id": "booking-1"}}, {"data": {}}, "pnr_number"),
    ],
)
def test_create_and_hold_rejects_missing_required_data(create_response, hold_response, missing_field):
    script = FakeScript(create_response, hold_response)
    service = AppService(None, script=script)

    with pytest.raises(ServiceError) as error:
        service.create_and_hold(bundle(), PASSENGERS, CONTACT, "VND")

    assert error.value.code == ServiceStateEnum.DATA_VALIDATION_FAILED.name
    assert missing_field in error.value.message
    assert script.trace_id is None


def test_create_and_hold_rejects_missing_fare_key_before_creating_order():
    script = FakeScript()
    service = AppService(None, script=script)

    with pytest.raises(ServiceError):
        service.create_and_hold(bundle(fare_key=None), PASSENGERS, CONTACT, "VND")

    assert script.create_calls == 0


def test_search_builds_routes_and_uses_current_parser(monkeypatch):
    script = FakeScript(search_response={"data": {"list_trip": []}})
    service = AppService(None, script=script)
    captured = {}

    def fake_parse(response_data, child_count, promo_code):
        captured.update(response=response_data, child_count=child_count, promo_code=promo_code)
        return ["journey"]

    monkeypatch.setattr(
        "flights.sunphuquocairways_9g.service.app_service.AppFlightParser.parse",
        fake_parse,
    )

    result = service.search(
        "SGN",
        "PQC",
        "2026-08-01T00:00:00.000",
        2,
        1,
        "VND",
        ret_date="2026-08-04T00:00:00.000",
        promo_code="SAVE",
    )

    assert result == ["journey"]
    assert captured["child_count"] == 1
    assert captured["promo_code"] == "SAVE"
