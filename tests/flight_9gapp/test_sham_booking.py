import importlib
from datetime import datetime
from decimal import Decimal

import pytest

from app.source_registry import module_for_source
from common.enums.freight_rate_type_enum import FreightRateTypeEnum
from common.enums.order_state_enum import OrderStateEnum
from common.errors.service_error import ServiceError, ServiceStateEnum
from common.model.flight.flight_bundle_model import FlightBundleModel
from common.model.flight.flight_bundle_price_model import FlightBundlePriceModel
from common.model.flight.flight_journey_model import FlightJourneyModel
from common.model.flight.flight_segment_model import FlightSegmentModel
from common.model.flight.flight_ssr_info_model import FlightSsrInfoModel
from common.model.task.request_sham_booking_task_data_model import RequestShamBookingTaskDataModel
from common.model.task.response_order_info_model import ResponseOrderInfoModel

sham_module = importlib.import_module("task.9Gapp.sham_booking")
_run_sham_booking = sham_module._run_sham_booking
_select_bundle = sham_module._select_bundle


def make_bundle(seat: int, cabin: str = "Y", product_tag: str = "ECONOMY LITE") -> FlightBundleModel:
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
        cabin=cabin,
        fareKey="trip-1",
        productTag=product_tag,
        seat=seat,
        freightRateType=FreightRateTypeEnum.PT,
    )


def make_journey(seat: int, flight_number: str = "9G0123") -> FlightJourneyModel:
    segment = FlightSegmentModel(
        segmentKey="flight-1",
        depAirport="SGN",
        arrAirport="PQC",
        depTime=datetime(2026, 8, 1, 8, 0),
        arrTime=datetime(2026, 8, 1, 9, 0),
        flightNumber=flight_number,
        carrier="9G",
        operatingCarrier="9G",
        operatingFlightNumber=flight_number,
        routeIndex=1,
        legIndex=1,
    )
    return FlightJourneyModel(
        journeyKey="journey-1",
        segments=[segment],
        bundles=[make_bundle(seat)],
        depAirport="SGN",
        arrAirport="PQC",
        depTime=segment.dep_time,
        arrTime=segment.arr_time,
    )


REQUEST = RequestShamBookingTaskDataModel(
    depAirport="SGN",
    arrAirport="PQC",
    depDate="20260801",
    flightNumber="9G0123",
    cabin="Y",
    bookingConfig={"bookRate": 10, "currencyCode": "VND"},
    ext={"productTag": "ECONOMY LITE"},
)


class FakeService:
    def __init__(self, first_seats=8, second_seats=5, flight_number="9G0123"):
        self.responses = [make_journey(first_seats, flight_number), make_journey(second_seats, flight_number)]
        self.search_adult_counts = []
        self.create_calls = 0
        self.created_passengers = None

    def search(self, **kwargs):
        self.search_adult_counts.append(kwargs["adt_number"])
        return [self.responses.pop(0)]

    def create_and_hold(self, bundle, passengers, contact_info, currency_code):
        self.create_calls += 1
        self.created_passengers = passengers
        return "booking-1", "ABC123"


def test_registry_discovers_9gapp_sham_booking():
    assert module_for_source("9GAPP", "shamBooking") == "task.9Gapp.sham_booking"


def test_select_bundle_matches_cabin_and_product():
    journey = make_journey(5)
    journey.bundles.append(make_bundle(5, cabin="C", product_tag="BUSINESS PRIME"))

    selected = _select_bundle(journey, "Y", "ECONOMY LITE")

    assert selected.cabin == "Y"
    assert selected.product_tag == "ECONOMY LITE"


def test_select_bundle_rejects_missing_product():
    with pytest.raises(ServiceError) as error:
        _select_bundle(make_journey(5), "Y", "BUSINESS PRIME")

    assert error.value.code == ServiceStateEnum.NO_AVAILABLE_BUNDLE.name


def test_sham_booking_searches_twice_and_creates_one_pnr():
    service = FakeService(first_seats=8, second_seats=5)

    response = _run_sham_booking(service, REQUEST, ResponseOrderInfoModel())

    assert service.search_adult_counts == [1, 5]
    assert service.create_calls == 1
    assert response.order_number == "booking-1"
    assert response.pnr == "ABC123"
    assert len(response.passengers) == 5
    assert response.total_amount == Decimal("550")
    assert response.order_state == OrderStateEnum.HOLD
    assert response.journeys[0].bundles[0].seat == 5


def test_sham_booking_does_not_create_when_second_search_has_fewer_seats():
    service = FakeService(first_seats=5, second_seats=3)

    with pytest.raises(ServiceError) as error:
        _run_sham_booking(service, REQUEST, ResponseOrderInfoModel())

    assert error.value.code == ServiceStateEnum.BUSINESS_ERROR.name
    assert service.create_calls == 0


def test_sham_booking_rejects_zero_seats_without_second_search():
    service = FakeService(first_seats=0, second_seats=0)

    with pytest.raises(ServiceError) as error:
        _run_sham_booking(service, REQUEST, ResponseOrderInfoModel())

    assert error.value.code == ServiceStateEnum.NO_AVAILABLE_CABIN.name
    assert service.search_adult_counts == [1]
    assert service.create_calls == 0


def test_sham_booking_rejects_non_matching_flight():
    service = FakeService(flight_number="9G0999")

    with pytest.raises(ServiceError) as error:
        _run_sham_booking(service, REQUEST, ResponseOrderInfoModel())

    assert error.value.code == ServiceStateEnum.NO_AVAILABLE_FLIGHT_NUMBER.name
    assert service.create_calls == 0
