from datetime import datetime, timedelta
from typing import Dict, List, Optional

from common.enums.gender_enum import GenderEnum
from common.enums.passenger_type_enum import PassengerTypeEnum
from common.errors.service_error import ServiceError, ServiceStateEnum
from common.model.flight.flight_bundle_model import FlightBundleModel
from common.model.flight.flight_journey_model import FlightJourneyModel
from common.model.order.contact_info_model import ContactInfoModel
from common.model.order.passenger_info_model import PassengerInfoModel
from common.model.proxy_Info_model import ProxyInfoModel
from common.model.task.response_order_info_model import ResponseOrderInfoModel
from common.utils.date_util import DateUtil
from flights.bookcabin.config import BookCabinConfig
from flights.bookcabin.flight_common.flight_parse import FlightParse
from flights.bookcabin.script.web_script import WebScript


class WebService:
    def __init__(self, proxy_info: Optional[ProxyInfoModel] = None):
        self.__script = WebScript(proxy_info=proxy_info)
        self.__country_code_map: Optional[Dict[str, str]] = None

    def initialize_session(self):
        self.__script.initialize_session()

    def initialize_http(self):
        self.initialize_session()

    def close(self):
        self.__script.close()

    def search(self,
               dep_airport: str,
               arr_airport: str,
               dep_date: str,
               adult_count: int,
               child_count: int,
               currency_code: str,
               ret_date: Optional[str] = None,
               promo_code: str = "",
               cabin_class: str = BookCabinConfig.DEFAULT_CABIN_CLASS) -> List[FlightJourneyModel]:
        response = self.__script.search(
            dep_airport=dep_airport,
            arr_airport=arr_airport,
            dep_date=dep_date,
            adult_count=adult_count,
            child_count=child_count,
            infant_count=0,
            currency_code=currency_code,
            ret_date=ret_date,
            promo_code=promo_code,
            cabin_class=self.__normalize_cabin_class(cabin_class),
        )
        return FlightParse.parse_search_response(response=response, child_count=child_count)

    def booking(self,
                journey: FlightJourneyModel,
                passengers: List[PassengerInfoModel],
                contact_info: ContactInfoModel,
                bundle: FlightBundleModel,
                response_order_data: ResponseOrderInfoModel) -> ResponseOrderInfoModel:
        cart_response = self.__script.create_cart(self.__build_cart_payload(bundle=bundle))
        cart_id = ((cart_response.get("data") or {}).get("cartId")
                   or (bundle.ext or {}).get("cartId")
                   or (journey.ext or {}).get("cartId"))
        if not cart_id:
            raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, "cartId")

        self.__script.cart_detail(cart_id)
        self.__script.ancillary(cart_id)

        booking_response = self.__script.booking(
            self.__build_booking_payload(
                cart_id=cart_id,
                passengers=passengers,
                contact_info=contact_info,
            )
        )
        booking_data = booking_response.get("data") or {}
        order_id = booking_data.get("orderId") or ""
        order_hash_id = booking_data.get("orderHash") or booking_data.get("orderHashId") or ""
        if not order_id or not order_hash_id:
            raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, "orderId/orderHash")

        order_response = self.__script.order_detail(order_id=order_id, order_hash_id=order_hash_id)
        order_result = FlightParse.parse_order_result(order_response)

        journey.bundles = [bundle]
        response_order_data.order_number = order_result["orderNo"] or order_id
        response_order_data.pnr = order_result["pnr"]
        response_order_data.passengers = passengers
        response_order_data.journeys = [journey]
        response_order_data.contact_info = contact_info
        response_order_data.currency_code = order_result["currency"] or bundle.price_info.currency
        response_order_data.total_amount = order_result["totalAmount"]
        return response_order_data

    @staticmethod
    def __build_cart_payload(bundle: FlightBundleModel) -> dict:
        ext = bundle.ext or {}
        fare_id = ext.get("fareId") or bundle.fare_key
        selected_fare_id = ext.get("selectedFareId") or {
            "depart": fare_id,
            "return": "",
        }
        if not selected_fare_id.get("depart") and fare_id:
            selected_fare_id["depart"] = fare_id

        cart_id = ext.get("cartId")
        search_id = ext.get("searchId")
        if not cart_id or not search_id or not selected_fare_id.get("depart"):
            raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, "cart booking data")

        return {
            "cartId": cart_id,
            "searchId": search_id,
            "selectedFareId": selected_fare_id,
            "currency": bundle.price_info.currency,
        }

    def __build_booking_payload(self,
                                cart_id: str,
                                passengers: List[PassengerInfoModel],
                                contact_info: ContactInfoModel) -> dict:
        adults = []
        children = []
        infants = []
        for index, passenger in enumerate(passengers, start=1):
            passenger_data = self.__build_passenger(passenger=passenger, index=index)
            if passenger.type == PassengerTypeEnum.CHD:
                children.append(passenger_data)
            elif passenger.type == PassengerTypeEnum.INF:
                infants.append(passenger_data)
            else:
                adults.append(passenger_data)

        return {
            "cartId": cart_id,
            "contact": self.__build_contact(contact_info=contact_info),
            "adults": adults,
            "childs": children,
            "infants": infants,
            "addons": {
                "insurances": [],
                "vouchers": [],
                "esims": [],
            },
        }

    def __build_passenger(self, passenger: PassengerInfoModel, index: int) -> dict:
        document_info = passenger.document_info
        nationality = (
            (document_info.nationality if document_info else None)
            or (document_info.issuing_country if document_info else None)
            or "US"
        )
        passport_number = (document_info.number if document_info else None) or self.__fallback_passport_number(
            passenger=passenger,
            index=index,
        )
        expire_date = (document_info.expire_date if document_info else None) or "2035-12-31"
        birthday = passenger.birthday or "1988-01-01"

        return {
            "title": self.__title(passenger),
            "firstName": (passenger.first_name or "").upper(),
            "lastName": (passenger.last_name or "").upper(),
            "dob": self.__frontend_iso_date(birthday),
            "nationality": self.__country_numeric_code(nationality),
            "passportNumber": passport_number,
            "dateOfExpired": self.__frontend_iso_date(expire_date),
            "ancillaries": {
                "baggages": [],
                "meals": [],
                "seats": [],
                "merchandises": [],
            },
        }

    @staticmethod
    def __normalize_cabin_class(cabin_class: str) -> str:
        value = (cabin_class or "").strip().upper()
        if value in {"C", "J", "BUSINESS"}:
            return "BUSINESS"
        if value in {"F", "FIRST"}:
            return "FIRST"
        return BookCabinConfig.DEFAULT_CABIN_CLASS

    @staticmethod
    def __build_contact(contact_info: ContactInfoModel) -> dict:
        phone_code = (contact_info.phone_code or "").strip()
        phone_code = phone_code if phone_code.startswith("+") else f"+{phone_code}"
        return {
            "phoneNumber": f"{phone_code}#{contact_info.phone_number}",
            "title": "Mr",
            "firstName": (contact_info.first_name or "").upper(),
            "lastName": (contact_info.last_name or "").upper(),
            "email": (contact_info.email_address or "").upper(),
        }

    @staticmethod
    def __title(passenger: PassengerInfoModel) -> str:
        return "Mr" if passenger.gender == GenderEnum.M else "Ms"

    @staticmethod
    def __fallback_passport_number(passenger: PassengerInfoModel, index: int) -> str:
        name_seed = f"{passenger.last_name}{passenger.first_name}".upper()
        name_seed = "".join(char for char in name_seed if char.isalnum())
        return f"P{index}{name_seed[:8]}".ljust(10, "0")

    @staticmethod
    def __frontend_iso_date(date_text: str) -> str:
        parsed = DateUtil.string_to_date_auto(date_text)
        if not parsed:
            raise ServiceError(ServiceStateEnum.DATA_VALIDATION_FAILED, f"invalid date: {date_text}")
        utc_time = datetime(parsed.year, parsed.month, parsed.day) - timedelta(hours=8)
        return utc_time.strftime("%Y-%m-%dT%H:%M:%S.000Z")

    def __country_numeric_code(self, country_code: str) -> str:
        if not country_code:
            return BookCabinConfig.DEFAULT_NATIONALITY_CODE
        normalized = str(country_code).strip().upper()
        if normalized.isdigit():
            return normalized

        country_map = self.__get_country_code_map()
        return (
            country_map.get(normalized)
            or BookCabinConfig.COUNTRY_CODE_FALLBACK.get(normalized)
            or BookCabinConfig.DEFAULT_NATIONALITY_CODE
        )

    def __get_country_code_map(self) -> Dict[str, str]:
        if self.__country_code_map is not None:
            return self.__country_code_map

        result = dict(BookCabinConfig.COUNTRY_CODE_FALLBACK)
        try:
            response = self.__script.countries()
            country_payload = response.get("country")
            if isinstance(country_payload, str):
                import json

                country_payload = json.loads(country_payload)
            entities = (
                (country_payload or {}).get("Entities")
                or (country_payload or {}).get("entities")
                or response.get("Entities")
                or response.get("entities")
                or []
            )
            for item in entities:
                alpha2 = (item.get("CountryCode") or "").upper()
                numeric = item.get("CabinClubCountryCode")
                if alpha2 and numeric:
                    result[alpha2] = str(numeric)
        except Exception:
            pass

        self.__country_code_map = result
        return result
