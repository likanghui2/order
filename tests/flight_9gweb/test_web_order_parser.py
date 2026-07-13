from decimal import Decimal

import pytest

from common.enums.order_state_enum import OrderStateEnum
from common.enums.ssr_type_enum import SsrTypeEnum
from common.errors.service_error import ServiceError, ServiceStateEnum
from flights.sunphuquocairways_9g.flight_common.web_order_parser import WebOrderParser


def itinerary(ticket_status="ISSUED", order_status="CONFIRMED"):
    documents = []
    if ticket_status:
        documents.append(
            {
                "id": "1234567890123",
                "documentType": "eticket",
                "status": ticket_status,
                "travelerIds": ["traveler-1"],
            }
        )
    return {
        "data": {
            "id": "ABC123",
            "status": order_status,
            "travelers": [
                {
                    "id": "traveler-1",
                    "passengerTypeCode": "ADT",
                    "dateOfBirth": "1990-01-01",
                    "names": [{"title": "MR", "firstName": "ADA", "lastName": "LOVELACE"}],
                }
            ],
            "contacts": [
                {"contactType": "Email", "address": "ada@example.com"},
                {
                    "contactType": "Phone",
                    "countryPhoneExtension": "+84",
                    "number": "901234567",
                },
            ],
            "travelDocuments": documents,
            "paymentRecords": [
                {"paymentTransactions": [{"amount": {"value": 1250000, "currencyCode": "VND"}}]}
            ],
            "air": {
                "bounds": [
                    {
                        "flights": [
                            {
                                "id": "flight-1",
                                "statusCode": "HK",
                                "bookingClass": "Y",
                                "fareFamilyCode": "EL1",
                                "cabin": "eco",
                            }
                        ]
                    }
                ]
            },
        },
        "dictionaries": {
            "currency": {"VND": {"decimalPlaces": 0}},
            "flight": {
                "flight-1": {
                    "marketingAirlineCode": "9G",
                    "marketingFlightNumber": "123",
                    "operatingAirlineCode": "9G",
                    "operatingFlightNumber": "123",
                    "departure": {"locationCode": "SGN", "dateTime": "2026-08-01T08:00:00+07:00"},
                    "arrival": {"locationCode": "PQC", "dateTime": "2026-08-01T09:00:00+07:00"},
                }
            },
        },
    }


def test_order_parser_maps_eticket_to_open_for_use():
    order = WebOrderParser.parse(itinerary())

    assert order.order_state == OrderStateEnum.OPEN_FOR_USE
    assert order.pnr == "ABC123"
    assert order.passengers[0].ticket_number == "1234567890123"
    assert order.journeys[0].segments[0].flight_number == "9G0123"
    assert order.journeys[0].bundles[0].product_tag == "ECONOMY LITE"
    assert order.total_amount == Decimal("1250000")
    assert order.currency_code == "VND"


def test_order_parser_maps_unticketed_order_to_hold():
    order = WebOrderParser.parse(itinerary(ticket_status=None))
    assert order.order_state == OrderStateEnum.HOLD
    assert order.passengers[0].ticket_number is None


def test_order_parser_maps_explicit_cancellation_and_unknown():
    assert WebOrderParser.parse(itinerary(ticket_status=None, order_status="CANCELLED")).order_state == OrderStateEnum.CANCEL
    unknown = itinerary(ticket_status=None, order_status="MYSTERY")
    assert WebOrderParser.parse(unknown).order_state == OrderStateEnum.UNKNOWN

    with pytest.raises(ServiceError) as error:
        WebOrderParser.parse({"data": {}, "dictionaries": {}})
    assert error.value.code == ServiceStateEnum.DATA_VALIDATION_FAILED.name


def test_order_parser_does_not_map_expired_or_failed_order_to_hold():
    assert WebOrderParser.parse(itinerary(ticket_status=None, order_status="EXPIRED")).order_state == OrderStateEnum.UNKNOWN
    assert WebOrderParser.parse(itinerary(ticket_status=None, order_status="FAILED")).order_state == OrderStateEnum.UNKNOWN


def test_order_parser_attaches_purchased_baggage_to_passenger():
    data = itinerary()
    data["data"]["services"] = [
        {
            "travelerIds": ["traveler-1"],
            "descriptions": [{"content": "PREPAID BAGGAGE 20 KG"}],
            "quantity": 1,
            "id": "bag-20",
        }
    ]

    order = WebOrderParser.parse(data)

    baggage = order.passengers[0].ssr.baggage[0]
    assert baggage.type == SsrTypeEnum.HAULING_BAGGAGE
    assert baggage.code == "bag-20"
    assert baggage.weight == 20


def test_order_parser_attaches_free_checked_and_carry_on_allowances():
    policies = {
        "data": {
            "freeCheckedBaggageAllowance": [
                {
                    "travelerIds": ["traveler-1"],
                    "details": {
                        "quantity": 1,
                        "baggageCharacteristics": [{"description": "UP TO 23 KG"}],
                    },
                }
            ],
            "freeCarryOnAllowance": [
                {
                    "travelerIds": ["traveler-1"],
                    "details": {
                        "quantity": 1,
                        "baggageCharacteristics": [{"description": "UP TO 7 KG"}],
                    },
                }
            ],
        }
    }

    order = WebOrderParser.parse(itinerary(), policies)

    assert [item.type for item in order.passengers[0].ssr.baggage] == [
        SsrTypeEnum.HAULING_BAGGAGE,
        SsrTypeEnum.HAND_BAGGAGE,
    ]
    assert [item.weight for item in order.passengers[0].ssr.baggage] == [23, 7]
