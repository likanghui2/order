from decimal import Decimal
from typing import Optional

from common.enums.gender_enum import GenderEnum
from common.enums.passenger_type_enum import PassengerTypeEnum
from common.errors.service_error import ServiceError, ServiceStateEnum
from common.model.flight.flight_bundle_model import FlightBundleModel
from common.model.order.contact_info_model import ContactInfoModel
from common.model.order.passenger_info_model import PassengerInfoModel
from common.model.proxy_Info_model import ProxyInfoModel
from flights.malaysiaairlines_mh.flight_common.web_flight_parser import WebFlightParser
from flights.malaysiaairlines_mh.script.web_script import WebScript


class WebService:
    def __init__(self, proxy_info: Optional[ProxyInfoModel] = None):
        self._script = WebScript(proxy_info)

    @property
    def currency(self) -> str:
        return self._script.currency

    def initialize_session(self):
        self._script.initialize_session()

    def initialize_security(self):
        self._script.reese84()

    def initialization(self, currency: str):
        self._script.initialization(currency)

    def close(self):
        self._script.close()

    def prepare_search(
        self,
        airport_data: list[tuple[str, str, str]],
        adult_count: int,
        child_count: int,
        promo_code: str = "",
    ):
        if promo_code:
            self._script.promo_code_search(
                self._portal_search_data(
                    airport_data,
                    adult_count,
                    child_count,
                    promo_code,
                )
            )
        else:
            self._script.init_facts(
                self._portal_search_data(
                    airport_data,
                    adult_count,
                    child_count,
                    "",
                )
            )

    def search(
        self,
        airport_data: list[tuple[str, str, str]],
        adult_count: int,
        child_count: int,
        promo_code: str = "",
    ):
        try:
            responses = self._search_raw(
                airport_data,
                adult_count,
                child_count,
                promo_code,
            )
        except ServiceError as exc:
            if exc.code != ServiceStateEnum.ROBOT_CHECK.name:
                raise
            currency = self.currency
            self.initialize_security()
            self.initialization(currency)
            responses = self._search_raw(
                airport_data,
                adult_count,
                child_count,
                promo_code,
            )
        return WebFlightParser.parse(
            responses,
            child_count=child_count,
            promo_code=promo_code,
        )

    def select_flight(self, bundle: FlightBundleModel) -> dict:
        if not bundle.fare_key:
            raise ServiceError(
                ServiceStateEnum.DATA_VALIDATION_FAILED,
                "fareKey",
            )
        return self._script.select_flight(bundle.fare_key.split("^"))

    def add_passengers(
        self,
        passengers: list[PassengerInfoModel],
        select_flight_response: dict,
        contact: ContactInfoModel,
    ) -> dict:
        response_data = select_flight_response.get("data") or {}
        response_travelers = response_data.get("travelers") or []
        if len(response_travelers) < len(passengers):
            raise ServiceError(
                ServiceStateEnum.BUSINESS_ERROR,
                "MH 购物车乘客数量不一致",
            )
        travelers = []
        for passenger, response_traveler in zip(passengers, response_travelers):
            if response_traveler.get("passengerTypeCode") != passenger.type.value:
                raise ServiceError(
                    ServiceStateEnum.BUSINESS_ERROR,
                    "MH 购物车乘客类型不一致",
                )
            if passenger.type == PassengerTypeEnum.ADT:
                title = "MS" if passenger.gender == GenderEnum.F else "MR"
            else:
                title = "MISS" if passenger.gender == GenderEnum.F else "MSTR"
            traveler = {
                "id": response_traveler["id"],
                "passengerTypeCode": passenger.type.value,
                "names": [{
                    "title": title,
                    "firstName": passenger.first_name,
                    "middleName": "",
                    "lastName": passenger.last_name,
                }],
                "gender": None,
                "nationalityCountryCodes": [],
            }
            if passenger.type == PassengerTypeEnum.CHD and passenger.birthday:
                traveler["dateOfBirth"] = passenger.birthday[:10]
            travelers.append(traveler)
        payload = {
            "travelers": travelers,
            "frequentFlyerCards": [],
            "contacts": [
                {
                    "address": contact.email_address,
                    "category": "personal",
                    "contactType": "Email",
                    "lang": "zh",
                    "purpose": "standard",
                    "travelerIds": [],
                },
                {
                    "category": "personal",
                    "contactType": "Phone",
                    "countryPhoneExtension": contact.phone_code,
                    "deviceType": "mobile",
                    "lang": "zh",
                    "number": contact.phone_number,
                    "purpose": "standard",
                    "travelerIds": [],
                },
            ],
            "extensions": [{
                "extensionType": "TextExtension",
                "name": "NEWSLETTER_SUBSCRIPTION",
                "content": "NEWSLETTER_SUBSCRIPTION",
            }],
        }
        return self._script.add_passengers(
            response_data["id"],
            passengers[0].last_name,
            payload,
        )

    def purchase_order(
        self,
        add_passengers_response: dict,
        passengers: list[PassengerInfoModel],
    ) -> dict:
        cart_id = (add_passengers_response.get("data") or {}).get("id")
        if not cart_id:
            raise ServiceError(
                ServiceStateEnum.DATA_VALIDATION_FAILED,
                "cartId",
            )
        try:
            response = self._script.purchase_order(cart_id)
        except ServiceError as exc:
            if exc.code != ServiceStateEnum.HCAP_RISK_CHECK_FAILED.name:
                raise
            self._script.solve_purchase_captcha()
            response = self._script.purchase_order(cart_id)
        order = (response.get("data") or [{}])[0]
        traveler_map = {
            (
                str((traveler.get("names") or [{}])[0].get("lastName") or "").upper(),
                str((traveler.get("names") or [{}])[0].get("firstName") or "").upper(),
            ): traveler.get("id")
            for traveler in order.get("travelers") or []
        }
        for passenger in passengers:
            passenger.key = traveler_map.get(
                (passenger.last_name.upper(), passenger.first_name.upper())
            )
        return response

    @staticmethod
    def order_total(response: dict) -> tuple[Decimal, str]:
        order = (response.get("data") or [{}])[0]
        prices = ((order.get("air") or {}).get("prices") or {})
        total_prices = prices.get("totalPrices") or [{}]
        total_price = total_prices[0]
        total = total_price.get("total", total_price)
        currency = (
            (total.get("currencyCode") if isinstance(total, dict) else None)
            or total_price.get("currencyCode")
            or ""
        )
        value = (
            total.get("value", total.get("total", 0))
            if isinstance(total, dict)
            else total
        )
        decimal_places = int(
            ((response.get("dictionaries") or {}).get("currency") or {})
            .get(currency, {})
            .get("decimalPlaces", 2)
        )
        return Decimal(str(value or 0)) / (Decimal(10) ** decimal_places), currency

    def _search_raw(
        self,
        airport_data: list[tuple[str, str, str]],
        adult_count: int,
        child_count: int,
        promo_code: str,
    ) -> list[dict]:
        responses = []
        for index in range(len(airport_data)):
            selected_bound_id = None
            if index == 1:
                first_groups = (
                    (responses[0].get("data") or {}).get("airBoundGroups") or []
                )
                first_bounds = (
                    first_groups[0].get("airBounds") or []
                    if first_groups
                    else []
                )
                if first_bounds:
                    selected_bound_id = first_bounds[0].get("airBoundId")
            responses.append(
                self._script.search_flight(
                    airport_data=airport_data,
                    adult_count=adult_count,
                    child_count=child_count,
                    requested_bound=index,
                    promo_code=promo_code,
                    selected_bound_id=selected_bound_id,
                )
            )
        return responses

    @staticmethod
    def _portal_search_data(
        airport_data: list[tuple[str, str, str]],
        adult_count: int,
        child_count: int,
        promo_code: str,
    ) -> dict:
        return {
            "departDate1": airport_data[0][2]
            .replace("-", "")
            .replace("T", "")
            .replace(":", "")
            .split(".")[0][:12],
            "returnDate1": (
                ""
                if len(airport_data) == 1
                else airport_data[1][2]
                .replace("-", "")
                .replace("T", "")
                .replace(":", "")
                .split(".")[0][:12]
            ),
            "originCountry": "Malaysia",
            "originAirportCode1": airport_data[0][0],
            "destAirportCode1": airport_data[0][1],
            "flightClass": "CFFECO|E",
            "adultCount": str(adult_count),
            "childCount": str(child_count),
            "infantCount": "0",
            "paymentType": "cash",
            "amal1": False,
            "promoCode": promo_code,
            "regionLanguage": "cn-Zh_cn",
            "amcvId": "",
            "teaserCategory": "",
            "isJdtPortal": False,
            "isJdtNormalBooking": False,
            "enrichAlwaysOnEligibility": "false",
            "autoApplyEnrichAlwaysOn": True,
        }
