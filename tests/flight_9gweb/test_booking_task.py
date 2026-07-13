import ast
import importlib
from decimal import Decimal
from pathlib import Path

import pytest

from app.source_registry import module_for_source
from common.enums.freight_rate_type_enum import FreightRateTypeEnum
from common.enums.gender_enum import GenderEnum
from common.enums.order_state_enum import OrderStateEnum
from common.enums.passenger_type_enum import PassengerTypeEnum
from common.errors.service_error import ServiceError
from common.model.flight.flight_bundle_model import FlightBundleModel
from common.model.flight.flight_bundle_price_model import FlightBundlePriceModel
from common.model.flight.flight_journey_model import FlightJourneyModel
from common.model.flight.flight_segment_model import FlightSegmentModel
from common.model.flight.flight_ssr_info_model import FlightSsrInfoModel
from common.model.order.contact_info_model import ContactInfoModel
from common.model.order.passenger_info_model import PassengerInfoModel
from common.model.task.request_booking_task_data_model import RequestBookingTaskDataModel
from common.model.task.response_order_info_model import ResponseOrderInfoModel
from flights.sunphuquocairways_9g.service.web_service import BookingResult


module = importlib.import_module("task.9Gweb.booking")


def flight(seats=2):
    segment = FlightSegmentModel(
        segmentKey="flight-1",
        depAirport="SGN",
        arrAirport="PQC",
        depTime="2026-08-01T08:00:00+07:00",
        arrTime="2026-08-01T09:00:00+07:00",
        flightNumber="9G0123",
        carrier="9G",
        operatingCarrier="9G",
        operatingFlightNumber="9G0123",
        routeIndex=1,
        legIndex=1,
    )
    bundle = FlightBundleModel(
        priceInfo=FlightBundlePriceModel(
            adultTicketPrice=Decimal("1000000"),
            adultTaxPrice=Decimal("250000"),
            childTicketPrice=Decimal("800000"),
            childTaxPrice=Decimal("200000"),
            currency="VND",
        ),
        ssrInfo=FlightSsrInfoModel(baggage=[]),
        code="EL1",
        cabinLevel="Y",
        cabin="Y",
        fareKey="bound-1",
        productTag="ECONOMY LITE",
        seat=seats,
        freightRateType=FreightRateTypeEnum.PT,
    )
    return FlightJourneyModel(
        journeyKey="bound-1",
        segments=[segment],
        bundles=[bundle],
        depAirport="SGN",
        arrAirport="PQC",
        depTime=segment.dep_time,
        arrTime=segment.arr_time,
    )


PASSENGER = PassengerInfoModel(
    type=PassengerTypeEnum.ADT,
    lastName="LOVELACE",
    firstName="ADA",
    gender=GenderEnum.F,
    birthday="1990-01-01",
)
CONTACT = ContactInfoModel(
    lastName="LOVELACE",
    firstName="ADA",
    emailAddress="ada@example.com",
    phoneCode="+84",
    phoneNumber="901234567",
)


def request(payment_type="NO_PAY", **changes):
    data = {
        "depAirport": "SGN",
        "arrAirport": "PQC",
        "depTime": "202608010800",
        "arrTime": "202608010900",
        "flightNumber": "9G0123",
        "productTag": "ECONOMY LITE",
        "promoCode": "",
        "ticketConfig": {
            "currencyCode": "VND",
            "isForceIssue": False,
            "priceThreshold": "1300000",
        },
        "freightRateType": "PT",
        "passengers": [PASSENGER.model_dump(by_alias=True, exclude_none=True)],
        "contactInfo": CONTACT.model_dump(by_alias=True),
        "paymentInfo": {
            "type": payment_type,
            "cardNumber": "4111111111111111",
            "cardExpiryDate": "08/29",
            "cardHolderName": "ADA LOVELACE",
            "cardType": "VI",
            "cardCVV": "123",
        },
        "ext": {},
    }
    data.update(changes)
    return RequestBookingTaskDataModel.model_validate(data)


class FakeService:
    def __init__(self, seats=2):
        self.journey = flight(seats)
        self.search_calls = []
        self.create_calls = 0
        self.baggage_calls = 0
        self.pay_calls = 0

    def search(self, **kwargs):
        self.search_calls.append(kwargs)
        return [self.journey]

    def create_order(self, bundle, passengers, contact_info):
        self.create_calls += 1
        passengers[0].ext["travelerId"] = "traveler-1"
        return BookingResult(
            pnr="ABC123",
            bundle=bundle,
            passengers=passengers,
            contact_info=contact_info,
            total_amount=Decimal("1250000"),
            currency="VND",
        )

    def add_requested_baggage(self, pnr, passengers, last_name):
        self.baggage_calls += 1

    def pay_order(self, pnr, passengers, contact_info, payment_info):
        self.pay_calls += 1
        paid = ResponseOrderInfoModel(
            pnr=pnr,
            orderState=OrderStateEnum.OPEN_FOR_USE,
            passengers=[passengers[0].model_copy(update={"ticket_number": "1234567890123"})],
        )
        return paid


def test_no_pay_booking_creates_one_pnr_and_returns_hold():
    service = FakeService()

    result = module._run_booking(service, request(), ResponseOrderInfoModel())

    assert service.create_calls == 1
    assert service.baggage_calls == 1
    assert service.pay_calls == 0
    assert result.pnr == "ABC123"
    assert result.order_state == OrderStateEnum.HOLD
    assert result.total_amount == Decimal("1250000")
    assert result.journeys[0].bundles[0].product_tag == "ECONOMY LITE"
    assert service.search_calls[0]["dep_date"] == "2026-08-01T00:00:00"


def test_card_booking_pays_once_and_returns_open_for_use():
    service = FakeService()

    result = module._run_booking(service, request("CARD"), ResponseOrderInfoModel())

    assert service.create_calls == 1
    assert service.pay_calls == 1
    assert result.order_state == OrderStateEnum.OPEN_FOR_USE
    assert result.passengers[0].ticket_number == "1234567890123"


def test_booking_validates_seats_before_creating_order():
    service = FakeService(seats=0)

    with pytest.raises(ServiceError):
        module._run_booking(service, request(), ResponseOrderInfoModel())

    assert service.create_calls == 0


def test_booking_registry_and_guarded_local_example():
    assert module_for_source("9GWEB", "booking") == "task.9Gweb.booking"
    tree = ast.parse(Path(module.__file__).read_text())
    assert any(
        isinstance(node, ast.If)
        and isinstance(node.test, ast.Compare)
        and isinstance(node.test.left, ast.Name)
        and node.test.left.id == "__name__"
        for node in tree.body
    )
