from decimal import Decimal

from common.enums.freight_rate_type_enum import FreightRateTypeEnum
from common.enums.gender_enum import GenderEnum
from common.enums.order_state_enum import OrderStateEnum
from common.enums.passenger_type_enum import PassengerTypeEnum
from common.enums.ssr_type_enum import SsrTypeEnum
from common.model.flight.flight_baggage_model import FlightBaggageModel
from common.model.flight.flight_bundle_model import FlightBundleModel
from common.model.flight.flight_bundle_price_model import FlightBundlePriceModel
from common.model.flight.flight_ssr_info_model import FlightSsrInfoModel
from common.model.order.contact_info_model import ContactInfoModel
from common.model.order.passenger_info_model import PassengerInfoModel
from flights.sunphuquocairways_9g.service.web_service import WebService
from tests.flight_9gweb.test_web_flight_parser import WEB_SEARCH_RESPONSE
from tests.flight_9gweb.test_web_order_parser import itinerary


BUNDLE = FlightBundleModel(
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
    seat=5,
    freightRateType=FreightRateTypeEnum.PT,
)

PASSENGERS = [
    PassengerInfoModel(
        type=PassengerTypeEnum.ADT,
        lastName="LOVELACE",
        firstName="ADA",
        gender=GenderEnum.F,
        birthday="1990-01-01",
    ),
    PassengerInfoModel(
        type=PassengerTypeEnum.CHD,
        lastName="LOVELACE",
        firstName="BYRON",
        gender=GenderEnum.M,
        birthday="2018-01-01",
    ),
]

CONTACT = ContactInfoModel(
    lastName="LOVELACE",
    firstName="ADA",
    emailAddress="ada@example.com",
    phoneCode="+84",
    phoneNumber="901234567",
)


class FakeScript:
    def __init__(self):
        self.initialized = 0
        self.authenticated = []
        self.search_calls = []
        self.updated_travelers = []
        self.contacts = []
        self.purchase_calls = 0
        self.service_calls = []

    def initialize_session(self):
        self.initialized += 1

    def authenticate(self, currency):
        self.authenticated.append(currency)

    def search(self, airport_data, adult_count, child_count, promo_code=""):
        self.search_calls.append((airport_data, adult_count, child_count, promo_code))
        return WEB_SEARCH_RESPONSE

    def create_cart(self, air_bound_ids):
        assert air_bound_ids == ["bound-1"]
        return {
            "data": {
                "id": "cart-1",
                "travelers": [
                    {"id": "cart-adt", "passengerTypeCode": "ADT"},
                    {"id": "cart-chd", "passengerTypeCode": "CHD"},
                ],
            }
        }

    def update_traveler(self, cart_id, traveler_id, traveler, last_name):
        self.updated_travelers.append((cart_id, traveler_id, traveler, last_name))
        return {"data": {}}

    def add_contacts(self, cart_id, contacts, last_name):
        self.contacts.append((cart_id, contacts, last_name))
        return {"data": contacts}

    def purchase_order(self, cart_id):
        self.purchase_calls += 1
        return {
            "data": [
                {
                    "id": "ABC123",
                    "travelers": [
                        {
                            "id": "order-adt",
                            "passengerTypeCode": "ADT",
                            "names": [{"firstName": "ADA", "lastName": "LOVELACE"}],
                        },
                        {
                            "id": "order-chd",
                            "passengerTypeCode": "CHD",
                            "names": [{"firstName": "BYRON", "lastName": "LOVELACE"}],
                        },
                    ],
                    "contacts": [{"id": "contact-1", "contactType": "Email"}],
                    "remainingAmount": {"value": 2250000, "currencyCode": "VND"},
                }
            ],
            "dictionaries": {
                "currency": {"VND": {"decimalPlaces": 0}},
                "flight": {
                    "flight-1": {"marketingAirlineCode": "9G", "marketingFlightNumber": "123"}
                },
            },
        }

    def services_by_order(self, pnr, last_name):
        return {"data": [{"services": []}]}

    def add_services(self, pnr, last_name, services):
        self.service_calls.append((pnr, last_name, services))
        return {"data": {}}

    def get_itinerary(self, pnr, last_name):
        return itinerary()

    def get_baggage(self, pnr, last_name):
        return {"data": []}


def service():
    return WebService(None, script=FakeScript())


def test_search_authenticates_on_currency_change_and_parses_round_trip():
    current = service()
    current.initialize_session()

    journeys = current.search(
        "SGN", "PQC", "2026-08-01T00:00:00", 1, 1, "VND", "2026-08-04T00:00:00", "SAVE"
    )
    current.search("SGN", "PQC", "2026-08-01T00:00:00", 1, 0, "VND")

    assert current.script.initialized == 1
    assert current.script.authenticated == ["VND"]
    assert len(current.script.search_calls[0][0]) == 2
    assert journeys[0].bundles[0].product_tag == "ECONOMY LITE"


def test_create_order_updates_every_traveler_and_purchases_once():
    current = service()

    result = current.create_order(BUNDLE, PASSENGERS, CONTACT)

    assert current.script.purchase_calls == 1
    assert len(current.script.updated_travelers) == len(PASSENGERS)
    assert len(current.script.contacts) == 1
    assert current.script.updated_travelers[0][2]["names"][0]["title"] == "MRS"
    assert current.script.updated_travelers[1][2]["names"][0]["title"] == "MSTR"
    assert result.pnr == "ABC123"
    assert result.total_amount == Decimal("2250000")
    assert result.currency == "VND"
    assert result.flight_ids == {"9G0123": "flight-1"}
    assert PASSENGERS[0].ext["travelerId"] == "order-adt"


def test_add_requested_baggage_merges_quantities_and_submits_once():
    current = service()
    passenger = PASSENGERS[0].model_copy(deep=True)
    passenger.ext["travelerId"] = "order-adt"
    passenger.ssr = FlightSsrInfoModel(
        baggage=[
            FlightBaggageModel(
                type=SsrTypeEnum.HAULING_BAGGAGE,
                code="bag-20",
                price=Decimal("100000"),
                number=2,
                weight=20,
            )
        ]
    )

    current.add_requested_baggage("ABC123", [passenger], "LOVELACE")

    assert current.script.service_calls == [
        (
            "ABC123",
            "LOVELACE",
            [{"serviceId": "bag-20", "travelerId": "order-adt", "quantity": 2, "parameters": []}],
        )
    ]


def test_order_detail_uses_itinerary_and_maps_status():
    current = service()
    order = current.order_detail("ABC123", "LOVELACE", "VND")

    assert current.script.authenticated == ["VND"]
    assert order.order_state == OrderStateEnum.OPEN_FOR_USE
    assert order.pnr == "ABC123"
