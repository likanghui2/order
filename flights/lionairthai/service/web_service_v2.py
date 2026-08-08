from decimal import Decimal
from typing import Optional

from common.enums.gender_enum import GenderEnum
from common.enums.passenger_type_enum import PassengerTypeEnum
from common.errors.service_error import ServiceError, ServiceStateEnum
from common.model.flight.flight_bundle_model import FlightBundleModel
from common.model.flight.flight_journey_model import FlightJourneyModel
from common.model.order.contact_info_model import ContactInfoModel
from common.model.order.passenger_info_model import PassengerInfoModel
from common.model.order.payment_info_model import PaymentInfoModel
from common.model.proxy_Info_model import ProxyInfoModel
from common.utils.pay_2c2p_util import Pay2c2pUtil
from flights.lionairthai.config_v2 import LionairthaiConfigV2
from flights.lionairthai.flight_common.flight_info_parser_v2 import FlightInfoParserV2
from flights.lionairthai.script.web_script_v2 import WebScriptV2


class WebServiceV2:
    def __init__(self, proxy_info: Optional[ProxyInfoModel] = None):
        self._script = WebScriptV2(proxy_info)

    def initialize_session(self):
        self._script.initialize_session()

    def search(self, dep_airport: str, arr_airport: str, date: str,
               adt_number: int, chd_number: int, currency_code: str,
               promo_code: str = "", ret_date: Optional[str] = None):
        if adt_number <= 0 or chd_number < 0:
            raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, "passengerCount")
        currency = str(currency_code or "").strip().upper()
        point_of_sale = LionairthaiConfigV2.CURRENCY_POINT_OF_SALE.get(currency)
        if not point_of_sale:
            raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, f"SL暂不支持币种[{currency}]")
        try:
            dep_country = LionairthaiConfigV2.airport_country(dep_airport)
            arr_country = LionairthaiConfigV2.airport_country(arr_airport)
        except ValueError as error:
            raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, str(error)) from error
        itinerary_parts = [{
                "depDate": date,
                "depPort": {"airportCode": dep_airport, "countryCode": dep_country},
                "arrPort": {"airportCode": arr_airport, "countryCode": arr_country},
            }]
        if ret_date:
            itinerary_parts.append({
                "depDate": ret_date,
                "depPort": {"airportCode": arr_airport, "countryCode": arr_country},
                "arrPort": {"airportCode": dep_airport, "countryCode": dep_country},
            })
        response = self._script.availability({
            "tripType": 1 if ret_date else 0,
            "itineraryParts": itinerary_parts,
            "paxNumbers": {
                "numAdults": adt_number,
                "numChildren": chd_number,
                "numInfants": 0,
                "numStudents": 0,
            },
            "cabinClass": 0,
            "pointOfSale": point_of_sale,
            "searchType": 0,
            "promoCode": promo_code,
            "cartId": "",
            "searchId": "",
            "userAgent": "Web",
            "sort": 2,
            "language": "en_US",
        })
        if response.get("error"):
            raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, str(response["error"]))
        return FlightInfoParserV2.parse(response)

    def add_cart(self, bundle: FlightBundleModel, adult_count: int):
        response = self._script.add_cart({
            "cartId": "",
            "searchId": "",
            "fareIds": [bundle.fare_key],
            "paxNumbers": {
                "numAdults": adult_count,
                "numChildren": 0,
                "numInfants": 0,
                "numStudents": 0,
            },
        })
        self._check(response, "add/cart")

    def get_cart(self) -> dict:
        response = self._script.get_cart()
        self._check(response, "get/cart")
        return response

    def add_passengers(self, passengers: list[PassengerInfoModel],
                       contact: ContactInfoModel, international: bool):
        payload_passengers = []
        for passenger in passengers:
            if passenger.type != PassengerTypeEnum.ADT:
                raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, "passengerType")
            document = passenger.document_info
            nationality = (document.nationality if document else "US") or "US"
            passport = None
            if international:
                if not document or not document.number or not document.expire_date:
                    raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, "passport")
                passport = {
                    "birthCountry": nationality,
                    "issuingCountry": document.issuing_country or nationality,
                    "number": document.number,
                    "expirationDate": document.expire_date,
                }
            title = LionairthaiConfigV2.PASSENGER_TITLE[f"ADT_{passenger.gender.value}"]
            payload_passengers.append({
                "passengerInfo": {
                    "title": title,
                    "givenName": passenger.first_name,
                    "surname": passenger.last_name,
                    "gender": 0 if passenger.gender == GenderEnum.M else 1,
                    "birthDate": passenger.birthday,
                    "nationality": nationality,
                    "passport": passport,
                    "middleName": None,
                },
                "paxCode": 0,
            })
        first = payload_passengers[0]["passengerInfo"]
        phone_country = str(contact.phone_code or "66").replace("+", "").removeprefix("00")
        location_code = "DMK0066" if phone_country == "66" else f"JFK00{phone_country}"
        response = self._script.add_passengers({
            "passengers": payload_passengers,
            "contactInfo": {
                "phone": {
                    "countryCode": f"+{phone_country}",
                    "locationCityCode": location_code,
                    "number": contact.phone_number,
                    "type": "HOME",
                },
                "email": contact.email_address,
                "confirmEmail": contact.email_address,
                "title": first["title"],
                "givenName": contact.first_name,
                "surname": contact.last_name,
            },
            "cartId": "",
            "searchId": "",
            "ipAddress": "",
            "userAgent": "Web",
            "browserNameAndVersion": LionairthaiConfigV2.USER_AGENT,
        })
        self._check(response, "add/pax")

    def get_booking_cart(self) -> dict:
        response = self._script.get_booking_cart()
        self._check(response, "Get/BookingCart")
        return response

    @staticmethod
    def validate_cart(cart: dict, bundle: FlightBundleModel, passenger_count: int,
                      journey: FlightJourneyModel):
        if cart.get("totalCost") is None:
            raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, "cart.totalCost")
        expected = (
            bundle.price_info.adult_ticket_price + bundle.price_info.adult_tax_price
        ) * passenger_count
        actual = Decimal(str(cart["totalCost"]))
        if actual != expected:
            raise ServiceError(
                ServiceStateEnum.BUSINESS_ERROR,
                f"SL价格变化，查询价[{expected}]，购物车价[{actual}]",
            )

        fares = cart.get("fares") or []
        if not fares:
            raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, "cart.fares")
        matching_fares = [
            fare for fare in fares
            if fare.get("depPort") == journey.dep_airport
            and fare.get("arrPort") == journey.arr_airport
        ]
        if len(matching_fares) != 1:
            raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, "cart.route")
        fare = matching_fares[0]
        expected_flights = [segment.flight_number for segment in journey.segments]
        actual_flights = []
        for segment in fare.get("flightSegs") or []:
            carrier = segment.get("carrier") or {}
            actual_flights.append(
                f"{carrier.get('airCode') or ''}{carrier.get('airFlightNo') or ''}"
            )
        if actual_flights != expected_flights:
            raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, "cart.flight")

        brands = fare.get("brands") or []
        if not any(
            str(brand.get("basketHashCode") or "") == str(bundle.fare_key or "")
            for brand in brands
        ):
            raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, "cart.bundle")

        fare_cost = fare.get("cartTotalFareCost") or cart.get("cartTotalFareCost") or {}
        cart_currency = fare_cost.get("currency")
        if cart_currency != bundle.price_info.currency:
            raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, "cart.currency")
        quantity = (fare_cost.get("fareBreakDown") or {}).get("quantity")
        if quantity is None or int(quantity) != passenger_count:
            raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, "cart.passengerCount")

    def failed_payment_pnr(self, payment: PaymentInfoModel,
                           contact: ContactInfoModel,
                           first_passenger: PassengerInfoModel,
                           currency: str) -> tuple[str, dict]:
        expiry = payment.card_expiry_date.split("/")
        if len(expiry) != 2:
            raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, "cardExpiryDate")
        month, year = expiry
        if len(year) == 2:
            year = f"20{year}"
        secure_token = Pay2c2pUtil.encrypt_card_info(
            payment.card_number,
            year,
            month,
            payment.card_cvv,
        )
        title = LionairthaiConfigV2.PASSENGER_TITLE[f"ADT_{first_passenger.gender.value}"]
        response = self._script.payment({
            "cartId": "",
            "searchId": "",
            "customerIp": "",
            "securePayToken": secure_token,
            "currency": currency,
            "custName": f"{title} {contact.first_name} {contact.last_name}",
            "custEmail": contact.email_address,
            "PaymentMethod": "1",
        })
        if response.get("status") is True:
            raise ServiceError(ServiceStateEnum.PAYMENT_EXCEPTION, "SL压位支付意外成功")
        pnr = response.get("pnr")
        if not (
            response.get("status") is False
            and isinstance(pnr, str)
            and len(pnr) == 6
            and pnr.isascii()
            and pnr.isalnum()
        ):
            raise ServiceError(
                ServiceStateEnum.BUSINESS_ERROR,
                response.get("message") or "SL失败支付未返回PNR",
            )
        return pnr, response

    @staticmethod
    def _check(response: dict, operation: str):
        if not isinstance(response, dict) or response.get("status") is not True:
            message = response.get("message") if isinstance(response, dict) else None
            raise ServiceError(ServiceStateEnum.BUSINESS_ERROR, message or operation)
