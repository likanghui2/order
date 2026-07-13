from copy import deepcopy
from decimal import Decimal

import pytest

from common.errors.service_error import ServiceError, ServiceStateEnum
from flights.sunphuquocairways_9g.config import Config
from flights.sunphuquocairways_9g.flight_common.app_flight_parser import AppFlightParser


SEARCH_RESPONSE = {
    "success": True,
    "data": {
        "list_trip": [
            {
                "trip_id": "journey-id",
                "list_itinerary": [
                    {
                        "flight_id": "flight-id",
                        "flight_number": "123",
                        "departure_info": {"code": "SGN", "datetime": "2026-08-01T08:00:00+07:00"},
                        "arrival_info": {"code": "PQC", "datetime": "2026-08-01T09:00:00+07:00"},
                        "duration": 3600,
                    }
                ],
                "booking_class": [
                    {
                        "trip_id": "outbound-trip-id",
                        "fare_family_code": "EL1",
                        "booking_class": "Y",
                        "booking_status": "available",
                        "available_count": 4,
                        "segment_fare": [{"cabin": "economy", "fare_basis": "YLOW"}],
                        "pricing": {
                            "pax_pricing": [
                                {
                                    "passenger_type": "ADT",
                                    "base_fare": 1000000,
                                    "tax": 100000,
                                    "currency": "VND",
                                },
                                {
                                    "passenger_type": "CHD",
                                    "base_fare": 800000,
                                    "tax": 80000,
                                    "currency": "VND",
                                },
                            ]
                        },
                    }
                ],
            }
        ]
    },
}


def test_parse_search_response_to_current_models():
    journeys = AppFlightParser.parse(SEARCH_RESPONSE, child_count=1, promo_code="SAVE")

    journey = journeys[0]
    assert journey.journey_key == "journey-id"
    assert journey.dep_airport == "SGN"
    assert journey.arr_airport == "PQC"
    assert [segment.flight_number for segment in journey.segments] == ["9G0123"]
    assert journey.segments[0].route_index == 1

    bundle = journey.bundles[0]
    assert bundle.fare_key == "outbound-trip-id"
    assert bundle.cabin == "Y"
    assert bundle.product_tag == "ECONOMY LITE"
    assert bundle.seat == 4
    assert bundle.price_info.adult_ticket_price == Decimal("1000000")
    assert bundle.price_info.adult_tax_price == Decimal("100000")
    assert bundle.price_info.child_ticket_price == Decimal("800000")
    assert bundle.price_info.child_tax_price == Decimal("80000")
    assert bundle.ext["fareFamilyCode"] == "EL1"
    assert bundle.ext["promoCode"] == "SAVE"


def test_parse_filters_sold_out_bundle_and_empty_journey():
    response = deepcopy(SEARCH_RESPONSE)
    response["data"]["list_trip"][0]["booking_class"][0]["booking_status"] = "soldOut"

    assert AppFlightParser.parse(response) == []


def test_parse_uses_lowest_segment_availability_and_default_nine():
    response = deepcopy(SEARCH_RESPONSE)
    booking_class = response["data"]["list_trip"][0]["booking_class"][0]
    booking_class.pop("available_count")
    booking_class["segment_fare"] = [
        {"cabin": "economy", "seat_availablity": 7},
        {"cabin": "economy", "seat_availability": 3},
    ]
    assert AppFlightParser.parse(response)[0].bundles[0].seat == 3

    booking_class["segment_fare"] = [{"cabin": "economy"}]
    assert AppFlightParser.parse(response)[0].bundles[0].seat == 9


def test_parse_builds_stable_journey_key_from_segments():
    response = deepcopy(SEARCH_RESPONSE)
    trip = response["data"]["list_trip"][0]
    trip.pop("trip_id")

    journey = AppFlightParser.parse(response)[0]

    assert journey.journey_key == "flight-id"
    assert journey.segments[0].segment_key == "flight-id"


def test_currency_context_returns_copy_and_rejects_unsupported_currency():
    context = Config.currency_context("vnd")
    context["office_id"] = "changed"
    assert Config.currency_context("VND")["office_id"] == "HAN9G08MB"

    with pytest.raises(ServiceError) as error:
        Config.currency_context("CNY")
    assert error.value.code == ServiceStateEnum.DATA_VALIDATION_FAILED.name
