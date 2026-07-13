from copy import deepcopy
from decimal import Decimal

import pytest

from common.errors.service_error import ServiceError, ServiceStateEnum
from flights.sunphuquocairways_9g.config import Config
from flights.sunphuquocairways_9g.flight_common.web_flight_parser import WebFlightParser


WEB_SEARCH_RESPONSE = {
    "data": {
        "airBoundGroups": [
            {
                "boundDetails": {"segments": [{"flightId": "flight-1"}]},
                "airBounds": [
                    {
                        "airBoundId": "bound-1",
                        "fareFamilyCode": "EL1",
                        "status": {"value": "available"},
                        "availabilityDetails": [{"bookingClass": "Y", "cabin": "eco", "quota": 4}],
                        "prices": {
                            "unitPrices": [
                                {
                                    "travelerIds": ["ADT-1"],
                                    "prices": [{"base": 1000000, "totalTaxes": 100000, "currencyCode": "VND"}],
                                },
                                {
                                    "travelerIds": ["CHD-1"],
                                    "prices": [{"base": 800000, "totalTaxes": 80000, "currencyCode": "VND"}],
                                },
                            ]
                        },
                    }
                ],
            }
        ]
    },
    "dictionaries": {
        "currency": {"VND": {"decimalPlaces": 0}},
        "flight": {
            "flight-1": {
                "marketingAirlineCode": "9G",
                "marketingFlightNumber": "123",
                "operatingAirlineCode": "9G",
                "operatingFlightNumber": "123",
                "aircraftCode": "320",
                "departure": {"locationCode": "SGN", "dateTime": "2026-08-01T08:00:00+07:00", "terminal": "1"},
                "arrival": {"locationCode": "PQC", "dateTime": "2026-08-01T09:00:00+07:00", "terminal": "1"},
                "duration": 3600,
            }
        },
        "fareFamilyWithServices": {},
    },
}


def test_web_currency_context_maps_cny_and_returns_copy():
    context = Config.web_currency_context("cny")
    assert context["country_code"] == "CN"
    context["country_code"] = "changed"
    assert Config.web_currency_context("CNY")["country_code"] == "CN"


def test_web_currency_context_rejects_unknown_currency():
    with pytest.raises(ServiceError) as error:
        Config.web_currency_context("EUR")
    assert error.value.code == ServiceStateEnum.DATA_VALIDATION_FAILED.name


def test_parser_maps_web_bundle_to_current_model():
    journey = WebFlightParser.parse(WEB_SEARCH_RESPONSE, child_count=1, promo_code="SAVE")[0]

    assert journey.journey_key == "bound-1"
    assert journey.segments[0].flight_number == "9G0123"
    assert journey.segments[0].route_index == 1
    bundle = journey.bundles[0]
    assert bundle.fare_key == "bound-1"
    assert bundle.product_tag == "ECONOMY LITE"
    assert bundle.cabin == "Y"
    assert bundle.seat == 4
    assert bundle.price_info.adult_ticket_price == Decimal("1000000")
    assert bundle.price_info.adult_tax_price == Decimal("100000")
    assert bundle.price_info.child_ticket_price == Decimal("800000")
    assert bundle.price_info.currency == "VND"
    assert [item.weight for item in bundle.ssr_info.baggage] == [23, 7]
    assert bundle.ext["promoCode"] == "SAVE"


def test_parser_uses_minor_unit_decimal_places():
    response = deepcopy(WEB_SEARCH_RESPONSE)
    response["dictionaries"]["currency"] = {"USD": {"decimalPlaces": 2}}
    price = response["data"]["airBoundGroups"][0]["airBounds"][0]["prices"]["unitPrices"][0]["prices"][0]
    price.update(base=12345, totalTaxes=678, currencyCode="USD")

    bundle = WebFlightParser.parse(response)[0].bundles[0]

    assert bundle.price_info.adult_ticket_price == Decimal("123.45")
    assert bundle.price_info.adult_tax_price == Decimal("6.78")


def test_parser_filters_sold_out_and_missing_flights():
    sold_out = deepcopy(WEB_SEARCH_RESPONSE)
    sold_out["data"]["airBoundGroups"][0]["airBounds"][0]["status"]["value"] = "soldOut"
    assert WebFlightParser.parse(sold_out) == []

    missing = deepcopy(WEB_SEARCH_RESPONSE)
    missing["dictionaries"]["flight"] = {}
    assert WebFlightParser.parse(missing) == []
