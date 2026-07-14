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
    ext={"passengerCount": 3, "productTag": "DO NOT MATCH"},
)


class FakeService:
    def __init__(self, seats=5, flight_number="9G0123"):
        self.journey = make_journey(seats, flight_number)
        self.search_adult_counts = []
        self.create_calls = 0
        self.created_passengers = None
        self.created_bundle = None

    def initialize_session(self):
        pass

    def search(self, **kwargs):
        self.search_adult_counts.append(kwargs["adt_number"])
        return [self.journey]

    def create_and_hold(self, bundle, passengers, contact_info, currency_code):
        self.create_calls += 1
        self.created_passengers = passengers
        self.created_bundle = bundle
        return "booking-1", "ABC123"


def test_registry_discovers_9gapp_sham_booking():
    assert module_for_source("9GAPP", "shamBooking") == "task.9Gapp.sham_booking"


def run_main(monkeypatch, service, request=REQUEST):
    monkeypatch.setattr(sham_module, "AppService", lambda proxy: service)
    monkeypatch.setattr(sham_module, "proxy_info_from_ext", lambda ext: "proxy")
    return sham_module.main.run.__wrapped__(None, request, ResponseOrderInfoModel())


def test_sham_booking_searches_once_for_requested_passenger_count_and_creates_one_pnr(monkeypatch):
    service = FakeService(seats=5)

    response = run_main(monkeypatch, service)

    assert service.search_adult_counts == [3]
    assert service.create_calls == 1
    assert response.order_number == "booking-1"
    assert response.pnr == "ABC123"
    assert len(response.passengers) == 3
    assert response.total_amount == Decimal("330")
    assert response.order_state == OrderStateEnum.HOLD
    assert response.journeys[0].bundles[0].seat == 5
    assert service.created_bundle.product_tag == "ECONOMY LITE"


def test_sham_booking_does_not_create_when_bundle_has_fewer_seats(monkeypatch):
    service = FakeService(seats=2)

    with pytest.raises(ServiceError) as error:
        run_main(monkeypatch, service)

    assert error.value.code == ServiceStateEnum.BUSINESS_ERROR.name
    assert service.create_calls == 0


def test_sham_booking_rejects_zero_seats(monkeypatch):
    service = FakeService(seats=0)

    with pytest.raises(ServiceError) as error:
        run_main(monkeypatch, service)

    assert error.value.code == ServiceStateEnum.NO_AVAILABLE_CABIN.name
    assert service.search_adult_counts == [3]
    assert service.create_calls == 0


def test_sham_booking_rejects_non_matching_flight(monkeypatch):
    service = FakeService(flight_number="9G0999")

    with pytest.raises(ServiceError) as error:
        run_main(monkeypatch, service)

    assert error.value.code == ServiceStateEnum.NO_AVAILABLE_FLIGHT_NUMBER.name
    assert service.create_calls == 0


def test_sham_booking_defaults_to_one_passenger(monkeypatch):
    service = FakeService(seats=5)
    request = REQUEST.model_copy(update={"ext": {}})

    response = run_main(monkeypatch, service, request)

    assert service.search_adult_counts == [1]
    assert len(response.passengers) == 1
