import ast
import importlib
from decimal import Decimal
from pathlib import Path

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
from flights.sunphuquocairways_9g.service.web_service import BookingResult


module = importlib.import_module("task.9Gweb.sham_booking")


def journey(seats):
    bundle = FlightBundleModel(
        priceInfo=FlightBundlePriceModel(
            adultTicketPrice=Decimal("1000000"),
            adultTaxPrice=Decimal("250000"),
            childTicketPrice=Decimal("0"),
            childTaxPrice=Decimal("0"),
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
    return FlightJourneyModel(
        journeyKey="bound-1",
        segments=[segment],
        bundles=[bundle],
        depAirport="SGN",
        arrAirport="PQC",
        depTime=segment.dep_time,
        arrTime=segment.arr_time,
    )


class FakeService:
    def __init__(self, first_seats=8, second_seats=5):
        self.seats = [first_seats, second_seats]
        self.search_counts = []
        self.create_calls = 0

    def search(self, **kwargs):
        self.search_counts.append(kwargs["adt_number"])
        return [journey(self.seats[len(self.search_counts) - 1])]

    def create_order(self, bundle, passengers, contact_info):
        self.create_calls += 1
        return BookingResult(
            pnr="ABC123",
            bundle=bundle,
            passengers=passengers,
            contact_info=contact_info,
            total_amount=Decimal("6250000"),
            currency="VND",
        )


def request(**changes):
    data = {
        "depAirport": "SGN",
        "arrAirport": "PQC",
        "depDate": "20260801",
        "flightNumber": "9G0123",
        "cabin": "Y",
        "bookingConfig": {"bookRate": 10, "currencyCode": "VND"},
        "ext": {"productTag": "ECONOMY LITE"},
    }
    data.update(changes)
    return RequestShamBookingTaskDataModel.model_validate(data)


def test_sham_searches_one_then_five_and_purchases_once():
    service = FakeService()

    result = module._run_sham_booking(service, request(), ResponseOrderInfoModel())

    assert service.search_counts == [1, 5]
    assert service.create_calls == 1
    assert result.pnr == "ABC123"
    assert "|" not in result.pnr
    assert result.order_state == OrderStateEnum.HOLD
    assert len(result.passengers) == 5
    assert result.total_amount == Decimal("6250000")
    assert result.journeys[0].bundles[0].product_tag == "ECONOMY LITE"


def test_sham_rejects_second_search_seat_decline_without_purchase():
    service = FakeService(first_seats=8, second_seats=4)

    with pytest.raises(ServiceError) as error:
        module._run_sham_booking(service, request(), ResponseOrderInfoModel())

    assert error.value.code == ServiceStateEnum.BUSINESS_ERROR.name
    assert service.create_calls == 0


def test_sham_rejects_zero_seats_and_wrong_product():
    with pytest.raises(ServiceError):
        module._run_sham_booking(FakeService(first_seats=0), request(), ResponseOrderInfoModel())
    with pytest.raises(ServiceError):
        module._run_sham_booking(
            FakeService(),
            request(ext={"productTag": "BUSINESS PRIME"}),
            ResponseOrderInfoModel(),
        )


def test_registry_and_guarded_local_example():
    assert module_for_source("9GWEB", "shamBooking") == "task.9Gweb.sham_booking"
    source = Path(module.__file__).read_text()
    tree = ast.parse(source)
    assert any(
        isinstance(node, ast.If)
        and isinstance(node.test, ast.Compare)
        and isinstance(node.test.left, ast.Name)
        and node.test.left.id == "__name__"
        for node in tree.body
    )
